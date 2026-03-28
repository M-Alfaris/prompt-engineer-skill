"""Experiment validation — checks plan.yaml, templates, and test data for correctness.

Usage:
    python scripts/validate.py --experiment experiments/{id}/
    python scripts/validate.py --experiment experiments/{id}/ --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Paths must be resolvable regardless of cwd — scripts are run from the
# project root via  python scripts/validate.py, so sys.path must include
# the project root so that `scripts.utils.*` imports work.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.config import load_yaml  # noqa: E402

console = Console()

VALID_STRATEGIES = {"full", "fractional", "random_sample", "latin_square", "progressive", "adaptive"}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single validation check.

    Attributes:
        name: Short, human-readable name for the check.
        passed: True when the check succeeded.
        message: Detail string — success note or failure reason.
    """

    name: str
    passed: bool
    message: str


@dataclass
class ValidationReport:
    """Aggregated results for one experiment directory.

    Attributes:
        experiment_dir: Absolute path that was validated.
        checks: Ordered list of individual check results.
    """

    experiment_dir: Path
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """True when every check passed."""
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, message: str) -> None:
        """Append a check result."""
        self.checks.append(CheckResult(name=name, passed=passed, message=message))


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------


def _check_plan_yaml(experiment_dir: Path, report: ValidationReport) -> dict[str, Any]:
    """Validate plan.yaml and return the parsed data (empty dict on failure)."""
    plan_path = experiment_dir / "plan.yaml"

    # 1. Exists
    if not plan_path.exists():
        report.add("plan.yaml: exists", False, f"File not found: {plan_path}")
        return {}
    report.add("plan.yaml: exists", True, str(plan_path))

    # 2. Valid YAML
    try:
        raw: dict[str, Any] = load_yaml(plan_path)
    except yaml.YAMLError as exc:
        report.add("plan.yaml: valid YAML", False, str(exc))
        return {}
    report.add("plan.yaml: valid YAML", True, "Parsed successfully")

    # 3. Required top-level fields
    required_top = {"axes", "evaluation", "execution", "budget"}
    # Support both flat and nested `experiment:` wrapper
    has_experiment_id = (
        "experiment_id" in raw
        or ("experiment" in raw and "id" in raw.get("experiment", {}))
    )
    missing_top = [k for k in required_top if k not in raw]
    if not has_experiment_id:
        missing_top.append("experiment_id / experiment.id")
    if missing_top:
        report.add(
            "plan.yaml: required fields",
            False,
            f"Missing: {missing_top}",
        )
    else:
        report.add("plan.yaml: required fields", True, "All required fields present")

    # 4. Unique IDs within axes
    axes: dict[str, Any] = raw.get("axes", {})
    for axis_name in ("templates", "parameters", "models"):
        items: list[dict[str, Any]] = axes.get(axis_name, [])
        ids = [i.get("id") for i in items if isinstance(i, dict)]
        duplicates = {i for i in ids if ids.count(i) > 1}
        key = f"plan.yaml: unique {axis_name} IDs"
        if duplicates:
            report.add(key, False, f"Duplicate IDs: {sorted(duplicates)}")
        else:
            report.add(key, True, f"{len(ids)} unique IDs")

    # 5. Criterion weights sum to 1.0 (±0.01)
    criteria: list[dict[str, Any]] = raw.get("evaluation", {}).get("criteria", [])
    if criteria:
        total_weight = sum(float(c.get("weight", 1.0)) for c in criteria)
        weight_ok = abs(total_weight - 1.0) <= 0.01
        report.add(
            "plan.yaml: criterion weights sum to 1.0",
            weight_ok,
            f"Sum = {total_weight:.4f}" + ("" if weight_ok else " (expected 1.0 ±0.01)"),
        )
    else:
        report.add(
            "plan.yaml: criterion weights sum to 1.0",
            True,
            "No criteria defined (skipped)",
        )

    # 6. Budget > 0
    budget: dict[str, Any] = raw.get("budget", {})
    max_cost = budget.get("max_cost_usd", 0)
    try:
        budget_ok = float(max_cost) > 0
    except (TypeError, ValueError):
        budget_ok = False
    report.add(
        "plan.yaml: budget > 0",
        budget_ok,
        f"max_cost_usd = {max_cost}" + ("" if budget_ok else " (must be > 0)"),
    )

    # 7. Strategy is valid
    strategy = raw.get("execution", {}).get("strategy", "")
    strategy_ok = strategy in VALID_STRATEGIES
    report.add(
        "plan.yaml: execution strategy is valid",
        strategy_ok,
        f"strategy = '{strategy}'"
        + (
            ""
            if strategy_ok
            else f" (must be one of {sorted(VALID_STRATEGIES)})"
        ),
    )

    return raw


def _check_templates(
    experiment_dir: Path,
    plan_raw: dict[str, Any],
    report: ValidationReport,
) -> dict[str, Path]:
    """Validate every template YAML in templates/.

    Returns a mapping of template_id -> Path for all files that loaded.
    """
    template_dir = experiment_dir / "templates"

    if not template_dir.exists():
        report.add("templates/: directory exists", False, f"Not found: {template_dir}")
        return {}
    report.add("templates/: directory exists", True, str(template_dir))

    yaml_files = sorted(template_dir.glob("*.yaml"))
    if not yaml_files:
        report.add("templates/: at least one file", False, "No .yaml files found")
        return {}
    report.add("templates/: at least one file", True, f"{len(yaml_files)} file(s) found")

    loaded: dict[str, Path] = {}
    template_issues: list[str] = []
    jinja_var_pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")

    for yaml_path in yaml_files:
        try:
            raw_tmpl: dict[str, Any] = load_yaml(yaml_path)
        except yaml.YAMLError as exc:
            template_issues.append(f"{yaml_path.name}: invalid YAML — {exc}")
            continue

        # Required fields
        missing = [
            k
            for k in ("id", "name", "system_prompt", "user_prompt")
            if not raw_tmpl.get(k)
        ]
        if missing:
            template_issues.append(f"{yaml_path.name}: missing fields {missing}")
            continue

        tmpl_id: str = raw_tmpl["id"]
        raw_vars = raw_tmpl.get("variables", [])
        # Variables can be strings or dicts with a 'name' field
        declared_vars: list[str] = [
            v["name"] if isinstance(v, dict) else str(v)
            for v in raw_vars
        ]

        # Check technique field
        if "technique" not in raw_tmpl:
            template_issues.append(f"{yaml_path.name}: missing 'technique' field")

        # Jinja2 variable references vs. declared variables
        all_text = raw_tmpl["system_prompt"] + "\n" + raw_tmpl["user_prompt"]
        referenced_vars = set(jinja_var_pattern.findall(all_text))
        declared_set = set(declared_vars)

        undeclared = referenced_vars - declared_set
        if undeclared:
            template_issues.append(
                f"{yaml_path.name}: variables used but not declared: {sorted(undeclared)}"
            )

        unused = declared_set - referenced_vars
        if unused:
            template_issues.append(
                f"{yaml_path.name}: variables declared but not used: {sorted(unused)}"
            )

        loaded[tmpl_id] = yaml_path

    if template_issues:
        report.add(
            "templates/: all files valid",
            False,
            "; ".join(template_issues),
        )
    else:
        report.add(
            "templates/: all files valid",
            True,
            f"All {len(loaded)} template(s) passed",
        )

    return loaded


def _check_test_inputs(experiment_dir: Path, report: ValidationReport) -> None:
    """Validate data/test_inputs.yaml."""
    inputs_path = experiment_dir / "data" / "test_inputs.yaml"

    if not inputs_path.exists():
        report.add(
            "data/test_inputs.yaml: exists",
            False,
            f"File not found: {inputs_path}",
        )
        return
    report.add("data/test_inputs.yaml: exists", True, str(inputs_path))

    try:
        raw: dict[str, Any] = load_yaml(inputs_path)
    except yaml.YAMLError as exc:
        report.add("data/test_inputs.yaml: valid YAML", False, str(exc))
        return
    report.add("data/test_inputs.yaml: valid YAML", True, "Parsed successfully")

    inputs: list[Any] = raw.get("inputs", [])
    if not isinstance(inputs, list) or not inputs:
        report.add(
            "data/test_inputs.yaml: has inputs list",
            False,
            "'inputs' key is missing or empty",
        )
        return
    report.add(
        "data/test_inputs.yaml: has inputs list",
        True,
        f"{len(inputs)} input(s) found",
    )

    # Unique IDs + non-empty text
    ids_seen: set[str] = set()
    input_issues: list[str] = []
    for idx, item in enumerate(inputs):
        if not isinstance(item, dict):
            input_issues.append(f"item[{idx}] is not a dict")
            continue
        item_id = item.get("id")
        if not item_id:
            input_issues.append(f"item[{idx}] has no 'id'")
        elif item_id in ids_seen:
            input_issues.append(f"duplicate id '{item_id}'")
        else:
            ids_seen.add(str(item_id))

        text = item.get("text", "")
        if not text or not str(text).strip():
            input_issues.append(f"item id='{item_id}' has empty 'text'")

    if input_issues:
        report.add(
            "data/test_inputs.yaml: inputs valid",
            False,
            "; ".join(input_issues[:5])
            + ("..." if len(input_issues) > 5 else ""),
        )
    else:
        report.add(
            "data/test_inputs.yaml: inputs valid",
            True,
            f"All {len(inputs)} inputs have unique IDs and non-empty text",
        )


def _check_cross_validation(
    plan_raw: dict[str, Any],
    loaded_templates: dict[str, Path],
    report: ValidationReport,
) -> None:
    """Cross-validate plan.yaml references against the file system."""
    if not plan_raw:
        return

    axes = plan_raw.get("axes", {})

    # Every template_id in plan.yaml must have a loaded file
    plan_template_ids = {
        t.get("id") for t in axes.get("templates", []) if isinstance(t, dict)
    }
    missing_files = plan_template_ids - set(loaded_templates.keys())
    if missing_files:
        report.add(
            "cross-validation: all plan template_ids have matching files",
            False,
            f"No matching template file for: {sorted(missing_files)}",
        )
    else:
        report.add(
            "cross-validation: all plan template_ids have matching files",
            True,
            f"All {len(plan_template_ids)} template reference(s) resolved",
        )

    # Every model must have a provider field
    models: list[dict[str, Any]] = axes.get("models", [])
    models_without_provider = [
        m.get("id", "?")
        for m in models
        if isinstance(m, dict) and not m.get("provider")
    ]
    if models_without_provider:
        report.add(
            "cross-validation: all models have provider",
            False,
            f"Missing provider on model(s): {models_without_provider}",
        )
    else:
        report.add(
            "cross-validation: all models have provider",
            True,
            f"All {len(models)} model(s) have a provider field",
        )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_rich_report(report: ValidationReport) -> None:
    """Render the report as a rich table to the console."""
    status_icon = "[bold green]PASS[/]" if report.valid else "[bold red]FAIL[/]"
    console.print(
        f"\n[bold]Experiment:[/] {report.experiment_dir}\n"
        f"[bold]Result:    [/] {status_icon}\n"
    )

    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
        expand=False,
    )
    table.add_column("Status", width=6, justify="center")
    table.add_column("Check", style="dim")
    table.add_column("Detail")

    for chk in report.checks:
        icon = "[green]PASS[/]" if chk.passed else "[red]FAIL[/]"
        table.add_row(icon, chk.name, chk.message)

    console.print(table)

    total = len(report.checks)
    passed = sum(1 for c in report.checks if c.passed)
    console.print(
        f"\n{passed}/{total} checks passed"
        + ("\n" if report.valid else " — fix the issues above and re-run\n")
    )


def _print_json_report(report: ValidationReport) -> None:
    """Print the report as a JSON object to stdout."""
    payload = {
        "valid": report.valid,
        "checks": [
            {"name": c.name, "passed": c.passed, "message": c.message}
            for c in report.checks
        ],
    }
    print(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_experiment(experiment_dir: Path) -> ValidationReport:
    """Run all validation checks on *experiment_dir*.

    Args:
        experiment_dir: Path to the experiment root (must contain plan.yaml).

    Returns:
        A :class:`ValidationReport` with every check result populated.
    """
    report = ValidationReport(experiment_dir=experiment_dir.resolve())

    plan_raw = _check_plan_yaml(experiment_dir, report)
    loaded_templates = _check_templates(experiment_dir, plan_raw, report)
    _check_test_inputs(experiment_dir, report)
    _check_cross_validation(plan_raw, loaded_templates, report)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate",
        description="Validate an experiment directory before running it.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        metavar="DIR",
        help="Path to the experiment directory (e.g. experiments/2026-03-24-foo/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output results as JSON to stdout instead of a rich table.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 if all checks pass, 1 if any check fails.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    experiment_dir = Path(args.experiment)
    if not experiment_dir.exists():
        console.print(f"[red]ERROR:[/] Experiment directory not found: {experiment_dir}")
        return 1

    report = validate_experiment(experiment_dir)

    if args.output_json:
        _print_json_report(report)
    else:
        _print_rich_report(report)

    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())

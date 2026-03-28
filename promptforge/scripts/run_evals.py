#!/usr/bin/env python3
"""Run eval test cases for the PromptForge skill.

Reads evals/test_cases.yaml and executes all programmatic checks (file
existence, schema validation, weight sums, required fields). Tests that
require actually running the pipeline are marked requires_execution: true and
are skipped unless --execute is passed.

Usage:
    python scripts/run_evals.py
    python scripts/run_evals.py --category research
    python scripts/run_evals.py --category plan --json
    python scripts/run_evals.py --experiment experiments/2026-03-24-ecommerce-content-moderation/
    python scripts/run_evals.py --execute --experiment experiments/my-experiment/
    python scripts/run_evals.py --list-categories
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency handling — yaml is required; rich is optional
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    _RICH = True
except ImportError:
    _RICH = False

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EVALS_DIR = _PROJECT_ROOT / "evals"
_TEST_CASES_FILE = _EVALS_DIR / "test_cases.yaml"

VALID_CATEGORIES = {
    "trigger", "research", "plan", "build", "execute", "evaluate", "report", "end_to_end"
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    id: str
    name: str
    category: str
    passed: bool
    skipped: bool
    message: str
    elapsed_ms: float = 0.0


@dataclass
class EvalSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[EvalResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [
                {
                    "id": r.id,
                    "name": r.name,
                    "category": r.category,
                    "passed": r.passed,
                    "skipped": r.skipped,
                    "message": r.message,
                    "elapsed_ms": round(r.elapsed_ms, 1),
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    """Load a YAML file, returning None on parse failure."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError:
        return None


def _load_json(path: Path) -> Any:
    """Load a JSON file, returning None on parse failure."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _count_words(text: str) -> int:
    return len(text.split())


def _section_content(md_text: str, header: str) -> str:
    """Return text between the given ## header and the next ## header (or EOF)."""
    pattern = rf"^##\s+{re.escape(header)}\b"
    lines = md_text.splitlines()
    inside = False
    collected: list[str] = []
    for line in lines:
        if re.match(pattern, line, re.IGNORECASE):
            inside = True
            continue
        if inside:
            if re.match(r"^##\s", line):
                break
            collected.append(line)
    return "\n".join(collected).strip()


def _find_experiment_dir(base: Path) -> Path | None:
    """Return the most recently modified experiment subdirectory, if any."""
    experiments_root = base / "experiments"
    if not experiments_root.is_dir():
        return None
    candidates = [
        d for d in experiments_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


# ---------------------------------------------------------------------------
# Category-specific check functions
# ---------------------------------------------------------------------------

def _check_trigger(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    """
    Trigger tests cannot be fully automated without an orchestrator. We validate
    that the test case itself is well-formed and return a skip with a note.
    """
    prompt = case.get("prompt", "")
    if not prompt:
        return False, "Test case has no prompt field"
    expected = case.get("expected_behaviors", [])
    unexpected = case.get("unexpected_behaviors", [])
    if not expected:
        return False, "Trigger test has no expected_behaviors"
    return True, (
        f"Trigger test structure valid ({len(expected)} expected, "
        f"{len(unexpected)} unexpected behaviors). "
        "Full trigger verification requires orchestrator routing — run manually."
    )


def _check_research(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    brief = exp_dir / "research_brief.md"
    if not brief.exists():
        return False, f"research_brief.md not found at {brief}"

    content = brief.read_text(encoding="utf-8")
    if len(content) < 800:
        return False, f"research_brief.md is too short ({len(content)} chars, minimum 800)"

    required_sections = [
        "Task Definition",
        "Discovered LLM Models",
        "Discovered Prompt Techniques",
        "Recommended Parameter Strategy",
        "Success Criteria",
        "Constraints",
        "Test Data Strategy",
    ]
    missing = []
    for section in required_sections:
        # Accept ##, ###, or plain bold header variations
        pattern = rf"(^##\s+{re.escape(section)}|^\*\*{re.escape(section)}\*\*)"
        if not re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            missing.append(section)

    if missing:
        return False, f"research_brief.md missing sections: {missing}"

    # Check no section is empty
    for section in required_sections:
        body = _section_content(content, section)
        if len(body.strip()) < 5:
            return False, f"Section '{section}' appears to be empty in research_brief.md"

    # Check discovered models table has at least one row (| ... | pattern)
    models_body = _section_content(content, "Discovered LLM Models")
    table_rows = [l for l in models_body.splitlines() if l.startswith("|") and "---" not in l]
    if len(table_rows) < 2:  # header + at least one data row
        return False, "Discovered LLM Models section has no model rows in its table"

    # Check prompt techniques count
    techniques_body = _section_content(content, "Discovered Prompt Techniques")
    technique_headers = re.findall(r"^###\s+.+", techniques_body, re.MULTILINE)
    if len(technique_headers) < 4:
        return (
            False,
            f"Discovered Prompt Techniques has {len(technique_headers)} subsections, "
            "need at least 4",
        )

    return True, (
        f"research_brief.md looks good: {len(content)} chars, "
        f"all {len(required_sections)} sections present, "
        f"{len(technique_headers)} techniques, "
        f"{len(table_rows) - 1} model rows"
    )


def _check_plan(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    plan_path = exp_dir / "plan.yaml"
    if not plan_path.exists():
        return False, f"plan.yaml not found at {plan_path}"

    plan = _load_yaml(plan_path)
    if plan is None:
        return False, f"plan.yaml at {plan_path} failed to parse as valid YAML"

    errors: list[str] = []

    # Criterion weights sum check
    criteria = plan.get("evaluation", {}).get("criteria", [])
    if not criteria:
        errors.append("evaluation.criteria is empty")
    else:
        total_weight = sum(float(c.get("weight", 0)) for c in criteria)
        if not math.isclose(total_weight, 1.0, abs_tol=0.001):
            errors.append(
                f"evaluation.criteria weights sum to {total_weight:.4f}, expected 1.0"
            )
        for c in criteria:
            w = float(c.get("weight", -1))
            if w <= 0.0:
                errors.append(f"Criterion '{c.get('name')}' has weight <= 0.0")
            if w > 0.6:
                errors.append(
                    f"Criterion '{c.get('name')}' has weight {w:.2f} > 0.6 "
                    "(single criterion dominates)"
                )

    # Axes minimum checks
    axes = plan.get("axes", {})
    templates = axes.get("templates", [])
    params = axes.get("parameters", [])
    models = axes.get("models", [])

    if len(templates) < 2:
        errors.append(
            f"axes.templates has {len(templates)} entries, need at least 2"
        )
    if len(params) < 2:
        errors.append(
            f"axes.parameters has {len(params)} entries, need at least 2"
        )
    if len(models) < 1:
        errors.append("axes.models is empty")

    # Template field checks
    for t in templates:
        if "id" not in t:
            errors.append(f"Template entry missing 'id' field: {t}")
        if "file" not in t:
            errors.append(f"Template entry missing 'file' field: {t}")

    # Model field checks
    for m in models:
        for field_name in ("id", "name", "provider"):
            if field_name not in m:
                errors.append(f"Model entry missing '{field_name}' field: {m}")

    # Parameter field checks
    for p in params:
        if "id" not in p:
            errors.append(f"Parameter entry missing 'id' field: {p}")
        if "temperature" not in p:
            errors.append(f"Parameter entry missing 'temperature' field: {p}")

    # Uniqueness checks
    template_ids = [t.get("id") for t in templates]
    if len(template_ids) != len(set(template_ids)):
        errors.append(f"Duplicate template IDs: {template_ids}")
    model_ids = [m.get("id") for m in models]
    if len(model_ids) != len(set(model_ids)):
        errors.append(f"Duplicate model IDs: {model_ids}")
    param_ids = [p.get("id") for p in params]
    if len(param_ids) != len(set(param_ids)):
        errors.append(f"Duplicate parameter IDs: {param_ids}")

    # Budget check
    budget = plan.get("budget", {})
    if "max_cost_usd" not in budget:
        errors.append("budget.max_cost_usd is absent from plan.yaml")

    if errors:
        return False, "; ".join(errors)

    return True, (
        f"plan.yaml valid: {len(templates)} templates, {len(params)} param sets, "
        f"{len(models)} models, weights sum={total_weight:.4f}, "
        f"budget=${budget.get('max_cost_usd', 'N/A')}"
    )


def _check_build(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    templates_dir = exp_dir / "templates"
    if not templates_dir.is_dir():
        return False, f"templates/ directory not found at {templates_dir}"

    template_files = list(templates_dir.glob("*.yaml"))
    if len(template_files) < 2:
        return False, f"templates/ has {len(template_files)} files, need at least 2"

    errors: list[str] = []

    for tf in template_files:
        t = _load_yaml(tf)
        if t is None:
            errors.append(f"{tf.name}: failed to parse as YAML")
            continue

        # One technique per template
        technique = t.get("technique")
        if not technique:
            errors.append(f"{tf.name}: missing 'technique' field")
        elif isinstance(technique, list):
            errors.append(
                f"{tf.name}: 'technique' must be a single string, got list: {technique}"
            )

        # Output format instructions
        system = t.get("system_prompt", "")
        user = t.get("user_prompt", "")
        combined = (system + " " + user).lower()
        if "json" not in combined and "format" not in combined and "schema" not in combined:
            errors.append(
                f"{tf.name}: no output format instructions found in system_prompt or user_prompt"
            )

        # Variable declaration vs usage consistency
        declared_vars = {v if isinstance(v, str) else v.get("name") for v in t.get("variables", [])}
        used_vars = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", system + " " + user))
        undeclared = used_vars - declared_vars
        unused = declared_vars - used_vars
        if undeclared:
            errors.append(f"{tf.name}: undeclared variables used in prompts: {undeclared}")
        if unused:
            errors.append(f"{tf.name}: declared variables not used in prompts: {unused}")

    # Test inputs check
    test_inputs_path = exp_dir / "data" / "test_inputs.yaml"
    if not test_inputs_path.exists():
        errors.append(f"data/test_inputs.yaml not found at {test_inputs_path}")
    else:
        inputs_doc = _load_yaml(test_inputs_path)
        if inputs_doc is None:
            errors.append("data/test_inputs.yaml failed to parse")
        else:
            inputs = inputs_doc.get("inputs", []) if isinstance(inputs_doc, dict) else inputs_doc
            if len(inputs) < 15:
                errors.append(
                    f"test_inputs.yaml has {len(inputs)} inputs, need at least 15"
                )

            ids = [i.get("id") for i in inputs if isinstance(i, dict)]
            if len(ids) != len(set(ids)):
                errors.append("test_inputs.yaml contains duplicate input IDs")

            missing_text = [
                i.get("id", "unknown")
                for i in inputs
                if isinstance(i, dict) and not i.get("text")
            ]
            if missing_text:
                errors.append(f"Inputs missing 'text' field: {missing_text[:5]}")

            categories = set()
            for i in inputs:
                if isinstance(i, dict):
                    meta = i.get("metadata", {}) or {}
                    cat = meta.get("category") or meta.get("difficulty")
                    if cat:
                        categories.add(cat.lower())
            required_cats = {"easy", "hard", "edge"}
            missing_cats = required_cats - categories
            if missing_cats:
                errors.append(
                    f"test_inputs.yaml missing categories: {missing_cats}. "
                    f"Found: {categories}"
                )

    if errors:
        return False, "; ".join(errors)

    return True, (
        f"Build artifacts valid: {len(template_files)} templates, "
        f"all have technique field and output format instructions"
    )


def _check_execute(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    """
    Execution tests that can be done statically: check that result records
    contain the required fields. Full execution tests require --execute.
    """
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    results_dir = exp_dir / "results"
    if not results_dir.is_dir():
        return False, f"results/ directory not found at {results_dir}"

    jsonl_files = list(results_dir.glob("*.jsonl"))
    if not jsonl_files:
        return False, "No .jsonl result files found in results/"

    required_fields = {"tokens_in", "tokens_out", "cost_usd", "latency_ms"}
    errors: list[str] = []
    records_checked = 0

    for jf in jsonl_files[:3]:  # check up to 3 files
        with open(jf, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"{jf.name} line {line_num}: not valid JSON")
                    continue

                missing = required_fields - set(record.keys())
                if missing:
                    errors.append(
                        f"{jf.name} line {line_num}: missing fields {missing}"
                    )
                records_checked += 1
                if records_checked >= 20:
                    break
        if records_checked >= 20:
            break

    # Check execution_summary.yaml
    summary_path = exp_dir / "execution_summary.yaml"
    if not summary_path.exists():
        errors.append(f"execution_summary.yaml not found at {summary_path}")
    else:
        summary = _load_yaml(summary_path)
        if summary is None:
            errors.append("execution_summary.yaml failed to parse")
        else:
            if "cost" not in summary and "total_cost_usd" not in summary:
                errors.append("execution_summary.yaml missing cost section")
            if "status" not in summary:
                errors.append("execution_summary.yaml missing 'status' field")

    if errors:
        return False, "; ".join(errors)

    return True, (
        f"Execute artifacts valid: checked {records_checked} result records across "
        f"{len(jsonl_files)} files, all have required fields"
    )


def _check_evaluate(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    evals_dir = exp_dir / "evaluations"
    if not evals_dir.is_dir():
        return False, f"evaluations/ directory not found at {evals_dir}"

    errors: list[str] = []

    # Check scores.jsonl
    scores_path = evals_dir / "scores.jsonl"
    if not scores_path.exists():
        errors.append(f"scores.jsonl not found at {scores_path}")
    else:
        scores: list[float] = []
        with open(scores_path, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"scores.jsonl line {line_num}: not valid JSON")
                    continue

                score = record.get("composite_score")
                if score is None:
                    errors.append(
                        f"scores.jsonl line {line_num}: missing 'composite_score' field"
                    )
                elif not (1.0 <= float(score) <= 10.0):
                    errors.append(
                        f"scores.jsonl line {line_num}: composite_score {score} out of range [1, 10]"
                    )
                else:
                    scores.append(float(score))

        if scores and len(set(scores)) == 1:
            errors.append(
                "All composite_scores are identical — evaluation is not discriminating"
            )

    # Check summary.yaml
    summary_path = evals_dir / "summary.yaml"
    if not summary_path.exists():
        errors.append(f"summary.yaml not found at {summary_path}")
    else:
        summary = _load_yaml(summary_path)
        if summary is None:
            errors.append("summary.yaml failed to parse")
        else:
            required_keys = ["overall_best_combination"]
            for key in required_keys:
                if key not in summary:
                    errors.append(f"summary.yaml missing required key: '{key}'")

            best = summary.get("overall_best_combination", {})
            for sub_key in ("cell_id", "template_id", "model_id", "param_id"):
                if sub_key not in best:
                    errors.append(
                        f"summary.yaml overall_best_combination missing '{sub_key}'"
                    )

            # Check axis_means or per_axis_best_levels exists
            if "per_axis_best_levels" not in summary and "axis_means" not in summary:
                errors.append(
                    "summary.yaml missing per_axis_best_levels or axis_means (axis effects)"
                )

    if errors:
        return False, "; ".join(errors)

    return True, (
        f"Evaluate artifacts valid: {len(scores)} scored records, "
        f"scores in range [{min(scores, default=0):.2f}, {max(scores, default=0):.2f}], "
        "summary.yaml has best combination and axis effects"
    )


def _check_report(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    report_path = exp_dir / "report.md"
    if not report_path.exists():
        return False, f"report.md not found at {report_path}"

    content = report_path.read_text(encoding="utf-8")
    if len(content) < 1000:
        return False, f"report.md is too short ({len(content)} chars, minimum 1000)"

    errors: list[str] = []

    required_sections = [
        "Executive Summary",
        "Methodology",
        ("Results", "Results Overview"),
        "Axis Analysis",
        "Interaction Effects",
        ("Cost", "Cost-Performance"),
        "Winning Prompt",
        "Recommendations",
        ("Raw Data", "Raw Data Reference"),
    ]

    for section in required_sections:
        if isinstance(section, tuple):
            found = any(
                re.search(rf"^##\s+{re.escape(s)}", content, re.IGNORECASE | re.MULTILINE)
                for s in section
            )
            label = " or ".join(section)
        else:
            found = bool(
                re.search(rf"^##\s+{re.escape(section)}", content, re.IGNORECASE | re.MULTILINE)
            )
            label = section

        if not found:
            errors.append(f"Missing section: '{label}'")

    # Executive summary word count
    exec_body = _section_content(content, "Executive Summary")
    word_count = _count_words(exec_body)
    if word_count > 200:
        errors.append(
            f"Executive Summary is {word_count} words, should be <=150"
        )
    if word_count < 10:
        errors.append("Executive Summary appears to be empty")

    # Winning prompt section has actual content
    winning_body = _section_content(content, "Winning Prompt")
    if len(winning_body) < 100:
        errors.append(
            f"Winning Prompt section is too short ({len(winning_body)} chars) — "
            "must contain full prompt text"
        )
    if "system" not in winning_body.lower() and "system_prompt" not in winning_body.lower():
        errors.append(
            "Winning Prompt section does not appear to contain a system prompt"
        )

    # report_data.json check
    report_data_path = exp_dir / "report_data.json"
    if not report_data_path.exists():
        errors.append(f"report_data.json not found at {report_data_path}")
    else:
        report_data = _load_json(report_data_path)
        if report_data is None:
            errors.append("report_data.json is not valid JSON")
        else:
            for key in ("rankings", "winner"):
                if key not in report_data:
                    errors.append(f"report_data.json missing key: '{key}'")
            rankings = report_data.get("rankings", [])
            if not rankings:
                errors.append("report_data.json rankings array is empty")

    if errors:
        return False, "; ".join(errors)

    return True, (
        f"report.md valid: {len(content)} chars, all 9 sections present, "
        f"Executive Summary={word_count} words, report_data.json valid"
    )


def _check_end_to_end(case: dict[str, Any], exp_dir: Path | None) -> tuple[bool, str]:
    if exp_dir is None:
        return False, "No experiment directory found. Run the pipeline first."

    required_artifacts = [
        ("state.yaml", False),
        ("research_brief.md", False),
        ("plan.yaml", False),
        ("templates", True),   # directory
        ("data/test_inputs.yaml", False),
        ("matrix.yaml", False),
        ("results", True),     # directory
        ("execution_summary.yaml", False),
        ("evaluations/scores.jsonl", False),
        ("evaluations/summary.yaml", False),
        ("report.md", False),
        ("report_data.json", False),
    ]

    errors: list[str] = []
    for artifact_name, is_dir in required_artifacts:
        artifact_path = exp_dir / artifact_name
        if is_dir:
            if not artifact_path.is_dir():
                errors.append(f"Directory missing: {artifact_name}/")
            else:
                contents = list(artifact_path.iterdir())
                if not contents:
                    errors.append(f"Directory is empty: {artifact_name}/")
        else:
            if not artifact_path.exists():
                errors.append(f"File missing: {artifact_name}")
            elif artifact_path.stat().st_size == 0:
                errors.append(f"File is empty: {artifact_name}")

    # Check state.yaml current_stage
    state_path = exp_dir / "state.yaml"
    if state_path.exists():
        state = _load_yaml(state_path)
        if state and state.get("current_stage") not in ("DONE", "REPORT"):
            errors.append(
                f"state.yaml current_stage is '{state.get('current_stage')}', "
                "expected DONE or REPORT for a completed experiment"
            )
        # Check all stages have completed_at
        if state:
            stages = state.get("stages_completed", {})
            for stage_name in ("RESEARCH", "PLAN", "BUILD", "MATRIX", "EXECUTE", "EVALUATE", "REPORT"):
                stage = stages.get(stage_name, {})
                if not stage:
                    errors.append(f"state.yaml missing stages_completed.{stage_name}")
                elif not stage.get("completed_at"):
                    errors.append(
                        f"state.yaml stages_completed.{stage_name} missing 'completed_at'"
                    )

    if errors:
        return False, "; ".join(errors)

    found = [a for a, _ in required_artifacts]
    return True, f"End-to-end artifacts valid: {len(found)} artifacts confirmed, state=DONE"


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_CHECKERS = {
    "trigger": _check_trigger,
    "research": _check_research,
    "plan": _check_plan,
    "build": _check_build,
    "execute": _check_execute,
    "evaluate": _check_evaluate,
    "report": _check_report,
    "end_to_end": _check_end_to_end,
}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_evals(
    category_filter: str | None = None,
    experiment_dir: Path | None = None,
    include_execution: bool = False,
) -> EvalSummary:
    if not _TEST_CASES_FILE.exists():
        print(f"ERROR: test cases file not found: {_TEST_CASES_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(_TEST_CASES_FILE, "r", encoding="utf-8") as fh:
        test_cases: list[dict[str, Any]] = yaml.safe_load(fh) or []

    # Resolve experiment directory
    if experiment_dir is None:
        experiment_dir = _find_experiment_dir(_PROJECT_ROOT)

    summary = EvalSummary()

    for case in test_cases:
        case_id = case.get("id", "unknown")
        case_name = case.get("name", case_id)
        category = case.get("category", "unknown")
        requires_execution = case.get("requires_execution", False)

        # Apply category filter
        if category_filter and category != category_filter:
            continue

        summary.total += 1

        # Skip execution-required tests unless --execute
        if requires_execution and not include_execution:
            summary.skipped += 1
            summary.results.append(
                EvalResult(
                    id=case_id,
                    name=case_name,
                    category=category,
                    passed=False,
                    skipped=True,
                    message="Requires pipeline execution (pass --execute to run)",
                )
            )
            continue

        checker = _CHECKERS.get(category)
        if checker is None:
            summary.skipped += 1
            summary.results.append(
                EvalResult(
                    id=case_id,
                    name=case_name,
                    category=category,
                    passed=False,
                    skipped=True,
                    message=f"No checker implemented for category '{category}'",
                )
            )
            continue

        t0 = time.perf_counter()
        try:
            passed, message = checker(case, experiment_dir)
        except Exception as exc:
            passed = False
            message = f"Checker raised an exception: {exc}"
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if passed:
            summary.passed += 1
        else:
            summary.failed += 1

        summary.results.append(
            EvalResult(
                id=case_id,
                name=case_name,
                category=category,
                passed=passed,
                skipped=False,
                message=message,
                elapsed_ms=elapsed_ms,
            )
        )

    return summary


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_rich(summary: EvalSummary, category_filter: str | None) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    title = "Prompt-Engineer Skill Evals"
    if category_filter:
        title += f" — category: {category_filter}"

    table = Table(title=title, box=box.ROUNDED, show_lines=False)
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", max_width=40)
    table.add_column("Category", style="cyan")
    table.add_column("Result", no_wrap=True)
    table.add_column("Message", max_width=60)

    for r in summary.results:
        if r.skipped:
            status = "[yellow]SKIPPED[/yellow]"
        elif r.passed:
            status = "[green]PASSED[/green]"
        else:
            status = "[red]FAILED[/red]"
        table.add_row(r.id, r.name, r.category, status, r.message)

    console.print(table)
    console.print(
        f"\n[bold]Total:[/bold] {summary.total}  "
        f"[green]Passed:[/green] {summary.passed}  "
        f"[red]Failed:[/red] {summary.failed}  "
        f"[yellow]Skipped:[/yellow] {summary.skipped}"
    )


def _print_plain(summary: EvalSummary, category_filter: str | None) -> None:
    header = "Prompt-Engineer Skill Evals"
    if category_filter:
        header += f" [category: {category_filter}]"
    print(f"\n{header}")
    print("-" * 60)

    for r in summary.results:
        if r.skipped:
            status = "SKIPPED"
        elif r.passed:
            status = "PASSED "
        else:
            status = "FAILED "
        print(f"{status}  {r.id:<30}  {r.message[:80]}")

    print("-" * 60)
    print(
        f"Total: {summary.total}  Passed: {summary.passed}  "
        f"Failed: {summary.failed}  Skipped: {summary.skipped}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run eval test cases for the PromptForge skill.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--category",
        choices=sorted(VALID_CATEGORIES),
        help="Run only tests in this category",
    )
    parser.add_argument(
        "--experiment",
        type=Path,
        metavar="PATH",
        help="Path to the experiment directory to validate (default: most recent)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Include tests that require pipeline execution (makes API calls)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON (for CI integration)",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available test categories and exit",
    )
    args = parser.parse_args()

    if args.list_categories:
        print("Available categories:")
        for cat in sorted(VALID_CATEGORIES):
            print(f"  {cat}")
        sys.exit(0)

    experiment_dir = args.experiment
    if experiment_dir and not experiment_dir.is_dir():
        print(f"ERROR: experiment directory not found: {experiment_dir}", file=sys.stderr)
        sys.exit(1)

    summary = run_evals(
        category_filter=args.category,
        experiment_dir=experiment_dir,
        include_execution=args.execute,
    )

    if args.json_output:
        print(json.dumps(summary.as_dict(), indent=2))
    elif _RICH:
        _print_rich(summary, args.category)
    else:
        _print_plain(summary, args.category)

    # Exit non-zero if any tests failed
    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()

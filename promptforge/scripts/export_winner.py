"""Winner export — extracts top-scoring prompt(s) into a standalone YAML/JSON.

Usage:
    python scripts/export_winner.py --experiment experiments/{id}/
    python scripts/export_winner.py --experiment experiments/{id}/ --top 3
    python scripts/export_winner.py --experiment experiments/{id}/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.config import load_yaml, save_yaml  # noqa: E402
from scripts.utils.templates import load_template  # noqa: E402

console = Console()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class WinnerRecord:
    """Self-contained, production-ready description of a winning prompt.

    Attributes:
        rank: Position in the ranking (1 = best).
        template_id: ID slug of the winning template.
        model: Full model name string (e.g. ``"claude-sonnet-4-20250514"``).
        provider: API provider (e.g. ``"anthropic"``).
        parameters: Dict of inference hyper-parameters.
        composite_score: Mean composite score from evaluations.
        system_prompt: Fully rendered (static) system prompt text.
        user_prompt: User prompt text (may contain Jinja2 ``{{ var }}`` for
            run-time substitution).
        variables: List of variable descriptor dicts.
        param_id: Parameter set ID from plan.yaml.
        model_id: Model ID slug from plan.yaml.
        cell_id: Evaluation matrix cell identifier.
        exported_at: ISO-8601 UTC timestamp of export.
    """

    rank: int
    template_id: str
    model: str
    provider: str
    parameters: dict[str, Any]
    composite_score: float
    system_prompt: str
    user_prompt: str
    variables: list[dict[str, Any]]
    param_id: str
    model_id: str
    cell_id: str
    exported_at: str


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------


def _load_summary(experiment_dir: Path) -> dict[str, Any]:
    """Load evaluations/summary.yaml.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Parsed summary dict.

    Raises:
        FileNotFoundError: If summary.yaml does not exist.
    """
    summary_path = experiment_dir / "evaluations" / "summary.yaml"
    if not summary_path.exists():
        raise FileNotFoundError(f"Summary file not found: {summary_path}")
    return load_yaml(summary_path)


def _load_plan(experiment_dir: Path) -> dict[str, Any]:
    """Load plan.yaml.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Parsed plan dict.

    Raises:
        FileNotFoundError: If plan.yaml does not exist.
    """
    plan_path = experiment_dir / "plan.yaml"
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    return load_yaml(plan_path)


def _resolve_template_path(
    experiment_dir: Path,
    template_id: str,
    plan_raw: dict[str, Any],
) -> Path:
    """Find the YAML file for *template_id* using plan.yaml mappings.

    Falls back to globbing templates/ when no explicit mapping is found.

    Args:
        experiment_dir: Experiment root directory.
        template_id: Template ID to locate.
        plan_raw: Parsed plan.yaml dict.

    Returns:
        Path to the template YAML file.

    Raises:
        FileNotFoundError: If no file can be found.
    """
    for ref in plan_raw.get("axes", {}).get("templates", []):
        if isinstance(ref, dict) and ref.get("id") == template_id:
            candidate = experiment_dir / ref["file"]
            if candidate.exists():
                return candidate

    # Fallback: scan templates/ by id field
    template_dir = experiment_dir / "templates"
    if template_dir.is_dir():
        for yaml_path in sorted(template_dir.glob("*.yaml")):
            try:
                raw = load_yaml(yaml_path)
                if raw.get("id") == template_id:
                    return yaml_path
            except Exception:  # noqa: BLE001
                continue

    raise FileNotFoundError(
        f"No template file found for id '{template_id}' in {experiment_dir}"
    )


def _resolve_model_info(
    model_id: str,
    plan_raw: dict[str, Any],
) -> dict[str, Any]:
    """Look up model name and provider from plan.yaml.

    Args:
        model_id: The ``id`` field of the model in plan.yaml axes.
        plan_raw: Parsed plan.yaml dict.

    Returns:
        Dict with at least ``name`` and ``provider`` keys.
    """
    for model in plan_raw.get("axes", {}).get("models", []):
        if isinstance(model, dict) and model.get("id") == model_id:
            return model
    return {"id": model_id, "name": model_id, "provider": "unknown"}


def _resolve_param_set(
    param_id: str,
    plan_raw: dict[str, Any],
) -> dict[str, Any]:
    """Look up parameter values from plan.yaml.

    Args:
        param_id: The ``id`` field of the parameter set.
        plan_raw: Parsed plan.yaml dict.

    Returns:
        Dict of parameter key/value pairs (without the ``id`` key).
    """
    for param_set in plan_raw.get("axes", {}).get("parameters", []):
        if isinstance(param_set, dict) and param_set.get("id") == param_id:
            return {k: v for k, v in param_set.items() if k != "id"}
    return {}


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def _extract_top_cells(
    summary: dict[str, Any],
    top_n: int,
) -> list[dict[str, Any]]:
    """Return the top *top_n* cell records from the summary.

    Prefers the ``top_10_cells`` list; falls back to
    ``overall_best_combination`` for the single winner case.

    Args:
        summary: Parsed evaluations/summary.yaml.
        top_n: Number of top cells to return.

    Returns:
        List of cell dicts, each with at least ``cell_id``, ``template_id``,
        ``model_id``, ``param_id``, and a score field.
    """
    top_cells: list[dict[str, Any]] = summary.get("top_10_cells", [])

    if top_cells:
        # Already sorted by rank in the summary
        return top_cells[:top_n]

    # Fallback: use overall_best_combination
    best = summary.get("overall_best_combination")
    if best:
        return [best]

    return []


def build_winner_records(
    experiment_dir: Path,
    top_n: int = 1,
) -> list[WinnerRecord]:
    """Build :class:`WinnerRecord` objects for the top *top_n* cells.

    Args:
        experiment_dir: Experiment root directory.
        top_n: Number of winners to extract (default 1).

    Returns:
        List of :class:`WinnerRecord`, ordered best-first.

    Raises:
        FileNotFoundError: If required experiment files are missing.
        ValueError: If the summary contains no evaluable cells.
    """
    summary = _load_summary(experiment_dir)
    plan_raw = _load_plan(experiment_dir)

    top_cells = _extract_top_cells(summary, top_n)
    if not top_cells:
        raise ValueError(
            "No evaluated cells found in evaluations/summary.yaml. "
            "Run the evaluation step first."
        )

    now_iso = datetime.now(tz=timezone.utc).isoformat()
    records: list[WinnerRecord] = []

    for rank_idx, cell in enumerate(top_cells, start=1):
        template_id: str = cell.get("template_id", "")
        model_id: str = cell.get("model_id", "")
        param_id: str = cell.get("param_id", "")
        cell_id: str = cell.get("cell_id", "")

        # Composite score — handle varying key names
        score: float = float(
            cell.get("mean_composite_score")
            or cell.get("mean_composite")
            or cell.get("composite_score")
            or 0.0
        )

        # Resolve model info
        model_info = _resolve_model_info(model_id, plan_raw)
        model_name: str = model_info.get("name", model_id)
        provider: str = model_info.get("provider", "unknown")

        # Resolve parameters
        parameters = _resolve_param_set(param_id, plan_raw)

        # Load template
        try:
            tmpl_path = _resolve_template_path(experiment_dir, template_id, plan_raw)
            template = load_template(tmpl_path)
        except FileNotFoundError as exc:
            console.print(f"[yellow]WARNING:[/] {exc} — skipping rank {rank_idx}")
            continue

        # Build variable descriptors from declared variables list
        variable_descriptors: list[dict[str, Any]] = [
            {"name": var, "description": ""} for var in template.variables
        ]

        records.append(
            WinnerRecord(
                rank=rank_idx,
                template_id=template_id,
                model=model_name,
                provider=provider,
                parameters=parameters,
                composite_score=round(score, 4),
                system_prompt=template.system_prompt,
                user_prompt=template.user_prompt,
                variables=variable_descriptors,
                param_id=param_id,
                model_id=model_id,
                cell_id=cell_id,
                exported_at=now_iso,
            )
        )

    return records


# ---------------------------------------------------------------------------
# File serialisation helpers
# ---------------------------------------------------------------------------


def _record_to_dict(record: WinnerRecord) -> dict[str, Any]:
    """Convert a :class:`WinnerRecord` to a plain dict for serialisation."""
    return {
        "rank": record.rank,
        "template_id": record.template_id,
        "model": record.model,
        "provider": record.provider,
        "parameters": record.parameters,
        "composite_score": record.composite_score,
        "system_prompt": record.system_prompt,
        "user_prompt": record.user_prompt,
        "variables": record.variables,
        # Metadata
        "cell_id": record.cell_id,
        "param_id": record.param_id,
        "model_id": record.model_id,
        "exported_at": record.exported_at,
    }


def _write_winner_files(
    experiment_dir: Path,
    records: list[WinnerRecord],
    top_n: int,
) -> tuple[Path, Path]:
    """Write winner.yaml and winner.json (or winner_top{N}.yaml/.json).

    Args:
        experiment_dir: Experiment root directory.
        records: Ordered list of winner records.
        top_n: Total number requested — used to decide on filename suffix.

    Returns:
        Tuple of (yaml_path, json_path).
    """
    suffix = "" if top_n == 1 else f"_top{top_n}"
    yaml_path = experiment_dir / f"winner{suffix}.yaml"
    json_path = experiment_dir / f"winner{suffix}.json"

    dicts = [_record_to_dict(r) for r in records]

    # YAML: single winner uses a flat mapping; multiple use a list
    yaml_data: Any = dicts[0] if len(dicts) == 1 else dicts
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    with open(json_path, "w") as f:
        json.dump(dicts[0] if len(dicts) == 1 else dicts, f, indent=2, ensure_ascii=False)

    return yaml_path, json_path


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def _print_rich_summary(records: list[WinnerRecord], yaml_path: Path, json_path: Path) -> None:
    """Display a summary table of exported winners."""
    console.print()
    table = Table(title="Exported Winner(s)", show_header=True, header_style="bold cyan")
    table.add_column("Rank", justify="center", width=5)
    table.add_column("Cell ID", style="dim")
    table.add_column("Template ID")
    table.add_column("Model")
    table.add_column("Params")
    table.add_column("Score", justify="right")

    for r in records:
        table.add_row(
            str(r.rank),
            r.cell_id,
            r.template_id,
            r.model,
            r.param_id,
            f"[bold green]{r.composite_score:.4f}[/]",
        )

    console.print(table)
    console.print(f"\n[bold]YAML:[/] {yaml_path}")
    console.print(f"[bold]JSON:[/] {json_path}\n")


def _print_json_summary(records: list[WinnerRecord]) -> None:
    """Print exported winner data as JSON to stdout."""
    dicts = [_record_to_dict(r) for r in records]
    print(json.dumps(dicts[0] if len(dicts) == 1 else dicts, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_winner",
        description="Extract the winning prompt(s) from evaluation results.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        metavar="DIR",
        help="Path to the experiment directory.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=1,
        metavar="N",
        help="Export the top N winners (default: 1).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print the exported data as JSON to stdout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 on success, 1 on error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.top < 1:
        parser.error("--top N must be >= 1")

    experiment_dir = Path(args.experiment)
    if not experiment_dir.exists():
        console.print(f"[red]ERROR:[/] Directory not found: {experiment_dir}")
        return 1

    try:
        records = build_winner_records(experiment_dir, top_n=args.top)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        return 1

    if not records:
        console.print("[red]ERROR:[/] No winner records could be built.")
        return 1

    try:
        yaml_path, json_path = _write_winner_files(experiment_dir, records, args.top)
    except OSError as exc:
        console.print(f"[red]ERROR:[/] Could not write output files: {exc}")
        return 1

    if args.output_json:
        _print_json_summary(records)
    else:
        _print_rich_summary(records, yaml_path, json_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())

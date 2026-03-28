"""End-to-end pipeline runner — chains all prompt engineering stages with one command.

Usage:
    python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/
    python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/ --dry-run
    python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/ --from evaluate
    python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/ --clean
    python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/ --resume

Pipeline stages (in order):
    VALIDATE  -> validate_experiment()
    MATRIX    -> generate_matrix()
    EXECUTE   -> run_experiment()      [async]
    EVALUATE  -> evaluate_experiment() [async]
    REPORT    -> build_report_data() + build_markdown_report() (skipped if unavailable)
    EXPORT    -> build_winner_records() (skipped if unavailable)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# sys.path bootstrap — must run before any project-local import
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.rule import Rule  # noqa: E402
from rich.table import Table  # noqa: E402

from scripts.utils.config import load_yaml, save_yaml  # noqa: E402

console = Console()

# ---------------------------------------------------------------------------
# Stage ordering
# ---------------------------------------------------------------------------

STAGES: list[str] = ["VALIDATE", "MATRIX", "EXECUTE", "EVALUATE", "REPORT", "EXPORT"]
CRITICAL_STAGES: frozenset[str] = frozenset({"VALIDATE", "MATRIX", "EXECUTE", "EVALUATE"})


# ---------------------------------------------------------------------------
# Resilient module imports
# ---------------------------------------------------------------------------


def _import_critical(module_path: str, symbol: str) -> Any:
    """Import *symbol* from *module_path*, raising ImportError on failure.

    Used for critical stages where a missing import is a hard error.

    Args:
        module_path: Dotted module path (e.g. ``"scripts.validate"``).
        symbol: Name of the callable to import.

    Returns:
        The imported callable.

    Raises:
        ImportError: If the module or symbol cannot be imported.
    """
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, symbol)


def _import_optional(module_path: str, symbol: str) -> Any | None:
    """Import *symbol* from *module_path*, returning None on any failure.

    Used for optional stages (REPORT, EXPORT) where missing dependencies are
    non-fatal — the stage is simply skipped with a warning.

    Args:
        module_path: Dotted module path.
        symbol: Name of the callable to import.

    Returns:
        The imported callable, or ``None`` if import fails.
    """
    import importlib

    try:
        module = importlib.import_module(module_path)
        return getattr(module, symbol)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]WARNING: Could not import {module_path}.{symbol}: {exc}[/]")
        return None


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _load_state(experiment_dir: Path) -> dict[str, Any]:
    """Load state.yaml from *experiment_dir*, returning an empty dict if absent.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Parsed state dict (may be empty for a fresh run).
    """
    state_path = experiment_dir / "state.yaml"
    if state_path.exists():
        return load_yaml(state_path)
    return {}


def _save_state(experiment_dir: Path, state: dict[str, Any]) -> None:
    """Persist *state* to state.yaml atomically (overwrite).

    Args:
        experiment_dir: Experiment root directory.
        state: State dict to write.
    """
    state_path = experiment_dir / "state.yaml"
    save_yaml(state_path, state)


def _mark_stage_completed(
    experiment_dir: Path,
    state: dict[str, Any],
    stage: str,
) -> None:
    """Record a stage as completed in *state* and write state.yaml.

    Args:
        experiment_dir: Experiment root directory.
        state: Mutable state dict (modified in place).
        stage: Stage name (e.g. ``"VALIDATE"``).
    """
    stages_completed: dict[str, Any] = state.setdefault("stages_completed", {})
    stages_completed[stage] = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
    }
    state["current_stage"] = stage
    _save_state(experiment_dir, state)


def _mark_stage_failed(
    experiment_dir: Path,
    state: dict[str, Any],
    stage: str,
    error: str,
) -> None:
    """Record a stage as failed in *state* and write state.yaml.

    Args:
        experiment_dir: Experiment root directory.
        state: Mutable state dict (modified in place).
        stage: Stage name.
        error: Short error description to persist.
    """
    stages_completed: dict[str, Any] = state.setdefault("stages_completed", {})
    stages_completed[stage] = {
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "error": error,
    }
    state["current_stage"] = stage
    _save_state(experiment_dir, state)


def _stage_is_completed(state: dict[str, Any], stage: str) -> bool:
    """Return True if *stage* is marked completed in *state*.

    Args:
        state: Parsed state dict.
        stage: Stage name to check.

    Returns:
        True when the stage has a ``"completed"`` status entry.
    """
    entry = state.get("stages_completed", {}).get(stage, {})
    return entry.get("status") == "completed"


# ---------------------------------------------------------------------------
# Clean helpers
# ---------------------------------------------------------------------------


def _clean_experiment(experiment_dir: Path) -> None:
    """Remove regenerable artefacts so the pipeline runs from scratch.

    Deletes: matrix.yaml, results/, evaluations/, execution_summary.yaml,
    report_data.json, report.md, winner*.yaml, winner*.json, state.yaml.

    Args:
        experiment_dir: Experiment root directory.
    """
    targets: list[Path] = [
        experiment_dir / "matrix.yaml",
        experiment_dir / "execution_summary.yaml",
        experiment_dir / "report_data.json",
        experiment_dir / "report.md",
        experiment_dir / "state.yaml",
    ]
    # Glob-based removals
    targets.extend(experiment_dir.glob("winner*.yaml"))
    targets.extend(experiment_dir.glob("winner*.json"))

    dirs: list[Path] = [
        experiment_dir / "results",
        experiment_dir / "evaluations",
    ]

    removed: list[str] = []
    for path in targets:
        if path.exists():
            path.unlink()
            removed.append(path.name)

    for directory in dirs:
        if directory.exists():
            shutil.rmtree(directory)
            removed.append(f"{directory.name}/")

    if removed:
        console.print(f"[yellow]Cleaned:[/] {', '.join(removed)}")
    else:
        console.print("[yellow]Nothing to clean.[/]")


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


def _run_validate(experiment_dir: Path) -> None:
    """Run the VALIDATE stage.

    Args:
        experiment_dir: Experiment root directory.

    Raises:
        ImportError: If the validate module cannot be imported.
        RuntimeError: If validation checks fail.
    """
    validate_experiment = _import_critical("scripts.validate", "validate_experiment")
    report = validate_experiment(experiment_dir)
    if not report.valid:
        raise RuntimeError(
            f"Validation failed — {sum(1 for c in report.checks if not c.passed)} "
            f"check(s) did not pass. Fix the issues above and re-run."
        )


def _run_matrix(
    experiment_dir: Path,
    force_matrix: bool,
    dry_run: bool,
) -> None:
    """Run the MATRIX stage.

    Args:
        experiment_dir: Experiment root directory.
        force_matrix: When True, regenerate matrix.yaml even if it exists.
        dry_run: When True, pass dry_run=True to generate_matrix() so no
            file is written.

    Raises:
        ImportError: If the generate_matrix module cannot be imported.
    """
    generate_matrix = _import_critical("scripts.generate_matrix", "generate_matrix")

    matrix_path = experiment_dir / "matrix.yaml"
    if matrix_path.exists() and not force_matrix and not dry_run:
        console.print(
            f"  [dim]matrix.yaml already exists — skipping generation "
            f"(use --force-matrix to regenerate)[/]"
        )
        return

    generate_matrix(experiment_dir, strategy_override=None, dry_run=dry_run)


async def _run_execute(experiment_dir: Path) -> dict[str, Any]:
    """Run the EXECUTE stage asynchronously.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Execution summary dict from run_experiment().

    Raises:
        ImportError: If the run_experiment module cannot be imported.
    """
    run_experiment = _import_critical("scripts.run_experiment", "run_experiment")
    return await run_experiment(experiment_dir)


async def _run_evaluate(experiment_dir: Path) -> None:
    """Run the EVALUATE stage asynchronously.

    Args:
        experiment_dir: Experiment root directory.

    Raises:
        ImportError: If the evaluate module cannot be imported.
    """
    evaluate_experiment = _import_critical("scripts.evaluate", "evaluate_experiment")
    await evaluate_experiment(experiment_dir)


def _run_report(experiment_dir: Path) -> bool:
    """Run the REPORT stage, skipping gracefully if unavailable.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        True if the stage ran successfully, False if skipped or failed.
    """
    build_report_data = _import_optional("scripts.generate_report", "build_report_data")
    build_markdown_report = _import_optional(
        "scripts.generate_report", "build_markdown_report"
    )
    write_report_files = _import_optional(
        "scripts.generate_report", "_write_report_files"
    )

    if build_report_data is None or build_markdown_report is None:
        console.print("  [dim]REPORT stage skipped — generate_report unavailable.[/]")
        return False

    try:
        report_data = build_report_data(experiment_dir)
        markdown = build_markdown_report(report_data)
        if write_report_files is not None:
            write_report_files(experiment_dir, report_data, markdown)
        else:
            # Fallback: write manually
            json_path = experiment_dir / "report_data.json"
            md_path = experiment_dir / "report.md"
            with open(json_path, "w") as fh:
                json.dump(report_data, fh, indent=2, ensure_ascii=False, default=str)
            md_path.write_text(markdown, encoding="utf-8")
        return True
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [yellow]REPORT stage warning: {exc}[/]")
        return False


def _run_export(experiment_dir: Path) -> bool:
    """Run the EXPORT stage, skipping gracefully if unavailable.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        True if the stage ran successfully, False if skipped or failed.
    """
    build_winner_records = _import_optional(
        "scripts.export_winner", "build_winner_records"
    )
    write_winner_files = _import_optional(
        "scripts.export_winner", "_write_winner_files"
    )

    if build_winner_records is None:
        console.print("  [dim]EXPORT stage skipped — export_winner unavailable.[/]")
        return False

    try:
        records = build_winner_records(experiment_dir, top_n=1)
        if not records:
            console.print("  [yellow]EXPORT: no winner records built (evaluation may be empty).[/]")
            return False
        if write_winner_files is not None:
            write_winner_files(experiment_dir, records, top_n=1)
        return True
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"  [yellow]EXPORT stage skipped: {exc}[/]")
        return False
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [yellow]EXPORT stage warning: {exc}[/]")
        return False


# ---------------------------------------------------------------------------
# Stage header / footer rendering
# ---------------------------------------------------------------------------


def _stage_header(stage: str, index: int, total: int) -> None:
    """Print a rich rule header for a pipeline stage.

    Args:
        stage: Stage name.
        index: 1-based position in the pipeline.
        total: Total number of stages being run.
    """
    console.print()
    console.rule(
        f"[bold cyan]Stage {index}/{total}: {stage}[/]",
        style="cyan",
    )


def _stage_footer(stage: str, elapsed: float, skipped: bool = False) -> None:
    """Print a completion line for a stage.

    Args:
        stage: Stage name.
        elapsed: Wall-clock seconds the stage took.
        skipped: When True, mark as skipped rather than completed.
    """
    if skipped:
        console.print(f"  [dim]{stage} skipped[/]  ({elapsed:.1f}s)")
    else:
        console.print(
            f"  [bold green]DONE[/] {stage}  ({elapsed:.1f}s)"
        )


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------


def _print_final_summary(
    experiment_dir: Path,
    stages_run: list[str],
    stage_times: dict[str, float],
    total_elapsed: float,
    output_json: bool,
) -> None:
    """Print the pipeline completion summary.

    Reads execution_summary.yaml for cost data if available.

    Args:
        experiment_dir: Experiment root directory.
        stages_run: Ordered list of stages that were attempted.
        stage_times: Mapping of stage name -> wall-clock seconds.
        total_elapsed: Total wall-clock seconds for the entire pipeline.
        output_json: When True, print a JSON summary to stdout instead of
            the rich table.
    """
    # Try to load cost from execution_summary.yaml
    total_cost: float | None = None
    exec_summary_path = experiment_dir / "execution_summary.yaml"
    if exec_summary_path.exists():
        try:
            exec_summary = load_yaml(exec_summary_path)
            total_cost = exec_summary.get("total_cost_usd")
        except Exception:  # noqa: BLE001
            pass

    state = _load_state(experiment_dir)
    stages_completed_map: dict[str, Any] = state.get("stages_completed", {})

    if output_json:
        payload: dict[str, Any] = {
            "experiment_dir": str(experiment_dir),
            "stages_run": stages_run,
            "stage_times_seconds": {s: round(t, 2) for s, t in stage_times.items()},
            "total_elapsed_seconds": round(total_elapsed, 2),
            "total_cost_usd": total_cost,
            "stages_status": {
                s: stages_completed_map.get(s, {}).get("status", "not_run")
                for s in stages_run
            },
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    console.print()
    console.rule("[bold green]Pipeline Complete[/]", style="green")
    console.print()

    table = Table(title="Pipeline Summary", show_header=True, header_style="bold")
    table.add_column("Stage", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Time", justify="right")

    for stage in stages_run:
        status_entry = stages_completed_map.get(stage, {})
        status = status_entry.get("status", "skipped")
        elapsed_s = stage_times.get(stage, 0.0)

        if status == "completed":
            status_cell = "[green]completed[/]"
        elif status == "failed":
            status_cell = "[red]FAILED[/]"
        else:
            status_cell = "[dim]skipped[/]"

        table.add_row(stage, status_cell, f"{elapsed_s:.1f}s")

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/]",
        "",
        f"[bold]{total_elapsed:.1f}s[/]",
    )

    console.print(table)

    if total_cost is not None:
        console.print(f"\n[bold]Total cost:[/] ${total_cost:.4f} USD")

    console.print()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description=(
            "End-to-end prompt engineering pipeline runner. "
            "Chains VALIDATE -> MATRIX -> EXECUTE -> EVALUATE -> REPORT -> EXPORT."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.run_pipeline --experiment experiments/2026-03-25-keyword-extraction/
  python -m scripts.run_pipeline --experiment experiments/... --dry-run
  python -m scripts.run_pipeline --experiment experiments/... --from evaluate
  python -m scripts.run_pipeline --experiment experiments/... --resume
  python -m scripts.run_pipeline --experiment experiments/... --clean
        """,
    )
    parser.add_argument(
        "--experiment",
        required=True,
        metavar="DIR",
        help="Path to the experiment directory (must contain plan.yaml).",
    )
    parser.add_argument(
        "--from",
        dest="from_stage",
        metavar="STAGE",
        choices=STAGES,
        help=(
            "Start pipeline from this stage, skipping earlier ones. "
            "Choices: " + ", ".join(STAGES)
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Skip stages already marked completed in state.yaml.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Run VALIDATE and MATRIX only (with cost preview). "
            "Does not execute API calls or write results."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help=(
            "Delete matrix.yaml, results/, evaluations/, execution_summary.yaml, "
            "and state.yaml before running."
        ),
    )
    parser.add_argument(
        "--force-matrix",
        action="store_true",
        default=False,
        help="Regenerate matrix.yaml even if it already exists.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        default=False,
        help="Output the final pipeline summary as JSON to stdout.",
    )
    return parser


# ---------------------------------------------------------------------------
# Main pipeline orchestrator
# ---------------------------------------------------------------------------


async def _run_pipeline_async(
    experiment_dir: Path,
    from_stage: str | None,
    resume: bool,
    dry_run: bool,
    force_matrix: bool,
    output_json: bool,
) -> int:
    """Async pipeline orchestrator.

    Args:
        experiment_dir: Resolved path to the experiment directory.
        from_stage: If set, skip all stages before this one.
        resume: When True, skip stages already marked completed in state.yaml.
        dry_run: When True, stop after MATRIX without executing.
        force_matrix: When True, regenerate matrix.yaml unconditionally.
        output_json: When True, emit JSON summary at the end.

    Returns:
        Exit code: 0 on success, 1 on any stage failure.
    """
    # Determine which stages to run
    if dry_run:
        active_stages = ["VALIDATE", "MATRIX"]
    elif from_stage is not None:
        start_index = STAGES.index(from_stage)
        active_stages = STAGES[start_index:]
    else:
        active_stages = list(STAGES)

    state = _load_state(experiment_dir)

    # Initialise experiment_id in state if absent
    if "experiment_id" not in state:
        state["experiment_id"] = experiment_dir.name
        _save_state(experiment_dir, state)

    total_stages = len(active_stages)
    stage_times: dict[str, float] = {}
    pipeline_start = time.monotonic()

    console.print()
    console.print(
        Panel.fit(
            f"[bold]Experiment:[/] {experiment_dir}\n"
            f"[bold]Stages:    [/] {' -> '.join(active_stages)}"
            + (" [dim](dry-run)[/]" if dry_run else ""),
            title="[bold cyan]PromptForge Pipeline[/]",
            border_style="cyan",
        )
    )

    for stage_index, stage in enumerate(active_stages, start=1):
        # --resume: skip already-completed stages
        if resume and _stage_is_completed(state, stage):
            t0 = time.monotonic()
            _stage_header(stage, stage_index, total_stages)
            console.print(f"  [dim]Skipping — already completed (--resume)[/]")
            elapsed = time.monotonic() - t0
            stage_times[stage] = elapsed
            _stage_footer(stage, elapsed, skipped=True)
            continue

        _stage_header(stage, stage_index, total_stages)
        t0 = time.monotonic()

        try:
            if stage == "VALIDATE":
                _run_validate(experiment_dir)

            elif stage == "MATRIX":
                _run_matrix(experiment_dir, force_matrix=force_matrix, dry_run=dry_run)

            elif stage == "EXECUTE":
                await _run_execute(experiment_dir)

            elif stage == "EVALUATE":
                await _run_evaluate(experiment_dir)

            elif stage == "REPORT":
                success = _run_report(experiment_dir)
                elapsed = time.monotonic() - t0
                stage_times[stage] = elapsed
                if success:
                    _mark_stage_completed(experiment_dir, state, stage)
                _stage_footer(stage, elapsed, skipped=not success)
                continue  # skip the generic footer below

            elif stage == "EXPORT":
                success = _run_export(experiment_dir)
                elapsed = time.monotonic() - t0
                stage_times[stage] = elapsed
                if success:
                    _mark_stage_completed(experiment_dir, state, stage)
                _stage_footer(stage, elapsed, skipped=not success)
                continue  # skip the generic footer below

        except (ImportError, RuntimeError, FileNotFoundError, ValueError) as exc:
            elapsed = time.monotonic() - t0
            stage_times[stage] = elapsed

            error_msg = str(exc)
            console.print(f"\n[bold red]ERROR in {stage}:[/] {error_msg}")

            _mark_stage_failed(experiment_dir, state, stage, error_msg)

            total_elapsed = time.monotonic() - pipeline_start
            _print_final_summary(
                experiment_dir,
                active_stages,
                stage_times,
                total_elapsed,
                output_json,
            )
            console.print(
                f"[bold red]Pipeline aborted at {stage}.[/] "
                f"Fix the issue and re-run with [bold]--resume[/] or [bold]--from {stage}[/]."
            )
            return 1

        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            stage_times[stage] = elapsed

            error_msg = f"{type(exc).__name__}: {exc}"
            console.print(f"\n[bold red]UNEXPECTED ERROR in {stage}:[/] {error_msg}")

            _mark_stage_failed(experiment_dir, state, stage, error_msg)

            total_elapsed = time.monotonic() - pipeline_start
            _print_final_summary(
                experiment_dir,
                active_stages,
                stage_times,
                total_elapsed,
                output_json,
            )
            console.print(
                f"[bold red]Pipeline aborted at {stage}.[/] "
                f"Re-run with [bold]--resume[/] or [bold]--from {stage}[/] after fixing the issue."
            )
            return 1

        elapsed = time.monotonic() - t0
        stage_times[stage] = elapsed

        # Mark non-dry-run MATRIX and VALIDATE as completed even though their
        # own modules write state.yaml in their own format — we normalise here.
        _mark_stage_completed(experiment_dir, state, stage)
        _stage_footer(stage, elapsed)

    total_elapsed = time.monotonic() - pipeline_start
    _print_final_summary(
        experiment_dir,
        active_stages,
        stage_times,
        total_elapsed,
        output_json,
    )

    if dry_run:
        console.print(
            "[bold yellow]Dry-run complete.[/] "
            "Re-run without [bold]--dry-run[/] to execute the full pipeline."
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    experiment_dir = Path(args.experiment).resolve()

    if not experiment_dir.exists():
        console.print(f"[bold red]ERROR:[/] Experiment directory not found: {experiment_dir}")
        return 1

    if not (experiment_dir / "plan.yaml").exists():
        console.print(
            f"[bold red]ERROR:[/] No plan.yaml found in {experiment_dir}. "
            "Is this a valid experiment directory?"
        )
        return 1

    # --clean: wipe regenerable artefacts before starting
    if args.clean:
        console.print()
        console.rule("[yellow]Cleaning experiment artefacts[/]", style="yellow")
        _clean_experiment(experiment_dir)

    try:
        return asyncio.run(
            _run_pipeline_async(
                experiment_dir=experiment_dir,
                from_stage=args.from_stage,
                resume=args.resume,
                dry_run=args.dry_run,
                force_matrix=args.force_matrix,
                output_json=args.output_json,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/]")
        return 130


if __name__ == "__main__":
    sys.exit(main())

"""Async experiment runner — EXECUTE stage of the prompt engineering pipeline.

Usage:
    python scripts/run_experiment.py --experiment experiments/2026-03-24-foo/
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

# ---------------------------------------------------------------------------
# Project-local imports
# ---------------------------------------------------------------------------
from scripts.utils.config import (
    ExperimentConfig,
    load_experiment_config,
    load_yaml,
    save_yaml,
)
from scripts.utils.cost import calculate_cost
from scripts.utils.io import append_jsonl, read_jsonl, write_jsonl
from scripts.utils.providers import CompletionResult, get_provider
from scripts.utils.rate_limiter import AsyncRateLimiter
from scripts.utils.templates import PromptTemplate, load_templates, render_template

console = Console()

# ---------------------------------------------------------------------------
# Budget guard
# ---------------------------------------------------------------------------

HARD_STOP_SENTINEL = object()  # raised through asyncio.Queue to signal abort


class BudgetExceededError(RuntimeError):
    """Raised when the accumulated cost surpasses the experiment budget."""


# ---------------------------------------------------------------------------
# Matrix generation
# ---------------------------------------------------------------------------


def _generate_matrix(config: ExperimentConfig) -> list[dict[str, Any]]:
    """Return the full-factorial cell list from an ExperimentConfig.

    Each cell is a dict with keys: ``cell_id``, ``template_id``,
    ``param_id``, ``model_id``, ``model_name``, ``provider``,
    ``temperature``, ``max_tokens``, ``top_p``.
    """
    templates = config.axes.templates or []
    parameters = config.axes.parameters or []
    models = config.axes.models or []

    cells: list[dict[str, Any]] = []
    idx = 0

    for tpl in templates:
        for param in parameters:
            param_data = param.model_dump()
            applicable = param_data.pop("applicable_models", None)

            for model in models:
                if applicable and model.id not in applicable:
                    continue

                cell_id = f"cell_{idx:04d}_t{tpl.id}_p{param.id}_m{model.id}"
                cell = {
                    "cell_id": cell_id,
                    "template_id": tpl.id,
                    "template_file": tpl.file,
                    "param_id": param.id,
                    "model_id": model.id,
                    "model_name": model.name,
                    "provider": model.provider,
                    "temperature": param.temperature,
                    "max_tokens": param.max_tokens,
                    "top_p": param.top_p,
                    "base_url": getattr(model, "base_url", None),
                    "api_key_env": getattr(model, "api_key_env", None),
                    "cost_per_million_input": getattr(model, "cost_per_million_input", None),
                    "cost_per_million_output": getattr(model, "cost_per_million_output", None),
                }
                known_keys = {"id", "temperature", "max_tokens", "top_p", "applicable_models"}
                for key, val in param_data.items():
                    if key not in known_keys and val is not None:
                        cell[key] = val
                cells.append(cell)
                idx += 1

    return cells


# ---------------------------------------------------------------------------
# Test-input loading
# ---------------------------------------------------------------------------


def _load_test_inputs(
    experiment_dir: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Load test inputs from the experiment's data/ dir or the project data/ dir.

    Supports both ``.jsonl`` files (read line by line) and ``.yaml`` files
    (expected to contain a top-level list).  Returns a flat list of input
    dicts, each guaranteed to have an ``input_id`` key.
    """
    search_dirs = [
        experiment_dir / "data",
        project_root / "data",
    ]

    inputs: list[dict[str, Any]] = []

    for data_dir in search_dirs:
        if not data_dir.exists():
            continue

        for jsonl_file in sorted(data_dir.glob("*.jsonl")):
            try:
                records = read_jsonl(jsonl_file)
                for i, rec in enumerate(records):
                    if "input_id" not in rec:
                        rec["input_id"] = f"{jsonl_file.stem}_{i:04d}"
                inputs.extend(records)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]Warning: could not read {jsonl_file}: {exc}[/]")

        # Also check .yaml files
        for yaml_file in sorted(data_dir.glob("*.yaml")):
            try:
                raw = load_yaml(yaml_file)
                yaml_inputs = raw.get("inputs", [])
                for i, item in enumerate(yaml_inputs):
                    if isinstance(item, dict):
                        rec = dict(item)
                        # Map 'id' -> 'input_id' for pipeline consistency
                        if "id" in rec and "input_id" not in rec:
                            rec["input_id"] = rec.pop("id")
                        elif "input_id" not in rec:
                            rec["input_id"] = f"{yaml_file.stem}_{i:04d}"
                        inputs.append(rec)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]Warning: could not read {yaml_file}: {exc}[/]")

        # Only fall through to project data dir if nothing was found locally.
        if inputs:
            break

    if not inputs:
        console.print(
            "[yellow]Warning: no test inputs found — using a single empty input.[/]"
        )
        inputs = [{"input_id": "default_input_0000"}]

    return inputs


# ---------------------------------------------------------------------------
# Single-cell execution
# ---------------------------------------------------------------------------


async def _execute_cell(
    cell: dict[str, Any],
    test_input: dict[str, Any],
    templates: dict[str, PromptTemplate],
    provider_cache: dict[str, Any],
    rate_limiter: AsyncRateLimiter,
    semaphore: asyncio.Semaphore,
    results_dir: Path,
    budget_state: dict[str, float],
    budget_ceiling: float,
) -> dict[str, Any] | None:
    """Execute one (cell, test_input) pair and persist the result.

    Returns the result record on success, or ``None`` when the budget is
    exceeded before the call is made.
    """
    # Pre-flight budget check (best-effort; not a hard guarantee under
    # concurrent execution, but the post-flight check keeps us honest).
    if budget_state["total_cost"] >= budget_ceiling:
        return None

    template_id = cell["template_id"]
    template = templates.get(template_id)
    if template is None:
        console.print(
            f"[red]Template '{template_id}' not found — skipping cell {cell['cell_id']}.[/]"
        )
        return None

    # Build render variables from the test input.
    # Map common field names to template variable names:
    # - "text" -> "input" (templates use {{ input }}, test data uses "text")
    render_vars = dict(test_input)
    if "text" in render_vars and "input" not in render_vars:
        render_vars["input"] = render_vars["text"]

    # Render the prompt with the test input variables.
    try:
        rendered = render_template(template, render_vars)
    except Exception as exc:  # noqa: BLE001
        console.print(
            f"[red]Template render error for {cell['cell_id']}: {exc}[/]"
        )
        return None

    # Detect image inputs and attach to rendered prompt as a separate channel.
    # Supports: "image", "images", "image_url", "image_urls" keys in the input.
    # Images bypass Jinja2 rendering so the same template works for text-only
    # AND vision inputs without any template changes.
    images: list[str] = []
    for img_key in ("image", "images", "image_url", "image_urls"):
        val = test_input.get(img_key)
        if val:
            if isinstance(val, str):
                images.append(val)
            elif isinstance(val, list):
                images.extend(val)

    if images:
        # Resolve relative paths against the experiment directory.
        resolved_images: list[str] = []
        for img in images:
            if not img.startswith(("http://", "https://", "data:")):
                exp_path = results_dir.parent / img
                if exp_path.exists():
                    resolved_images.append(str(exp_path))
                else:
                    resolved_images.append(img)  # pass as-is; provider will warn
            else:
                resolved_images.append(img)
        rendered["images"] = resolved_images

    cache_key = (cell["provider"], cell.get("base_url", ""))
    if cache_key not in provider_cache:
        try:
            provider_cache[cache_key] = get_provider(cell)
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[red]Could not instantiate provider '{cell['provider']}': {exc}[/]"
            )
            return None

    provider = provider_cache[cache_key]

    async with semaphore:
        async with rate_limiter:
            t_start = time.monotonic()
            # Build API kwargs — core params + extended params if present
            api_kwargs: dict[str, Any] = {
                "prompt": rendered,
                "model": cell["model_name"],
                "temperature": cell["temperature"],
                "max_tokens": cell["max_tokens"],
                "top_p": cell["top_p"],
            }
            # Pass through ALL extra parameters from the cell
            # (anything beyond the core fields gets forwarded to the provider)
            skip_keys = {
                "cell_id", "template_id", "template_file", "param_id",
                "model_id", "model_name", "provider", "base_url",
                "api_key_env", "cost_per_million_input", "cost_per_million_output",
                "repetition", "status",
                "prompt", "model", "temperature", "max_tokens", "top_p",
            }
            for key, val in cell.items():
                if key not in skip_keys and val is not None:
                    api_kwargs[key] = val

            try:
                result: CompletionResult = await provider.complete(**api_kwargs)
            except Exception as exc:  # noqa: BLE001
                console.print(
                    f"[red]API error for {cell['cell_id']} / {test_input['input_id']}: {exc}[/]"
                )
                return None
            latency_ms = round((time.monotonic() - t_start) * 1000, 1)

    cost = calculate_cost(
        cell["model_name"],
        result.input_tokens,
        result.output_tokens,
        model_config=cell,  # passes cost_per_1k_input/output if available
    )

    # Enforce hard budget ceiling atomically enough for our purposes.
    budget_state["total_cost"] += cost
    if budget_state["total_cost"] > budget_ceiling:
        raise BudgetExceededError(
            f"Budget ceiling ${budget_ceiling:.2f} exceeded "
            f"(accumulated ${budget_state['total_cost']:.4f})."
        )

    record: dict[str, Any] = {
        "cell_id": cell["cell_id"],
        "template_id": template_id,
        "param_id": cell["param_id"],
        "model": cell["model_name"],
        "provider": cell["provider"],
        "parameters": {
            "temperature": cell["temperature"],
            "max_tokens": cell["max_tokens"],
            "top_p": cell["top_p"],
        },
        "input_id": test_input["input_id"],
        "input": test_input,
        "output": result.text,
        "tokens_in": result.input_tokens,
        "tokens_out": result.output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    out_path = results_dir / f"{cell['cell_id']}.jsonl"
    append_jsonl(out_path, record)

    return record


# ---------------------------------------------------------------------------
# Main experiment runner
# ---------------------------------------------------------------------------


async def run_experiment(experiment_dir: Path) -> dict[str, Any]:
    """Load, generate matrix (if needed), execute, and summarise an experiment.

    Args:
        experiment_dir: Path to the experiment directory containing
            ``plan.yaml``.

    Returns:
        The execution summary dict (also written to ``execution_summary.yaml``).

    Raises:
        FileNotFoundError: If ``plan.yaml`` is absent.
        BudgetExceededError: If the budget ceiling is breached mid-run.
    """
    experiment_dir = experiment_dir.resolve()
    plan_path = experiment_dir / "plan.yaml"

    if not plan_path.exists():
        raise FileNotFoundError(f"plan.yaml not found at {plan_path}")

    console.rule("[bold blue]Prompt Engineering Experiment Runner[/]")
    console.print(f"Experiment: [cyan]{experiment_dir.name}[/]")

    # ------------------------------------------------------------------
    # Load configuration
    # ------------------------------------------------------------------
    config: ExperimentConfig = load_experiment_config(experiment_dir)

    console.print(f"Name       : {config.name}")
    console.print(f"Budget     : ${config.budget.max_cost_usd:.2f}")

    # ------------------------------------------------------------------
    # Matrix: load existing or generate fresh
    # ------------------------------------------------------------------
    matrix_path = experiment_dir / "matrix.yaml"
    if matrix_path.exists():
        raw_matrix = load_yaml(matrix_path)
        cells: list[dict[str, Any]] = raw_matrix.get("cells", [])
        console.print(
            f"Matrix     : loaded {len(cells)} cells from matrix.yaml"
        )
    else:
        cells = _generate_matrix(config)
        save_yaml(matrix_path, {"cells": cells})
        console.print(
            f"Matrix     : generated {len(cells)} cells (full factorial) → matrix.yaml"
        )

    if not cells:
        console.print("[yellow]No cells in matrix — nothing to execute.[/]")
        return {
            "experiment_id": config.experiment_id,
            "total_items": 0,
            "completed": 0,
            "errors": 0,
            "budget_breached": False,
            "total_cost_usd": 0.0,
            "per_model_cost": {},
        }

    # ------------------------------------------------------------------
    # Templates and test inputs
    # ------------------------------------------------------------------
    project_root = experiment_dir.parent.parent
    templates_dir = experiment_dir / "templates"
    templates: dict[str, PromptTemplate] = load_templates(templates_dir)
    console.print(f"Templates  : {len(templates)} loaded")

    test_inputs = _load_test_inputs(experiment_dir, project_root)
    console.print(f"Test inputs: {len(test_inputs)}")

    # ------------------------------------------------------------------
    # Build work queue: (cell × repetitions) × inputs, randomised
    # ------------------------------------------------------------------
    repetitions = config.execution.repetitions
    work_items: list[tuple[dict[str, Any], dict[str, Any], int]] = [
        (cell, inp, rep)
        for rep in range(repetitions)
        for cell in cells
        for inp in test_inputs
    ]

    if config.execution.randomize_order:
        random.shuffle(work_items)

    total_items = len(work_items)
    console.print(
        f"Work items : {total_items} "
        f"({len(cells)} cells × {len(test_inputs)} inputs × {repetitions} reps)"
    )

    # ------------------------------------------------------------------
    # Concurrency primitives
    # ------------------------------------------------------------------
    semaphore = asyncio.Semaphore(config.execution.max_concurrent)
    rate_limiter = AsyncRateLimiter(
        requests_per_minute=60,  # conservative default; providers may override
    )

    results_dir = experiment_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    budget_state: dict[str, float] = {"total_cost": 0.0}
    per_model_cost: dict[str, float] = {}
    budget_ceiling = config.budget.max_cost_usd
    warn_at = config.budget.warn_at_usd

    provider_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Execute with rich progress bar
    # ------------------------------------------------------------------
    completed = 0
    errors = 0
    budget_breached = False

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

    async def _run_item(
        cell: dict[str, Any],
        inp: dict[str, Any],
        progress_task: Any,
    ) -> None:
        nonlocal completed, errors, budget_breached

        try:
            result = await _execute_cell(
                cell=cell,
                test_input=inp,
                templates=templates,
                provider_cache=provider_cache,
                rate_limiter=rate_limiter,
                semaphore=semaphore,
                results_dir=results_dir,
                budget_state=budget_state,
                budget_ceiling=budget_ceiling,
            )
            if result is None:
                errors += 1
            else:
                completed += 1
                model_key = cell.get("model_name", "unknown")
                per_model_cost[model_key] = (
                    per_model_cost.get(model_key, 0.0) + result.get("cost_usd", 0.0)
                )

        except BudgetExceededError as exc:
            budget_breached = True
            console.print(f"\n[bold red]HARD STOP — {exc}[/]")

        progress.advance(progress_task)

        # Warn when approaching budget.
        if (
            warn_at is not None
            and not budget_breached
            and budget_state["total_cost"] >= warn_at
        ):
            console.print(
                f"[yellow]Cost warning: ${budget_state['total_cost']:.4f} "
                f"has reached warn threshold ${warn_at:.2f}[/]"
            )

    with progress:
        task_id = progress.add_task("Executing cells…", total=total_items)

        tasks: list[asyncio.Task[None]] = []
        for cell, inp, _rep in work_items:
            if budget_breached:
                break
            t = asyncio.create_task(_run_item(cell, inp, task_id))
            tasks.append(t)

        # Gather with return_exceptions so one failure does not cancel siblings.
        await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Execution summary
    # ------------------------------------------------------------------
    summary: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "total_items": total_items,
        "completed": completed,
        "errors": errors,
        "budget_breached": budget_breached,
        "total_cost_usd": round(budget_state["total_cost"], 6),
        "budget_ceiling_usd": budget_ceiling,
        "per_model_cost": {k: round(v, 6) for k, v in per_model_cost.items()},
    }

    summary_path = experiment_dir / "execution_summary.yaml"
    save_yaml(summary_path, summary)

    # ------------------------------------------------------------------
    # Consolidated results — all inputs + outputs in one file for review
    # ------------------------------------------------------------------
    all_results_path = experiment_dir / "all_results.jsonl"
    try:
        all_records: list[dict[str, Any]] = []
        for jsonl_path in sorted(results_dir.glob("*.jsonl")):
            all_records.extend(read_jsonl(jsonl_path))
        write_jsonl(all_results_path, all_records)
        console.print(
            f"Consolidated {len(all_records)} records → [cyan]{all_results_path}[/]"
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Warning: could not write consolidated results: {exc}[/]")

    # ------------------------------------------------------------------
    # Update state.yaml
    # ------------------------------------------------------------------
    state_path = experiment_dir / "state.yaml"
    state: dict[str, Any] = load_yaml(state_path) if state_path.exists() else {}
    state["EXECUTE"] = "completed"
    state["execute_completed_at"] = summary["completed_at"]
    save_yaml(state_path, state)

    # ------------------------------------------------------------------
    # Final summary table
    # ------------------------------------------------------------------
    table = Table(title="Execution Summary", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Work items", str(total_items))
    table.add_row("Completed", f"[green]{completed}[/]")
    table.add_row("Errors / skipped", f"[red]{errors}[/]" if errors else "0")
    table.add_row("Budget breached", "[red]YES[/]" if budget_breached else "[green]no[/]")
    table.add_row("Total cost", f"${budget_state['total_cost']:.4f}")
    table.add_row("Budget ceiling", f"${budget_ceiling:.2f}")

    console.print(table)
    console.print(f"\nSummary written to [cyan]{summary_path}[/]")

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_experiment",
        description="Execute all cells in a prompt engineering experiment.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        type=Path,
        metavar="DIR",
        help="Path to the experiment directory (must contain plan.yaml).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="After the run, print the execution_summary as JSON to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — parses args and drives the async runner."""
    args = _parse_args(argv)

    try:
        summary = asyncio.run(run_experiment(args.experiment))
        if args.json:
            # Write only the requested fields; use sys.stdout so rich does not
            # intercept or colour the output.
            json_payload = {
                "experiment_id": summary["experiment_id"],
                "total_items": summary["total_items"],
                "completed": summary["completed"],
                "errors": summary["errors"],
                "budget_breached": summary["budget_breached"],
                "total_cost_usd": summary["total_cost_usd"],
                "per_model_cost": summary["per_model_cost"],
            }
            sys.stdout.write(json.dumps(json_payload, indent=2) + "\n")
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)
    except BudgetExceededError as exc:
        console.print(f"[bold red]Budget exceeded:[/] {exc}")
        sys.exit(2)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()

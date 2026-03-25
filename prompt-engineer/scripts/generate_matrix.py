"""Matrix generator — MATRIX stage of the prompt engineering pipeline.

Reads plan.yaml, computes the combinatorial matrix from axes (templates x
parameters x models), applies the execution strategy (full/fractional), and
writes matrix.yaml.

Usage:
    python scripts/generate_matrix.py --experiment experiments/2026-03-25-foo/

Options:
    --strategy full|fractional|latin_square  Override plan.yaml strategy
    --dry-run                                 Print matrix stats without writing
"""

from __future__ import annotations

import argparse
import itertools
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from scripts.utils.config import (
    ExperimentConfig,
    load_experiment_config,
    load_yaml,
    save_yaml,
)
from scripts.utils.cost import calculate_cost

console = Console()


def generate_full_factorial(config: ExperimentConfig) -> list[dict[str, Any]]:
    """Generate every combination of template x parameters x models.

    Returns a list of cell dicts, each with:
        cell_id, template_id, template_file, param_id, model_id,
        model_name, provider, temperature, max_tokens, top_p, repetition
    """
    templates = config.axes.templates or []
    parameters = config.axes.parameters or []
    models = config.axes.models or []
    reps = config.execution.repetitions

    cells: list[dict[str, Any]] = []
    idx = 0

    for tpl, param, model in itertools.product(templates, parameters, models):
        for rep in range(1, reps + 1):
            cell_id = f"cell-{idx:04d}"
            cell = {
                "cell_id": cell_id,
                "template_id": tpl.id,
                "template_file": tpl.file,
                "param_id": param.id,
                "model_id": model.id,
                "model_name": model.name,
                "provider": model.provider,
                "base_url": getattr(model, "base_url", None),
                "api_key_env": getattr(model, "api_key_env", None),
                "cost_per_million_input": getattr(model, "cost_per_million_input", None),
                "cost_per_million_output": getattr(model, "cost_per_million_output", None),
                "temperature": param.temperature,
                "max_tokens": param.max_tokens,
                "top_p": param.top_p,
                "repetition": rep,
                "status": "pending",
            }
            # Include extended parameters when present
            for ext_key in ("top_k", "frequency_penalty", "presence_penalty",
                            "json_mode", "thinking", "thinking_budget",
                            "seed", "stop_sequences", "extra"):
                val = getattr(param, ext_key, None)
                if val is not None:
                    cell[ext_key] = val
            cells.append(cell)
            idx += 1

    return cells


def generate_fractional_factorial(
    config: ExperimentConfig,
    fraction: float = 0.25,
) -> list[dict[str, Any]]:
    """Sample a fraction of the full factorial while ensuring coverage.

    Every level of every axis appears at least once.
    """
    full = generate_full_factorial(config)
    target_size = max(int(len(full) * fraction), 1)

    # Ensure coverage: pick one cell per level for each axis
    covered: set[int] = set()
    for axis_key in ("template_id", "model_id", "param_id"):
        levels = {cell[axis_key] for cell in full}
        for level in levels:
            candidates = [
                i for i, c in enumerate(full)
                if c[axis_key] == level and i not in covered
            ]
            if candidates:
                covered.add(random.choice(candidates))

    # Fill remaining slots randomly
    remaining = [i for i in range(len(full)) if i not in covered]
    random.shuffle(remaining)
    slots_left = max(0, target_size - len(covered))
    covered.update(remaining[:slots_left])

    return [full[i] for i in sorted(covered)]


def estimate_cost(
    cells: list[dict[str, Any]],
    num_inputs: int,
    avg_input_tokens: int = 500,
    avg_output_tokens: int = 200,
) -> dict[str, Any]:
    """Estimate total cost for the matrix.

    Returns dict with: total_calls, total_cost_usd, cost_by_model.
    """
    total_calls = len(cells) * num_inputs
    total_cost = 0.0
    cost_by_model: dict[str, float] = {}

    for cell in cells:
        model = cell["model_name"]
        cell_cost = calculate_cost(model, avg_input_tokens, avg_output_tokens, model_config=cell)
        per_cell_total = cell_cost * num_inputs

        total_cost += per_cell_total
        cost_by_model[model] = cost_by_model.get(model, 0.0) + per_cell_total

    return {
        "total_cells": len(cells),
        "total_calls": total_calls,
        "total_cost_usd": round(total_cost, 4),
        "cost_by_model": {k: round(v, 4) for k, v in cost_by_model.items()},
    }


def generate_matrix(experiment_dir: Path, strategy_override: str | None = None, dry_run: bool = False) -> None:
    """Main entry: load plan, generate matrix, write matrix.yaml."""
    experiment_dir = experiment_dir.resolve()
    plan_path = experiment_dir / "plan.yaml"

    if not plan_path.exists():
        raise FileNotFoundError(f"plan.yaml not found at {plan_path}")

    console.rule("[bold blue]Matrix Generator[/]")
    console.print(f"Experiment: [cyan]{experiment_dir.name}[/]")

    config = load_experiment_config(experiment_dir)
    strategy = strategy_override or config.execution.strategy

    # Count axes
    n_templates = len(config.axes.templates)
    n_params = len(config.axes.parameters)
    n_models = len(config.axes.models)
    n_reps = config.execution.repetitions
    full_size = n_templates * n_params * n_models * n_reps

    console.print(f"Templates  : {n_templates}")
    console.print(f"Parameters : {n_params}")
    console.print(f"Models     : {n_models}")
    console.print(f"Repetitions: {n_reps}")
    console.print(f"Full size  : {full_size} cells")
    console.print(f"Strategy   : {strategy}")

    # Generate cells based on strategy
    if strategy == "fractional":
        cells = generate_fractional_factorial(config, fraction=0.25)
        console.print(f"Fractional : {len(cells)} cells (25% of full)")
    else:
        cells = generate_full_factorial(config)

    # Randomize order if configured
    if config.execution.randomize_order:
        random.shuffle(cells)
        console.print("Order      : randomized")

    # Load test input count for cost estimation
    data_dir = experiment_dir / "data"
    num_inputs = 20  # default
    for yaml_file in data_dir.glob("*.yaml"):
        try:
            data = load_yaml(yaml_file)
            if "inputs" in data:
                num_inputs = len(data["inputs"])
                break
        except Exception:
            pass

    # Cost estimate
    cost_info = estimate_cost(cells, num_inputs)

    console.print()
    cost_table = Table(title="Cost Estimate", show_header=True)
    cost_table.add_column("Metric", style="bold")
    cost_table.add_column("Value")
    cost_table.add_row("Total cells", str(cost_info["total_cells"]))
    cost_table.add_row("Total API calls", str(cost_info["total_calls"]))
    cost_table.add_row("Estimated cost", f"${cost_info['total_cost_usd']:.4f}")
    cost_table.add_row("Budget ceiling", f"${config.budget.max_cost_usd:.2f}")

    for model, cost in cost_info["cost_by_model"].items():
        cost_table.add_row(f"  {model}", f"${cost:.4f}")

    console.print(cost_table)

    # Budget check
    if cost_info["total_cost_usd"] > config.budget.max_cost_usd:
        console.print(
            f"\n[bold red]WARNING: Estimated cost ${cost_info['total_cost_usd']:.2f} "
            f"exceeds budget ${config.budget.max_cost_usd:.2f}[/]"
        )
        console.print("Consider: --strategy fractional, fewer models, or higher budget")

    if dry_run:
        console.print("\n[yellow]Dry run — matrix.yaml not written.[/]")
        return

    # Write matrix.yaml
    matrix_path = experiment_dir / "matrix.yaml"
    save_yaml(matrix_path, {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "total_cells": len(cells),
        "cost_estimate": cost_info,
        "cells": cells,
    })
    console.print(f"\nMatrix written to [cyan]{matrix_path}[/]")

    # Update state.yaml
    state_path = experiment_dir / "state.yaml"
    state = load_yaml(state_path) if state_path.exists() else {}
    stages = state.get("stages_completed", {})
    stages["MATRIX"] = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "artifact": "matrix.yaml",
    }
    state["stages_completed"] = stages
    state["current_stage"] = "EXECUTE"
    save_yaml(state_path, state)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="generate_matrix",
        description="Generate the combinatorial experiment matrix from plan.yaml.",
    )
    parser.add_argument(
        "--experiment", required=True, type=Path, metavar="DIR",
        help="Path to experiment directory (must contain plan.yaml).",
    )
    parser.add_argument(
        "--strategy", choices=["full", "fractional", "latin_square"],
        help="Override the strategy in plan.yaml.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print stats without writing matrix.yaml.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        generate_matrix(args.experiment, args.strategy, args.dry_run)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

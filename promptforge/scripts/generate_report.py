"""Report generator — builds report_data.json and report.md from evaluation results.

Usage:
    python scripts/generate_report.py --experiment experiments/{id}/
    python scripts/generate_report.py --experiment experiments/{id}/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.config import load_yaml  # noqa: E402
from scripts.utils.io import read_jsonl, write_markdown  # noqa: E402

console = Console()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_scores_df(experiment_dir: Path) -> pd.DataFrame:
    """Read evaluations/scores.jsonl into a DataFrame.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        DataFrame with one row per (cell_id, input_id, repetition) record.

    Raises:
        FileNotFoundError: If scores.jsonl does not exist.
    """
    scores_path = experiment_dir / "evaluations" / "scores.jsonl"
    if not scores_path.exists():
        raise FileNotFoundError(f"Scores file not found: {scores_path}")

    records = read_jsonl(scores_path)
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Flatten per-criterion scores from the nested ``scores`` dict into columns
    if "scores" in df.columns:
        criterion_df = pd.json_normalize(df["scores"])  # type: ignore[arg-type]
        df = pd.concat([df.drop(columns=["scores"]), criterion_df], axis=1)

    return df


def _load_summary(experiment_dir: Path) -> dict[str, Any]:
    """Load evaluations/summary.yaml.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Parsed summary dict (empty dict on missing file).
    """
    summary_path = experiment_dir / "evaluations" / "summary.yaml"
    if not summary_path.exists():
        return {}
    return load_yaml(summary_path)


def _load_plan(experiment_dir: Path) -> dict[str, Any]:
    """Load plan.yaml (returns empty dict when absent)."""
    plan_path = experiment_dir / "plan.yaml"
    if not plan_path.exists():
        return {}
    return load_yaml(plan_path)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------


def _detect_criterion_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that represent per-criterion scores.

    Heuristic: exclude known metadata columns and keep numeric columns that
    are not ``composite_score``.

    Args:
        df: The scores DataFrame.

    Returns:
        List of criterion column names.
    """
    excluded = {
        "cell_id", "template_id", "model", "model_id", "param_id",
        "input_id", "repetition", "composite_score", "judge_reasoning",
        "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    }
    return [
        col for col in df.columns
        if col not in excluded and pd.api.types.is_numeric_dtype(df[col])
    ]


def _build_rankings(df: pd.DataFrame, plan_raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate per-cell mean scores and return a ranked list.

    Args:
        df: Flat scores DataFrame.
        plan_raw: Parsed plan.yaml (used to look up model names).

    Returns:
        List of ranking dicts sorted by mean_score descending.
    """
    if df.empty or "composite_score" not in df.columns:
        return []

    # Build a model_id -> model_name lookup from plan
    model_lookup: dict[str, str] = {
        m.get("id", ""): m.get("name", m.get("id", ""))
        for m in plan_raw.get("axes", {}).get("models", [])
        if isinstance(m, dict)
    }

    group_cols = ["cell_id", "template_id", "param_id"]
    # Include model identifier: prefer model_id if present, else model
    if "model_id" in df.columns:
        group_cols.append("model_id")
        model_col = "model_id"
    elif "model" in df.columns:
        group_cols.append("model")
        model_col = "model"
    else:
        model_col = None

    # Aggregate score, cost, latency, and tokens per cell
    agg_cols = {"composite_score": ["mean", "std", "count"]}
    for extra_col in ("cost_usd", "latency_ms", "tokens_in", "tokens_out"):
        if extra_col in df.columns:
            agg_cols[extra_col] = "mean"

    agg = df.groupby(group_cols).agg(agg_cols).reset_index()
    # Flatten multi-level columns
    agg.columns = [
        f"{col[0]}_{col[1]}" if col[1] else col[0]
        for col in agg.columns
    ]
    agg = agg.rename(columns={
        "composite_score_mean": "mean_score",
        "composite_score_std": "std",
        "composite_score_count": "count",
        "cost_usd_mean": "mean_cost_usd",
        "latency_ms_mean": "mean_latency_ms",
        "tokens_in_mean": "mean_tokens_in",
        "tokens_out_mean": "mean_tokens_out",
    })
    agg["std"] = agg["std"].fillna(0.0)
    agg = agg.sort_values("mean_score", ascending=False).reset_index(drop=True)
    agg.insert(0, "rank", range(1, len(agg) + 1))

    rankings: list[dict[str, Any]] = []
    for _, row in agg.iterrows():
        model_id_val = row.get(model_col, "") if model_col else ""
        entry: dict[str, Any] = {
            "rank": int(row["rank"]),
            "cell_id": row.get("cell_id", ""),
            "template_id": row.get("template_id", ""),
            "model": model_lookup.get(str(model_id_val), str(model_id_val)),
            "model_id": str(model_id_val),
            "param_id": row.get("param_id", ""),
            "mean_score": round(float(row["mean_score"]), 4),
            "std": round(float(row["std"]), 4),
            "count": int(row["count"]),
        }
        if "mean_cost_usd" in row:
            entry["mean_cost_usd"] = round(float(row["mean_cost_usd"]), 6)
        if "mean_latency_ms" in row:
            entry["mean_latency_ms"] = round(float(row["mean_latency_ms"]), 1)
        if "mean_tokens_in" in row:
            entry["mean_tokens_in"] = round(float(row["mean_tokens_in"]), 0)
        if "mean_tokens_out" in row:
            entry["mean_tokens_out"] = round(float(row["mean_tokens_out"]), 0)
        rankings.append(entry)

    return rankings


def _build_axis_analysis(
    df: pd.DataFrame,
    plan_raw: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Compute marginal mean scores per level for each experimental axis.

    Args:
        df: Flat scores DataFrame.
        plan_raw: Parsed plan.yaml.

    Returns:
        Dict mapping axis name -> list of ``{level, mean_score}`` dicts,
        sorted by mean_score descending.
    """
    if df.empty or "composite_score" not in df.columns:
        return {}

    axis_map: dict[str, str] = {
        "template": "template_id",
        "model": "model_id" if "model_id" in df.columns else "model",
        "parameters": "param_id",
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for axis_label, col in axis_map.items():
        if col not in df.columns:
            continue
        # Aggregate score plus optional cost and latency
        agg_dict: dict[str, Any] = {"composite_score": "mean"}
        if "cost_usd" in df.columns:
            agg_dict["cost_usd"] = "mean"
        if "latency_ms" in df.columns:
            agg_dict["latency_ms"] = "mean"

        level_agg = (
            df.groupby(col)
            .agg(agg_dict)
            .sort_values("composite_score", ascending=False)
            .reset_index()
        )
        axis_rows: list[dict[str, Any]] = []
        for _, row in level_agg.iterrows():
            entry: dict[str, Any] = {
                "level": str(row[col]),
                "mean_score": round(float(row["composite_score"]), 4),
            }
            if "cost_usd" in row:
                entry["mean_cost_usd"] = round(float(row["cost_usd"]), 6)
            if "latency_ms" in row:
                entry["mean_latency_ms"] = round(float(row["latency_ms"]), 1)
            axis_rows.append(entry)
        result[axis_label] = axis_rows

    return result


def _build_cost_performance(
    df: pd.DataFrame,
    rankings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute cost-per-call and Pareto-efficiency for each cell.

    A cell is Pareto-efficient if no other cell dominates it on both score
    and cost simultaneously.

    Args:
        df: Flat scores DataFrame (may include ``cost_usd`` column).
        rankings: Pre-computed rankings list from :func:`_build_rankings`.

    Returns:
        List of cost-performance dicts, sorted by mean_score descending.
    """
    if not rankings:
        return []

    # Build cost, latency, and token lookups from scores if available
    cost_by_cell: dict[str, float] = {}
    latency_by_cell: dict[str, float] = {}
    tokens_in_by_cell: dict[str, float] = {}
    tokens_out_by_cell: dict[str, float] = {}
    if "cost_usd" in df.columns and "cell_id" in df.columns:
        cost_series = df.groupby("cell_id")["cost_usd"].mean()
        cost_by_cell = cost_series.to_dict()
    if "latency_ms" in df.columns and "cell_id" in df.columns:
        latency_by_cell = df.groupby("cell_id")["latency_ms"].mean().to_dict()
    if "tokens_in" in df.columns and "cell_id" in df.columns:
        tokens_in_by_cell = df.groupby("cell_id")["tokens_in"].mean().to_dict()
    if "tokens_out" in df.columns and "cell_id" in df.columns:
        tokens_out_by_cell = df.groupby("cell_id")["tokens_out"].mean().to_dict()

    rows: list[dict[str, Any]] = []
    for entry in rankings:
        cell_id = entry["cell_id"]
        cost = float(cost_by_cell.get(cell_id, 0.0))
        row_data: dict[str, Any] = {
            "cell_id": cell_id,
            "mean_score": entry["mean_score"],
            "cost_per_call": round(cost, 6),
            "pareto_efficient": False,  # Filled in below
        }
        if latency_by_cell:
            row_data["latency_ms"] = round(float(latency_by_cell.get(cell_id, 0.0)), 1)
        if tokens_in_by_cell:
            row_data["tokens_in"] = round(float(tokens_in_by_cell.get(cell_id, 0.0)), 0)
        if tokens_out_by_cell:
            row_data["tokens_out"] = round(float(tokens_out_by_cell.get(cell_id, 0.0)), 0)
        rows.append(row_data)

    # Mark Pareto-efficient cells (higher score, lower cost — non-dominated)
    for i, row_i in enumerate(rows):
        dominated = False
        for j, row_j in enumerate(rows):
            if i == j:
                continue
            # j dominates i if j has >= score AND <= cost, strictly better in at least one
            if (
                row_j["mean_score"] >= row_i["mean_score"]
                and row_j["cost_per_call"] <= row_i["cost_per_call"]
                and (
                    row_j["mean_score"] > row_i["mean_score"]
                    or row_j["cost_per_call"] < row_i["cost_per_call"]
                )
            ):
                dominated = True
                break
        row_i["pareto_efficient"] = not dominated

    return rows


def _build_per_criterion(
    df: pd.DataFrame,
    criterion_cols: list[str],
) -> dict[str, dict[str, Any]]:
    """Summarise per-criterion statistics and identify best/worst cells.

    Args:
        df: Flat scores DataFrame with criterion columns expanded.
        criterion_cols: List of criterion column names to analyse.

    Returns:
        Dict mapping criterion name -> stats dict.
    """
    if df.empty or not criterion_cols:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for criterion in criterion_cols:
        if criterion not in df.columns:
            continue

        overall_mean = float(df[criterion].mean())
        overall_std = float(df[criterion].std(ddof=1)) if len(df) > 1 else 0.0

        # Best and worst cells for this criterion
        best_cell = ""
        worst_cell = ""
        if "cell_id" in df.columns:
            cell_means = df.groupby("cell_id")[criterion].mean()
            best_cell = str(cell_means.idxmax())
            worst_cell = str(cell_means.idxmin())

        result[criterion] = {
            "mean": round(overall_mean, 4),
            "std": round(overall_std, 4),
            "best_cell": best_cell,
            "worst_cell": worst_cell,
        }

    return result


def _resolve_experiment_id(experiment_dir: Path, plan_raw: dict[str, Any]) -> str:
    """Extract experiment_id from plan.yaml or fall back to directory name."""
    if "experiment" in plan_raw:
        return str(plan_raw["experiment"].get("id", experiment_dir.name))
    return str(plan_raw.get("experiment_id", experiment_dir.name))


# ---------------------------------------------------------------------------
# Report data assembly
# ---------------------------------------------------------------------------


def build_report_data(experiment_dir: Path) -> dict[str, Any]:
    """Build the complete report_data dict from scores and summary.

    Args:
        experiment_dir: Experiment root directory.

    Returns:
        Structured report data dict ready for JSON serialisation.

    Raises:
        FileNotFoundError: If evaluations/scores.jsonl is missing.
    """
    df = _load_scores_df(experiment_dir)
    summary = _load_summary(experiment_dir)
    plan_raw = _load_plan(experiment_dir)

    experiment_id = _resolve_experiment_id(experiment_dir, plan_raw)
    generated_at = datetime.now(tz=timezone.utc).isoformat()

    # --- Summary block ---
    total_cells = int(summary.get("total_cells_evaluated", df["cell_id"].nunique() if not df.empty and "cell_id" in df.columns else 0))
    total_evaluations = len(df) if not df.empty else 0

    best_raw = summary.get("overall_best_combination", {})
    best_cell_block: dict[str, Any] = {
        "cell_id": best_raw.get("cell_id", ""),
        "template_id": best_raw.get("template_id", ""),
        "model": best_raw.get("model_name", best_raw.get("model_id", "")),
        "score": float(
            best_raw.get("mean_composite_score")
            or best_raw.get("mean_composite")
            or 0.0
        ),
    }

    # Worst cell from summary bottom_5 or computed from df
    worst_cell_block: dict[str, Any] = {"cell_id": "", "template_id": "", "model": "", "score": 0.0}
    bottom_cells: list[dict[str, Any]] = summary.get("bottom_5_cells", [])
    if bottom_cells:
        worst_raw = bottom_cells[-1]
        worst_cell_block = {
            "cell_id": worst_raw.get("cell_id", ""),
            "template_id": worst_raw.get("template_id", ""),
            "model": worst_raw.get("model_id", ""),
            "score": float(worst_raw.get("mean_composite", 0.0)),
        }
    elif not df.empty and "cell_id" in df.columns and "composite_score" in df.columns:
        worst_means = df.groupby("cell_id")["composite_score"].mean()
        worst_id = str(worst_means.idxmin())
        worst_row = df[df["cell_id"] == worst_id].iloc[0]
        worst_cell_block = {
            "cell_id": worst_id,
            "template_id": str(worst_row.get("template_id", "")),
            "model": str(worst_row.get("model_id", worst_row.get("model", ""))),
            "score": round(float(worst_means.min()), 4),
        }

    # --- Rankings ---
    rankings = _build_rankings(df, plan_raw)

    # --- Axis analysis ---
    axis_analysis = _build_axis_analysis(df, plan_raw)

    # --- Cost-performance ---
    cost_performance = _build_cost_performance(df, rankings)

    # --- Per-criterion ---
    criterion_cols = _detect_criterion_columns(df)
    per_criterion = _build_per_criterion(df, criterion_cols)

    return {
        "experiment_id": experiment_id,
        "generated_at": generated_at,
        "summary": {
            "total_cells": total_cells,
            "total_evaluations": total_evaluations,
            "best_cell": best_cell_block,
            "worst_cell": worst_cell_block,
        },
        "rankings": rankings,
        "axis_analysis": axis_analysis,
        "cost_performance": cost_performance,
        "per_criterion": per_criterion,
    }


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------


def _md_rankings_table(rankings: list[dict[str, Any]], top_n: int = 15) -> str:
    """Render rankings as a markdown table."""
    if not rankings:
        return "_No rankings data available._\n"

    # Detect which optional columns are present (only show if data exists)
    has_cost = any("mean_cost_usd" in r for r in rankings[:top_n])
    has_latency = any("mean_latency_ms" in r for r in rankings[:top_n])
    has_tokens = any("mean_tokens_in" in r for r in rankings[:top_n])

    header = "| Rank | Cell ID | Template | Model | Params | Mean Score | Std | N"
    separator = "|------|---------|----------|-------|--------|-----------|-----|---"
    if has_cost:
        header += " | Cost/Call"
        separator += "|----------"
    if has_latency:
        header += " | Latency (ms)"
        separator += "|--------------"
    if has_tokens:
        header += " | Tokens In | Tokens Out"
        separator += "|-----------|----------"
    header += " |"
    separator += "|"

    lines = [header, separator]
    for row in rankings[:top_n]:
        line = (
            f"| {row['rank']} "
            f"| {row['cell_id']} "
            f"| {row['template_id']} "
            f"| {row['model_id']} "
            f"| {row['param_id']} "
            f"| **{row['mean_score']:.4f}** "
            f"| {row['std']:.4f} "
            f"| {row['count']}"
        )
        if has_cost:
            cost = row.get("mean_cost_usd", 0.0)
            line += f" | ${cost:.6f}"
        if has_latency:
            latency = row.get("mean_latency_ms", 0.0)
            line += f" | {latency:.1f}"
        if has_tokens:
            tokens_in = row.get("mean_tokens_in", 0)
            tokens_out = row.get("mean_tokens_out", 0)
            line += f" | {tokens_in:.0f} | {tokens_out:.0f}"
        line += " |"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _md_axis_table(axis_data: list[dict[str, Any]]) -> str:
    """Render a single axis analysis list as a markdown table."""
    if not axis_data:
        return "_No data._\n"

    has_cost = any("mean_cost_usd" in r for r in axis_data)
    has_latency = any("mean_latency_ms" in r for r in axis_data)
    header = "| Level | Mean Score"
    separator = "|-------|----------"
    if has_cost:
        header += " | Mean Cost"
        separator += "|----------"
    if has_latency:
        header += " | Mean Latency (ms)"
        separator += "|------------------"
    header += " |"
    separator += "|"

    lines = [header, separator]
    for row in axis_data:
        line = f"| {row['level']} | {row['mean_score']:.4f}"
        if has_cost:
            line += f" | ${row.get('mean_cost_usd', 0.0):.6f}"
        if has_latency:
            line += f" | {row.get('mean_latency_ms', 0.0):.1f}"
        line += " |"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _md_cost_performance_table(cost_perf: list[dict[str, Any]]) -> str:
    """Render cost-performance data as a markdown table."""
    if not cost_perf:
        return "_No cost data available._\n"

    has_latency = any("latency_ms" in r for r in cost_perf)
    has_tokens = any("tokens_in" in r for r in cost_perf)

    header = "| Cell ID | Mean Score | Cost/Call (USD)"
    separator = "|---------|-----------|----------------"
    if has_latency:
        header += " | Latency (ms)"
        separator += "|--------------"
    if has_tokens:
        header += " | Tokens In | Tokens Out"
        separator += "|-----------|----------"
    header += " | Pareto Efficient |"
    separator += "|-----------------|"

    lines = [header, separator]
    for row in sorted(cost_perf, key=lambda x: x["mean_score"], reverse=True):
        pareto_marker = "Yes" if row["pareto_efficient"] else ""
        line = (
            f"| {row['cell_id']} "
            f"| {row['mean_score']:.4f} "
            f"| ${row['cost_per_call']:.6f}"
        )
        if has_latency:
            line += f" | {row.get('latency_ms', 0.0):.1f}"
        if has_tokens:
            line += f" | {row.get('tokens_in', 0):.0f} | {row.get('tokens_out', 0):.0f}"
        line += f" | {pareto_marker} |"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _md_per_criterion_table(per_criterion: dict[str, dict[str, Any]]) -> str:
    """Render per-criterion stats as a markdown table."""
    if not per_criterion:
        return "_No criterion data available._\n"
    lines = [
        "| Criterion | Mean | Std | Best Cell | Worst Cell |",
        "|-----------|------|-----|-----------|------------|",
    ]
    for criterion, stats in per_criterion.items():
        lines.append(
            f"| {criterion} "
            f"| {stats['mean']:.4f} "
            f"| {stats['std']:.4f} "
            f"| {stats['best_cell']} "
            f"| {stats['worst_cell']} |"
        )
    return "\n".join(lines) + "\n"


def build_markdown_report(data: dict[str, Any]) -> str:
    """Render a complete markdown report from *data*.

    Args:
        data: Output of :func:`build_report_data`.

    Returns:
        Markdown string suitable for writing to ``report.md``.
    """
    exp_id = data["experiment_id"]
    generated_at = data["generated_at"]
    summary = data["summary"]
    best = summary["best_cell"]
    worst = summary["worst_cell"]

    lines: list[str] = []

    # Header
    lines += [
        f"# Experiment Report: {exp_id}",
        "",
        f"**Generated:** {generated_at}",
        "",
    ]

    # Executive summary
    lines += [
        "## Executive Summary",
        "",
        f"- **Total cells evaluated:** {summary['total_cells']}",
        f"- **Total evaluation records:** {summary['total_evaluations']}",
        f"- **Best cell:** `{best['cell_id']}` — {best['template_id']} × {best['model']} — score **{best['score']:.4f}**",
        f"- **Worst cell:** `{worst['cell_id']}` — {worst['template_id']} × {worst['model']} — score **{worst['score']:.4f}**",
        "",
    ]

    # Rankings
    lines += [
        "## Cell Rankings (Top 15)",
        "",
        _md_rankings_table(data["rankings"]),
    ]

    # Axis analysis
    lines += ["## Axis Analysis", ""]
    axis_analysis: dict[str, list[dict[str, Any]]] = data["axis_analysis"]

    for axis_label in ("template", "model", "parameters"):
        axis_data = axis_analysis.get(axis_label, [])
        lines += [
            f"### By {axis_label.title()}",
            "",
            _md_axis_table(axis_data),
        ]

    # Cost-performance
    lines += [
        "## Cost-Performance Analysis",
        "",
        _md_cost_performance_table(data["cost_performance"]),
    ]

    # Per-criterion
    lines += [
        "## Per-Criterion Statistics",
        "",
        _md_per_criterion_table(data["per_criterion"]),
    ]

    # Recommendations placeholder
    lines += [
        "## Recommendations",
        "",
        "<!-- Claude: Please analyse the rankings, axis analysis, and per-criterion statistics",
        "     above and provide 3-5 actionable recommendations for the next experiment iteration.",
        "     Consider: which axes drive the most variance, cost-efficiency trade-offs,",
        "     and whether any criteria have unexpectedly low scores. -->",
        "",
        "_Recommendations to be filled in by analysis._",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File output helpers
# ---------------------------------------------------------------------------


def _write_report_files(
    experiment_dir: Path,
    data: dict[str, Any],
    markdown: str,
) -> tuple[Path, Path]:
    """Write report_data.json and report.md to the experiment directory.

    Args:
        experiment_dir: Experiment root directory.
        data: Structured report data dict.
        markdown: Rendered markdown string.

    Returns:
        Tuple of (json_path, md_path).
    """
    json_path = experiment_dir / "report_data.json"
    md_path = experiment_dir / "report.md"

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    write_markdown(md_path, markdown)

    return json_path, md_path


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------


def _print_rich_summary(
    data: dict[str, Any],
    json_path: Path,
    md_path: Path,
) -> None:
    """Render a console summary of the generated report."""
    summary = data["summary"]
    best = summary["best_cell"]

    console.print()
    table = Table(title="Report Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    table.add_row("Experiment ID", data["experiment_id"])
    table.add_row("Generated at", data["generated_at"])
    table.add_row("Total cells", str(summary["total_cells"]))
    table.add_row("Total evaluations", str(summary["total_evaluations"]))
    table.add_row(
        "Best cell",
        f"{best['cell_id']} ({best['template_id']}) — score {best['score']:.4f}",
    )
    table.add_row("Rankings computed", str(len(data["rankings"])))
    table.add_row("Criteria analysed", str(len(data["per_criterion"])))

    console.print(table)
    console.print(f"\n[bold]JSON data:[/] {json_path}")
    console.print(f"[bold]Markdown: [/] {md_path}\n")


def _print_json_output(data: dict[str, Any]) -> None:
    """Print the full report_data dict as JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_report",
        description="Generate report_data.json and report.md from evaluation results.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        metavar="DIR",
        help="Path to the experiment directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print the report data as JSON to stdout (files are still written).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 on success, 1 on error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    experiment_dir = Path(args.experiment)
    if not experiment_dir.exists():
        console.print(f"[red]ERROR:[/] Directory not found: {experiment_dir}")
        return 1

    try:
        report_data = build_report_data(experiment_dir)
    except FileNotFoundError as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]ERROR:[/] Unexpected error building report data: {exc}")
        return 1

    markdown = build_markdown_report(report_data)

    try:
        json_path, md_path = _write_report_files(experiment_dir, report_data, markdown)
    except OSError as exc:
        console.print(f"[red]ERROR:[/] Could not write report files: {exc}")
        return 1

    if args.output_json:
        _print_json_output(report_data)
    else:
        _print_rich_summary(report_data, json_path, md_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())

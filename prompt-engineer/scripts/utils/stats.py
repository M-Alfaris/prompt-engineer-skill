"""Statistical analysis utilities for experiment results."""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np
import pandas as pd
import scipy.stats


def compute_cell_stats(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute descriptive statistics for a list of score records.

    Each record in ``scores`` must contain a ``scores`` key mapping criterion
    names to numeric values (1-10 scale) and a ``composite_score`` key.

    Args:
        scores: List of score records produced by the evaluation engine.

    Returns:
        Dict with keys for each criterion plus ``composite_score``.  Each value
        is a dict containing ``mean``, ``median``, ``std``, ``ci_95_low``, and
        ``ci_95_high``.  Returns an empty dict when ``scores`` is empty.
    """
    if not scores:
        return {}

    # Collect values per criterion across all records.
    criterion_values: dict[str, list[float]] = {}

    for record in scores:
        # Per-criterion scores nested under the "scores" key.
        for criterion, value in record.get("scores", {}).items():
            criterion_values.setdefault(criterion, []).append(float(value))

        # Always track the composite score as its own series.
        if "composite_score" in record:
            criterion_values.setdefault("composite_score", []).append(
                float(record["composite_score"])
            )

    result: dict[str, Any] = {}
    for criterion, values in criterion_values.items():
        n = len(values)
        mean = statistics.mean(values)
        median = statistics.median(values)
        std = statistics.pstdev(values) if n == 1 else statistics.stdev(values)

        # 95 % confidence interval using the t-distribution when n >= 2.
        if n >= 2:
            se = std / math.sqrt(n)
            t_crit = scipy.stats.t.ppf(0.975, df=n - 1)
            ci_low = mean - t_crit * se
            ci_high = mean + t_crit * se
        else:
            ci_low = mean
            ci_high = mean

        result[criterion] = {
            "mean": round(mean, 4),
            "median": round(median, 4),
            "std": round(std, 4),
            "ci_95_low": round(ci_low, 4),
            "ci_95_high": round(ci_high, 4),
            "n": n,
        }

    return result


def compute_rankings(
    df: pd.DataFrame,
    score_column: str = "composite_score",
) -> pd.DataFrame:
    """Rank experiment cells from best to worst by a score column.

    Args:
        df: DataFrame where each row represents one (cell_id, input_id) pair.
            Must contain ``cell_id`` and ``score_column`` columns.
        score_column: Column to rank by.  Defaults to ``composite_score``.

    Returns:
        DataFrame aggregated to one row per ``cell_id``, with columns for mean,
        median, std, min, max, count, and ``rank`` (1 = best).  Sorted
        ascending by rank.

    Raises:
        KeyError: If ``cell_id`` or ``score_column`` are absent from ``df``.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["cell_id", "mean", "median", "std", "min", "max", "count", "rank"]
        )

    if "cell_id" not in df.columns:
        raise KeyError("DataFrame must contain a 'cell_id' column.")
    if score_column not in df.columns:
        raise KeyError(f"DataFrame must contain '{score_column}' column.")

    grouped = (
        df.groupby("cell_id")[score_column]
        .agg(
            mean="mean",
            median="median",
            std="std",
            min="min",
            max="max",
            count="count",
        )
        .reset_index()
    )

    grouped["std"] = grouped["std"].fillna(0.0)
    grouped["rank"] = grouped["mean"].rank(ascending=False, method="min").astype(int)
    return grouped.sort_values("rank").reset_index(drop=True)


def compute_axis_effects(
    df: pd.DataFrame,
    axes: list[str],
) -> dict[str, Any]:
    """Compute mean composite score per level for each experimental axis.

    This is used to answer questions such as "which temperature performed best
    overall?" by marginalising over all other axes.

    Args:
        df: DataFrame with one row per result.  Must contain
            ``composite_score`` and one column per axis name listed in
            ``axes``.
        axes: List of column names that represent experimental axes (e.g.
            ``["template_id", "param_id", "model"]``).

    Returns:
        Dict mapping each axis name to a sub-dict of
        ``{level_value: mean_score}``, ordered from highest to lowest mean.
        A special ``best`` key holds the level with the highest mean score.
    """
    if df.empty or "composite_score" not in df.columns:
        return {}

    results: dict[str, Any] = {}
    for axis in axes:
        if axis not in df.columns:
            continue

        level_means: dict[str, float] = (
            df.groupby(axis)["composite_score"]
            .mean()
            .sort_values(ascending=False)
            .round(4)
            .to_dict()
        )

        best_level = next(iter(level_means)) if level_means else None
        results[axis] = {
            "levels": level_means,
            "best": best_level,
        }

    return results


def compute_composite_score(
    scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Compute a weighted average composite score from per-criterion scores.

    Criteria that appear in ``scores`` but not in ``weights`` are given an
    implicit weight of 1.0.  Criteria that appear in ``weights`` but not in
    ``scores`` are ignored.

    Args:
        scores: Mapping of criterion name to numeric score (typically 1-10).
        weights: Mapping of criterion name to positive weight.

    Returns:
        Weighted average as a float.  Returns 0.0 when ``scores`` is empty.

    Raises:
        ValueError: If any weight is negative or the total weight is zero.
    """
    if not scores:
        return 0.0

    if any(w < 0 for w in weights.values()):
        raise ValueError("All criterion weights must be non-negative.")

    total_weight = 0.0
    weighted_sum = 0.0

    for criterion, score in scores.items():
        weight = weights.get(criterion, 1.0)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0.0:
        raise ValueError("Total weight must be greater than zero.")

    return round(weighted_sum / total_weight, 4)

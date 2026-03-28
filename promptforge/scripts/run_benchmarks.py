#!/usr/bin/env python3
"""Benchmark the PromptForge skill.

Runs all eval test cases, captures timing and token-usage metrics, and writes
a snapshot to benchmarks/YYYY-MM-DD-HH-MM.json. Optionally compares against a
previous benchmark run to surface regressions and improvements.

Usage:
    python scripts/run_benchmarks.py
    python scripts/run_benchmarks.py --experiment experiments/2026-03-24-ecommerce-content-moderation/
    python scripts/run_benchmarks.py --compare benchmarks/2026-03-01-10-00.json
    python scripts/run_benchmarks.py --execute --compare benchmarks/previous.json
    python scripts/run_benchmarks.py --output benchmarks/custom-name.json
    python scripts/run_benchmarks.py --category plan
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency handling
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box as rich_box
    _RICH = True
except ImportError:
    _RICH = False

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BENCHMARKS_DIR = _PROJECT_ROOT / "benchmarks"
_SKILL_MD = _PROJECT_ROOT / "SKILL.md"

# Add scripts dir to path so we can import run_evals
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

try:
    from run_evals import run_evals, EvalSummary
except ImportError as exc:
    print(f"ERROR: Could not import run_evals: {exc}", file=sys.stderr)
    print("Make sure run_evals.py exists in scripts/ and PyYAML is installed.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError:
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _get_skill_version() -> str:
    """Extract skill version from SKILL.md front-matter, or fall back to mtime."""
    if not _SKILL_MD.exists():
        return "unknown"
    content = _SKILL_MD.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    # Use file modification date as a proxy version
    mtime = datetime.fromtimestamp(_SKILL_MD.stat().st_mtime, tz=timezone.utc)
    return f"mtime-{mtime.strftime('%Y%m%d')}"


def _read_token_usage(experiment_dir: Path | None) -> dict[str, int]:
    """Read aggregated token usage from execution_summary.yaml if available."""
    if experiment_dir is None:
        return {"input": 0, "output": 0}

    summary_path = experiment_dir / "execution_summary.yaml"
    summary = _load_yaml(summary_path)
    if not summary:
        return {"input": 0, "output": 0}

    tokens = summary.get("tokens", {})
    # Handle different possible key structures
    input_tokens = (
        tokens.get("total_input")
        or tokens.get("input")
        or summary.get("total_input_tokens", 0)
    )
    output_tokens = (
        tokens.get("total_output")
        or tokens.get("output")
        or summary.get("total_output_tokens", 0)
    )
    return {"input": int(input_tokens or 0), "output": int(output_tokens or 0)}


def _find_experiment_dir(base: Path) -> Path | None:
    """Return the most recently modified experiment subdirectory."""
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


def _timestamp() -> str:
    """Return current UTC time as YYYY-MM-DD-HH-MM string for filenames."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d-%H-%M")


def _iso_timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Benchmark result builder
# ---------------------------------------------------------------------------

def build_benchmark_result(
    summary: EvalSummary,
    elapsed_seconds: float,
    experiment_dir: Path | None,
    category_filter: str | None,
) -> dict[str, Any]:
    """Build the full benchmark result dictionary."""
    pass_rate = summary.passed / summary.total if summary.total > 0 else 0.0
    token_usage = _read_token_usage(experiment_dir)
    failed_tests = [
        {"id": r.id, "name": r.name, "category": r.category, "message": r.message}
        for r in summary.results
        if not r.passed and not r.skipped
    ]

    result: dict[str, Any] = {
        "timestamp": _iso_timestamp(),
        "skill_version": _get_skill_version(),
        "category_filter": category_filter,
        "experiment_dir": str(experiment_dir) if experiment_dir else None,
        "eval_pass_rate": round(pass_rate, 4),
        "total_evals": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "token_usage": token_usage,
        "failed_tests": failed_tests,
        "per_category": _per_category_stats(summary),
    }
    return result


def _per_category_stats(summary: EvalSummary) -> dict[str, Any]:
    """Compute pass/fail/skip counts per category."""
    stats: dict[str, dict[str, int]] = {}
    for r in summary.results:
        cat = r.category
        if cat not in stats:
            stats[cat] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
        stats[cat]["total"] += 1
        if r.skipped:
            stats[cat]["skipped"] += 1
        elif r.passed:
            stats[cat]["passed"] += 1
        else:
            stats[cat]["failed"] += 1
    return stats


# ---------------------------------------------------------------------------
# Comparison / diff
# ---------------------------------------------------------------------------

def _compare_benchmarks(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> dict[str, Any]:
    """Compute regressions and improvements between two benchmark runs."""
    # Build lookup sets from test IDs
    def _id_set(benchmark: dict[str, Any], outcome: str) -> set[str]:
        results = benchmark.get("failed_tests", []) if outcome == "failed" else []
        if outcome == "failed":
            return {t["id"] for t in results}
        # For "passed" we need to infer from total - failed - skipped
        return set()

    prev_failed_ids = {t["id"] for t in previous.get("failed_tests", [])}
    curr_failed_ids = {t["id"] for t in current.get("failed_tests", [])}

    # Tests that were passing before and are now failing
    regressions = curr_failed_ids - prev_failed_ids
    # Tests that were failing before and are now passing
    improvements = prev_failed_ids - curr_failed_ids

    prev_rate = previous.get("eval_pass_rate", 0)
    curr_rate = current.get("eval_pass_rate", 0)
    rate_delta = curr_rate - prev_rate

    prev_elapsed = previous.get("elapsed_seconds", 0)
    curr_elapsed = current.get("elapsed_seconds", 0)
    elapsed_delta = curr_elapsed - prev_elapsed

    # Token usage delta
    prev_tokens = previous.get("token_usage", {})
    curr_tokens = current.get("token_usage", {})
    token_delta = {
        "input": curr_tokens.get("input", 0) - prev_tokens.get("input", 0),
        "output": curr_tokens.get("output", 0) - prev_tokens.get("output", 0),
    }

    return {
        "previous_timestamp": previous.get("timestamp"),
        "current_timestamp": current.get("timestamp"),
        "pass_rate_delta": round(rate_delta, 4),
        "pass_rate_previous": prev_rate,
        "pass_rate_current": curr_rate,
        "elapsed_delta_seconds": round(elapsed_delta, 2),
        "token_delta": token_delta,
        "regressions": sorted(regressions),
        "improvements": sorted(improvements),
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _print_benchmark_rich(result: dict[str, Any], diff: dict[str, Any] | None) -> None:
    console = Console()

    console.print(f"\n[bold cyan]PromptForge Benchmark[/bold cyan]")
    console.print(f"Timestamp:     {result['timestamp']}")
    console.print(f"Skill version: {result['skill_version']}")
    if result.get("category_filter"):
        console.print(f"Category:      {result['category_filter']}")
    if result.get("experiment_dir"):
        console.print(f"Experiment:    {result['experiment_dir']}")

    console.print()

    # Summary table
    table = Table(box=rich_box.SIMPLE_HEAD, show_header=False, pad_edge=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Pass rate", f"{result['eval_pass_rate']*100:.1f}%")
    table.add_row("Total evals", str(result["total_evals"]))
    table.add_row("Passed", f"[green]{result['passed']}[/green]")
    table.add_row("Failed", f"[red]{result['failed']}[/red]")
    table.add_row("Skipped", f"[yellow]{result['skipped']}[/yellow]")
    table.add_row("Elapsed", f"{result['elapsed_seconds']:.1f}s")
    tokens = result.get("token_usage", {})
    if tokens.get("input") or tokens.get("output"):
        table.add_row(
            "Token usage",
            f"in={tokens.get('input', 0):,}  out={tokens.get('output', 0):,}",
        )
    console.print(table)

    # Per-category breakdown
    per_cat = result.get("per_category", {})
    if per_cat:
        console.print("\n[bold]Per-category results:[/bold]")
        cat_table = Table(box=rich_box.SIMPLE_HEAD)
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Total", justify="right")
        cat_table.add_column("Passed", justify="right")
        cat_table.add_column("Failed", justify="right")
        cat_table.add_column("Skipped", justify="right")
        cat_table.add_column("Rate", justify="right")
        for cat, stats in sorted(per_cat.items()):
            non_skipped = stats["total"] - stats["skipped"]
            rate = (stats["passed"] / non_skipped * 100) if non_skipped > 0 else 0
            rate_str = f"{rate:.0f}%"
            if stats["failed"] > 0:
                rate_str = f"[red]{rate_str}[/red]"
            elif non_skipped > 0:
                rate_str = f"[green]{rate_str}[/green]"
            cat_table.add_row(
                cat,
                str(stats["total"]),
                f"[green]{stats['passed']}[/green]",
                f"[red]{stats['failed']}[/red]" if stats["failed"] else "0",
                str(stats["skipped"]),
                rate_str,
            )
        console.print(cat_table)

    # Failed tests
    failed = result.get("failed_tests", [])
    if failed:
        console.print(f"\n[bold red]Failed tests ({len(failed)}):[/bold red]")
        for ft in failed:
            console.print(f"  [red]FAIL[/red]  {ft['id']}  {ft['message'][:80]}")

    # Diff output
    if diff:
        console.print("\n[bold]Comparison with previous run:[/bold]")
        console.print(f"  Previous:   {diff['previous_timestamp']}")

        rate_delta = diff["pass_rate_delta"]
        if rate_delta > 0:
            rate_str = f"[green]+{rate_delta*100:.1f}%[/green]"
        elif rate_delta < 0:
            rate_str = f"[red]{rate_delta*100:.1f}%[/red]"
        else:
            rate_str = "0.0% (no change)"
        console.print(f"  Pass rate:  {diff['pass_rate_previous']*100:.1f}% -> "
                      f"{diff['pass_rate_current']*100:.1f}%  ({rate_str})")

        if diff["regressions"]:
            console.print(
                f"\n  [bold red]Regressions ({diff['regression_count']}) "
                "— tests that newly failed:[/bold red]"
            )
            for test_id in diff["regressions"]:
                console.print(f"    [red]-[/red] {test_id}")

        if diff["improvements"]:
            console.print(
                f"\n  [bold green]Improvements ({diff['improvement_count']}) "
                "— tests that newly passed:[/bold green]"
            )
            for test_id in diff["improvements"]:
                console.print(f"    [green]+[/green] {test_id}")

        if not diff["regressions"] and not diff["improvements"]:
            console.print("  No regressions or improvements — results unchanged.")


def _print_benchmark_plain(result: dict[str, Any], diff: dict[str, Any] | None) -> None:
    print("\nPromptForge Benchmark")
    print(f"Timestamp:     {result['timestamp']}")
    print(f"Skill version: {result['skill_version']}")
    if result.get("category_filter"):
        print(f"Category:      {result['category_filter']}")

    print()
    print(f"Pass rate:  {result['eval_pass_rate']*100:.1f}%")
    print(f"Total:      {result['total_evals']}")
    print(f"Passed:     {result['passed']}")
    print(f"Failed:     {result['failed']}")
    print(f"Skipped:    {result['skipped']}")
    print(f"Elapsed:    {result['elapsed_seconds']:.1f}s")

    tokens = result.get("token_usage", {})
    if tokens.get("input") or tokens.get("output"):
        print(f"Tokens:     in={tokens.get('input', 0):,}  out={tokens.get('output', 0):,}")

    failed = result.get("failed_tests", [])
    if failed:
        print(f"\nFailed tests ({len(failed)}):")
        for ft in failed:
            print(f"  FAIL  {ft['id']}  {ft['message'][:80]}")

    if diff:
        print("\nComparison with previous run:")
        print(f"  Previous: {diff['previous_timestamp']}")
        rate_delta = diff["pass_rate_delta"]
        sign = "+" if rate_delta >= 0 else ""
        print(
            f"  Pass rate: {diff['pass_rate_previous']*100:.1f}% -> "
            f"{diff['pass_rate_current']*100:.1f}%  ({sign}{rate_delta*100:.1f}%)"
        )
        if diff["regressions"]:
            print(f"\n  Regressions ({diff['regression_count']}) — newly failing:")
            for test_id in diff["regressions"]:
                print(f"    - {test_id}")
        if diff["improvements"]:
            print(f"\n  Improvements ({diff['improvement_count']}) — newly passing:")
            for test_id in diff["improvements"]:
                print(f"    + {test_id}")
        if not diff["regressions"] and not diff["improvements"]:
            print("  No regressions or improvements — results unchanged.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the PromptForge skill and write results to benchmarks/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--experiment",
        type=Path,
        metavar="PATH",
        help="Path to experiment directory to validate (default: most recent)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        metavar="BENCHMARK_JSON",
        help="Path to a previous benchmark JSON to diff against",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Include tests that require pipeline execution",
    )
    parser.add_argument(
        "--category",
        metavar="CATEGORY",
        help="Run only tests in this category",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        help="Override the output file path (default: benchmarks/YYYY-MM-DD-HH-MM.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_stdout",
        help="Also print the full benchmark JSON to stdout",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Run benchmark but do not write to benchmarks/ directory",
    )
    args = parser.parse_args()

    # Resolve experiment directory
    experiment_dir = args.experiment
    if experiment_dir:
        if not experiment_dir.is_dir():
            print(f"ERROR: experiment directory not found: {experiment_dir}", file=sys.stderr)
            sys.exit(1)
    else:
        experiment_dir = _find_experiment_dir(_PROJECT_ROOT)

    # Load previous benchmark for comparison
    previous_benchmark: dict[str, Any] | None = None
    if args.compare:
        previous_benchmark = _load_json(args.compare)
        if previous_benchmark is None:
            print(
                f"WARNING: Could not load previous benchmark: {args.compare}",
                file=sys.stderr,
            )

    # Run evals
    t_start = time.perf_counter()
    summary = run_evals(
        category_filter=args.category,
        experiment_dir=experiment_dir,
        include_execution=args.execute,
    )
    elapsed = time.perf_counter() - t_start

    # Build result
    result = build_benchmark_result(
        summary=summary,
        elapsed_seconds=elapsed,
        experiment_dir=experiment_dir,
        category_filter=args.category,
    )

    # Compute diff
    diff: dict[str, Any] | None = None
    if previous_benchmark:
        diff = _compare_benchmarks(result, previous_benchmark)
        result["comparison"] = diff

    # Save to benchmarks/
    if not args.no_save:
        _BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = args.output or (_BENCHMARKS_DIR / f"{_timestamp()}.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)

        if not args.json_stdout:
            if _RICH:
                Console().print(f"\n[dim]Benchmark saved to:[/dim] {output_path}")
            else:
                print(f"\nBenchmark saved to: {output_path}")

    # Print results
    if args.json_stdout:
        print(json.dumps(result, indent=2))
    elif _RICH:
        _print_benchmark_rich(result, diff)
    else:
        _print_benchmark_plain(result, diff)

    # Exit code: 0 if no failures, 1 if any failed, 2 if regressions detected
    if diff and diff.get("regression_count", 0) > 0:
        sys.exit(2)
    elif summary.failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

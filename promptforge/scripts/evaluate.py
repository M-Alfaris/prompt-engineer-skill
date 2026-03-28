"""Evaluation engine — EVALUATE stage of the prompt engineering pipeline.

Reads raw results produced by run_experiment.py, scores each output using a
flexible multi-method system where each criterion can independently use one of
five methods: llm_judge, code, ground_truth, regex, or composite.  Writes
scored records and a statistical summary, then marks the pipeline stage
complete.

Evaluation methods
------------------
llm_judge
    Sends the output to a judge LLM with a scoring prompt.  Returns a 1-10
    score per criterion.  Best for subjective quality checks (relevance, tone,
    reasoning, completeness).

code
    Runs a Python function against the output.  Built-in checks (json_valid,
    json_schema, contains_expected, keywords_in_input, length_check) require no
    custom file.  Additional checks can be placed in
    ``experiments/{id}/custom_checks.py`` with the signature::

        def my_check(output: str, input_data: dict, expected: Any) -> float

    Returns 0.0-10.0.

ground_truth
    Compares the model output against an expected answer taken from the test
    input data.  Supports exact_match, contains, f1_token, jaccard, and
    semantic (falls back to llm_judge).  Scores 0-10.

regex
    Pattern match on output text.  Pass = 10, fail = 0.

composite
    Routes each criterion to its own method based on the ``method`` field in
    the criterion definition.  No more ``regex:`` naming hacks.

Auto-detection (method: "auto")
--------------------------------
When ``evaluation.method`` is ``"auto"`` or a criterion omits ``method``:

1. Criterion has ``check`` field        → ``code``
2. Criterion has ``comparison`` and ``expected_field`` → ``ground_truth``
3. Criterion description starts with ``pattern:`` → ``regex``
4. Otherwise                            → ``llm_judge``

Usage:
    python scripts/evaluate.py --experiment experiments/2026-03-24-foo/
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from scripts.utils.config import (
    EvaluationConfig,
    EvaluationCriterion,
    ExperimentConfig,
    load_experiment_config,
    load_yaml,
    save_yaml,
)
from scripts.utils.io import append_jsonl, read_jsonl, write_jsonl
from scripts.utils.providers import CompletionResult, get_provider
from scripts.utils.stats import (
    compute_axis_effects,
    compute_cell_stats,
    compute_composite_score,
    compute_rankings,
)

console = Console()

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """\
You are an expert evaluator for language model outputs.
You will be given a prompt and a model response.
Score the response on each criterion using an integer from 1 to 10.
Return ONLY a valid JSON object. Example:
{"clarity": 8, "accuracy": 7, "conciseness": 9, "reasoning": "brief note"}
Do NOT include markdown fences or any text outside the JSON object.\
"""

_JUDGE_USER_TEMPLATE = """\
## Original Prompt
{prompt}

## Model Response
{response}

## Scoring Criteria
{criteria_block}

Return a JSON object with one integer key per criterion (1-10) and an \
optional "reasoning" string key.\
"""

_SEMANTIC_JUDGE_SYSTEM = """\
You are an expert evaluator assessing semantic equivalence between two texts.
Return ONLY a valid JSON object with a single key "score" (integer 1-10) and
an optional "reasoning" key.  A score of 10 means fully equivalent meaning;
1 means completely different.
Do NOT include markdown fences or any text outside the JSON object.\
"""

_SEMANTIC_JUDGE_TEMPLATE = """\
## Expected Answer
{expected}

## Model Output
{output}

Are these semantically equivalent?  Score 1-10 and include brief reasoning.\
"""


def _build_criteria_block(criteria: list[EvaluationCriterion]) -> str:
    lines = []
    for c in criteria:
        lines.append(f"- **{c.name}** (weight {c.weight}): {c.description}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Auto-detection helper
# ---------------------------------------------------------------------------


def _resolve_criterion_method(criterion: EvaluationCriterion) -> str:
    """Return the concrete method name for a criterion.

    Resolution order:
    1. Explicit ``method`` field (if set and not ``"auto"``).
    2. Presence of ``check`` field → ``"code"``.
    3. Presence of both ``comparison`` and ``expected_field`` → ``"ground_truth"``.
    4. Description starting with ``"pattern:"`` → ``"regex"``.
    5. Default → ``"llm_judge"``.

    Args:
        criterion: The criterion whose method should be resolved.

    Returns:
        One of ``"llm_judge"``, ``"code"``, ``"ground_truth"``, ``"regex"``.
    """
    explicit = (criterion.method or "").lower()
    if explicit and explicit != "auto":
        return explicit

    if criterion.check:
        return "code"

    if criterion.comparison and criterion.expected_field:
        return "ground_truth"

    if (criterion.description or "").startswith("pattern:"):
        return "regex"

    return "llm_judge"


# ---------------------------------------------------------------------------
# LLM-judge scorer
# ---------------------------------------------------------------------------


async def _score_with_llm_judge(
    result_record: dict[str, Any],
    eval_config: EvaluationConfig,
    provider_cache: dict[str, Any],
    semaphore: asyncio.Semaphore,
    criteria_override: list[EvaluationCriterion] | None = None,
) -> tuple[dict[str, float], str]:
    """Call the judge model and return (scores_dict, reasoning).

    Scores dict maps criterion name -> float (1-10).  Reasoning is a short
    string extracted from the judge's JSON response or empty on failure.

    Args:
        result_record: A single raw result record.
        eval_config: Evaluation configuration containing judge model settings.
        provider_cache: Shared dict for reusing provider instances.
        semaphore: Concurrency limiter for API calls.
        criteria_override: If provided, score only these criteria instead of
            all criteria in ``eval_config``.

    Returns:
        Tuple of (scores_dict, reasoning_string).
    """
    criteria = criteria_override if criteria_override is not None else eval_config.criteria
    if not criteria:
        return {}, ""

    judge_config = eval_config.get_judge_model_config()
    judge_model = judge_config["name"]
    cache_key = (judge_config["provider"], judge_config.get("base_url", ""))

    if cache_key not in provider_cache:
        try:
            provider_cache[cache_key] = get_provider(judge_config)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Could not instantiate judge provider: {exc}[/]")
            return {}, ""

    provider = provider_cache[cache_key]
    criteria_block = _build_criteria_block(criteria)

    original_prompt = (
        result_record.get("input", {}).get("rendered_prompt")
        or json.dumps(result_record.get("input", {}))
    )
    response_text = result_record.get("output", "")

    user_content = _JUDGE_USER_TEMPLATE.format(
        prompt=original_prompt,
        response=response_text,
        criteria_block=criteria_block,
    )

    async with semaphore:
        try:
            completion: CompletionResult = await provider.complete(
                prompt=user_content,
                model=judge_model,
                temperature=0.0,
                max_tokens=512,
                system=_JUDGE_SYSTEM,
            )
            raw_text = completion.text.strip()
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[red]Judge API error for record "
                f"{result_record.get('cell_id')}/{result_record.get('input_id')}: {exc}[/]"
            )
            return {}, ""

    # Parse the JSON response from the judge.
    try:
        clean = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
        parsed: dict[str, Any] = json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group())
            except json.JSONDecodeError:
                console.print(
                    f"[yellow]Could not parse judge JSON for "
                    f"{result_record.get('cell_id')}: {raw_text[:120]}[/]"
                )
                return {}, raw_text
        else:
            return {}, raw_text

    reasoning = str(parsed.pop("reasoning", ""))

    criterion_names = {c.name for c in criteria}
    scores: dict[str, float] = {}
    for name in criterion_names:
        if name in parsed:
            try:
                scores[name] = float(parsed[name])
            except (TypeError, ValueError):
                scores[name] = 0.0

    return scores, reasoning


# ---------------------------------------------------------------------------
# Built-in code checks
# ---------------------------------------------------------------------------


def _builtin_json_valid(output: str, input_data: dict[str, Any], expected: Any) -> float:
    """Return 10.0 if output contains valid JSON, 0.0 otherwise.

    Searches for a ``{...}`` block inside the output before falling back to
    parsing the whole output string, so incidental surrounding text is
    tolerated.

    Args:
        output: Model output text.
        input_data: Original test input dict (unused).
        expected: Unused.

    Returns:
        10.0 if valid JSON is found, 0.0 otherwise.
    """
    try:
        match = re.search(r"\{.*\}", output, re.DOTALL)
        if match:
            json.loads(match.group())
            return 10.0
        json.loads(output.strip())
        return 10.0
    except (json.JSONDecodeError, ValueError):
        return 0.0


def _builtin_json_schema(output: str, input_data: dict[str, Any], expected: Any) -> float:
    """Check if output JSON contains all expected keys.

    Args:
        output: Model output text.
        input_data: Original test input dict (unused).
        expected: List of required key names, e.g. ``["keywords", "summary"]``.
            If not a list, simply checks that the output is a JSON object.

    Returns:
        Fraction of expected keys found, scaled to 0-10.
    """
    try:
        match = re.search(r"\{.*\}", output, re.DOTALL)
        parsed = json.loads(match.group()) if match else json.loads(output.strip())
        if not isinstance(expected, list):
            return 10.0 if isinstance(parsed, dict) else 0.0
        found = sum(1 for k in expected if k in parsed)
        return round((found / len(expected)) * 10, 1)
    except Exception:  # noqa: BLE001
        return 0.0


def _builtin_contains_expected(output: str, input_data: dict[str, Any], expected: Any) -> float:
    """Check if expected values appear in the output.

    Args:
        output: Model output text.
        input_data: Original test input dict (unused).
        expected: A string or list of strings to search for.

    Returns:
        Fraction of expected values found (case-insensitive), scaled to 0-10.
        Returns 5.0 when ``expected`` is empty or None.
    """
    if not expected:
        return 5.0
    if isinstance(expected, str):
        return 10.0 if expected.lower() in output.lower() else 0.0
    if isinstance(expected, list):
        found = sum(1 for e in expected if str(e).lower() in output.lower())
        return round((found / len(expected)) * 10, 1)
    return 5.0


def _builtin_keywords_in_input(output: str, input_data: dict[str, Any], expected: Any) -> float:
    """Verify that extracted keywords actually appear in the source text.

    Designed for keyword-extraction tasks: parses ``output`` as JSON, reads
    the ``keywords`` list, and checks each keyword against
    ``input_data["text"]``.

    Args:
        output: Model output text, expected to be JSON with a ``keywords`` key.
        input_data: Original test input dict containing the source ``"text"``.
        expected: Unused.

    Returns:
        Fraction of keywords found in the source text, scaled to 0-10.
        Returns 0.0 if output is not parseable or ``keywords`` list is empty.
    """
    input_text = (input_data.get("text", "") or "").lower()
    try:
        match = re.search(r"\{.*\}", output, re.DOTALL)
        parsed = json.loads(match.group()) if match else json.loads(output.strip())
        keywords = parsed.get("keywords", [])
        if not keywords:
            return 0.0
        in_text = sum(1 for k in keywords if str(k).lower() in input_text)
        return round((in_text / len(keywords)) * 10, 1)
    except Exception:  # noqa: BLE001
        return 0.0


def _builtin_length_check(output: str, input_data: dict[str, Any], expected: Any) -> float:
    """Check that output length falls within an expected range.

    Args:
        output: Model output text.
        input_data: Original test input dict (unused).
        expected: ``{"min": N, "max": M}`` dict (character counts).  When not
            a dict, returns 10.0 if output is non-empty, 0.0 otherwise.

    Returns:
        10.0 if within range, 0.0 if outside range.
    """
    length = len(output.strip())
    if isinstance(expected, dict):
        min_len = expected.get("min", 0)
        max_len = expected.get("max", float("inf"))
        return 10.0 if min_len <= length <= max_len else 0.0
    return 10.0 if length > 0 else 0.0


# Registry of built-in check functions keyed by check name.
_BUILTIN_CHECKS: dict[str, Any] = {
    "json_valid": _builtin_json_valid,
    "json_schema": _builtin_json_schema,
    "contains_expected": _builtin_contains_expected,
    "keywords_in_input": _builtin_keywords_in_input,
    "length_check": _builtin_length_check,
}

# ---------------------------------------------------------------------------
# Custom checks file loader
# ---------------------------------------------------------------------------

# Module-level cache so the custom checks file is only imported once per run.
_custom_checks_cache: dict[Path, ModuleType | None] = {}


def _load_custom_checks(experiment_dir: Path) -> ModuleType | None:
    """Import ``custom_checks.py`` from the experiment directory if it exists.

    Args:
        experiment_dir: Path to the experiment directory.

    Returns:
        The imported module, or ``None`` if the file does not exist.
    """
    checks_path = experiment_dir / "custom_checks.py"
    if checks_path in _custom_checks_cache:
        return _custom_checks_cache[checks_path]

    if not checks_path.exists():
        _custom_checks_cache[checks_path] = None
        return None

    spec = importlib.util.spec_from_file_location("custom_checks", checks_path)
    if spec is None or spec.loader is None:
        _custom_checks_cache[checks_path] = None
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Could not load custom_checks.py: {exc}[/]")
        _custom_checks_cache[checks_path] = None
        return None

    _custom_checks_cache[checks_path] = module
    return module


# ---------------------------------------------------------------------------
# Code scorer
# ---------------------------------------------------------------------------


def _score_with_code(
    result_record: dict[str, Any],
    criterion: EvaluationCriterion,
    experiment_dir: Path,
) -> float:
    """Run a built-in or custom check function against the model output.

    Looks up ``criterion.check`` first in the built-in registry, then in the
    custom checks module loaded from ``experiment_dir/custom_checks.py``.

    Args:
        result_record: A single raw result record.
        criterion: The criterion being evaluated; ``criterion.check`` names the
            function to call and ``criterion.expected`` is forwarded as the
            third argument.
        experiment_dir: Path used to locate ``custom_checks.py``.

    Returns:
        Float score in the range 0.0-10.0.
    """
    check_name = criterion.check or ""
    output = result_record.get("output", "")
    input_data = result_record.get("input", {})
    expected = criterion.expected

    # 1. Built-in checks.
    if check_name in _BUILTIN_CHECKS:
        try:
            score = _BUILTIN_CHECKS[check_name](output, input_data, expected)
            return float(max(0.0, min(10.0, score)))
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[yellow]Built-in check '{check_name}' raised an error: {exc}[/]"
            )
            return 0.0

    # 2. Custom checks file.
    custom_module = _load_custom_checks(experiment_dir)
    if custom_module is not None and hasattr(custom_module, check_name):
        fn = getattr(custom_module, check_name)
        try:
            score = fn(output, input_data, expected)
            return float(max(0.0, min(10.0, score)))
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"[yellow]Custom check '{check_name}' raised an error: {exc}[/]"
            )
            return 0.0

    console.print(
        f"[yellow]Check '{check_name}' not found in built-ins or custom_checks.py — "
        f"scoring 0 for criterion '{criterion.name}'.[/]"
    )
    return 0.0


# ---------------------------------------------------------------------------
# Ground-truth comparison helpers
# ---------------------------------------------------------------------------


def _ground_truth_exact_match(output: str, expected: str) -> float:
    """Return 10.0 when output equals expected (case-insensitive, stripped).

    Args:
        output: Model output text.
        expected: Reference answer.

    Returns:
        10.0 for a match, 0.0 otherwise.
    """
    return 10.0 if output.strip().lower() == expected.strip().lower() else 0.0


def _ground_truth_contains(output: str, expected: str) -> float:
    """Return 10.0 when expected is a substring of output (case-insensitive).

    Args:
        output: Model output text.
        expected: Reference answer or phrase.

    Returns:
        10.0 if found, 0.0 otherwise.
    """
    return 10.0 if expected.strip().lower() in output.strip().lower() else 0.0


def _extract_items(text: str | list | Any) -> set[str]:
    """Extract comparable items from a value — handles strings, lists, and JSON.

    If text is a list: uses each item as-is (lowercased).
    If text is a JSON string containing a list or {"keywords": [...]}: parses and extracts items.
    Otherwise: splits on whitespace as fallback.
    """
    if isinstance(text, list):
        return {str(item).lower().strip() for item in text if item}

    text_str = str(text).strip()

    # Try parsing as JSON
    try:
        parsed = json.loads(text_str)
        if isinstance(parsed, list):
            return {str(item).lower().strip() for item in parsed if item}
        if isinstance(parsed, dict):
            # Check common keys: keywords, items, results, answers, labels
            for key in ("keywords", "items", "results", "answers", "labels", "entities", "tags"):
                if key in parsed and isinstance(parsed[key], list):
                    return {str(item).lower().strip() for item in parsed[key] if item}
            # If dict has no list values, use all values
            return {str(v).lower().strip() for v in parsed.values() if v}
    except (json.JSONDecodeError, TypeError):
        pass

    # Try finding JSON inside the text
    match = re.search(r'\{[^{}]*\}', text_str, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                for key in ("keywords", "items", "results", "answers", "labels", "entities", "tags"):
                    if key in parsed and isinstance(parsed[key], list):
                        return {str(item).lower().strip() for item in parsed[key] if item}
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: split on whitespace
    return {t for t in text_str.lower().split() if t}


def _ground_truth_f1_token(output: str, expected: str) -> float:
    """Compute F1 score between output and expected, scaled to 0-10.

    Smart about data types: if output/expected contain JSON keyword arrays,
    compares the actual keyword items instead of raw text tokens.
    """
    out_items = _extract_items(output)
    exp_items = _extract_items(expected)
    if not exp_items:
        return 10.0
    # Also check for fuzzy containment (e.g., "cloud computing" matches "cloud computing services")
    common = set()
    for exp in exp_items:
        for out in out_items:
            if exp in out or out in exp:
                common.add(exp)
                break
    if not common:
        return 0.0
    precision = len(common) / len(out_items) if out_items else 0.0
    recall = len(common) / len(exp_items)
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    )
    return round(f1 * 10, 1)


def _ground_truth_jaccard(output: str, expected: str) -> float:
    """Compute Jaccard similarity between output and expected, scaled to 0-10.

    Smart about data types: if output/expected contain JSON keyword arrays,
    compares the actual keyword items instead of raw text tokens.
    """
    out_items = _extract_items(output)
    exp_items = _extract_items(expected)
    if not out_items and not exp_items:
        return 10.0
    # Fuzzy matching: count items that overlap (substring containment)
    matched_out = set()
    matched_exp = set()
    for exp in exp_items:
        for out in out_items:
            if exp in out or out in exp:
                matched_out.add(out)
                matched_exp.add(exp)
    total_unique = len(out_items | exp_items)
    total_matched = len(matched_out | matched_exp)
    return round((total_matched / total_unique) * 10, 1) if total_unique else 0.0


# ---------------------------------------------------------------------------
# Ground-truth scorer
# ---------------------------------------------------------------------------


async def _score_with_ground_truth(
    result_record: dict[str, Any],
    criterion: EvaluationCriterion,
    eval_config: EvaluationConfig,
    provider_cache: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> float:
    """Compare model output against the expected answer from test input data.

    Reads the expected answer from ``result_record["input"][criterion.expected_field]``
    and applies the comparison mode specified by ``criterion.comparison``.

    Supported comparison modes: ``exact_match``, ``contains``, ``f1_token``,
    ``jaccard``, ``semantic`` (falls back to llm_judge).

    Args:
        result_record: A single raw result record.
        criterion: Criterion with ``expected_field`` and ``comparison`` set.
        eval_config: Evaluation config used when falling back to llm_judge for
            semantic comparison.
        provider_cache: Shared provider instance cache.
        semaphore: Concurrency limiter.

    Returns:
        Float score in the range 0.0-10.0.
    """
    expected_field = criterion.expected_field or ""
    input_data = result_record.get("input", {})
    expected_value = input_data.get(expected_field)

    if expected_value is None:
        console.print(
            f"[yellow]Ground-truth field '{expected_field}' not found in input for "
            f"criterion '{criterion.name}' — scoring 0.[/]"
        )
        return 0.0

    expected_str = str(expected_value)
    output = result_record.get("output", "")
    comparison = (criterion.comparison or "exact_match").lower()

    if comparison == "exact_match":
        return _ground_truth_exact_match(output, expected_str)
    elif comparison == "contains":
        return _ground_truth_contains(output, expected_str)
    elif comparison == "f1_token":
        return _ground_truth_f1_token(output, expected_str)
    elif comparison == "jaccard":
        return _ground_truth_jaccard(output, expected_str)
    elif comparison == "semantic":
        # Use the judge LLM to assess semantic equivalence.
        judge_config = eval_config.get_judge_model_config()
        judge_model = judge_config["name"]
        cache_key = (judge_config["provider"], judge_config.get("base_url", ""))

        if cache_key not in provider_cache:
            try:
                provider_cache[cache_key] = get_provider(judge_config)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Could not instantiate judge provider: {exc}[/]")
                return 0.0

        provider = provider_cache[cache_key]
        user_content = _SEMANTIC_JUDGE_TEMPLATE.format(
            expected=expected_str, output=output
        )

        async with semaphore:
            try:
                completion: CompletionResult = await provider.complete(
                    prompt=user_content,
                    model=judge_model,
                    temperature=0.0,
                    max_tokens=256,
                    system=_SEMANTIC_JUDGE_SYSTEM,
                )
                raw_text = completion.text.strip()
            except Exception as exc:  # noqa: BLE001
                console.print(
                    f"[red]Semantic judge API error for criterion '{criterion.name}': {exc}[/]"
                )
                return 0.0

        try:
            clean = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            clean = re.sub(r"\s*```$", "", clean)
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw_text, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}

        try:
            return float(max(0.0, min(10.0, parsed.get("score", 0.0))))
        except (TypeError, ValueError):
            return 0.0
    else:
        console.print(
            f"[yellow]Unknown ground_truth comparison mode '{comparison}' for "
            f"criterion '{criterion.name}' — defaulting to exact_match.[/]"
        )
        return _ground_truth_exact_match(output, expected_str)


# ---------------------------------------------------------------------------
# Regex scorer
# ---------------------------------------------------------------------------


def _score_with_regex(
    result_record: dict[str, Any],
    criteria: list[EvaluationCriterion],
) -> tuple[dict[str, float], str]:
    """Apply regex checks defined in criteria.

    Each criterion must carry its pattern in the ``description`` field as
    ``pattern:<regex>``.  A successful search scores 10; no match scores 0.

    Args:
        result_record: A single raw result record.
        criteria: List of criteria to evaluate with regex.

    Returns:
        Tuple of (scores_dict, reasoning_string).
    """
    output = result_record.get("output", "")
    scores: dict[str, float] = {}
    notes: list[str] = []

    for criterion in criteria:
        raw_desc = criterion.description or ""
        if raw_desc.startswith("pattern:"):
            pattern = raw_desc[len("pattern:"):]
        else:
            pattern = raw_desc

        if not pattern:
            scores[criterion.name] = 0.0
            notes.append(f"{criterion.name}: no pattern defined")
            continue

        try:
            matched = bool(re.search(pattern, output))
        except re.error as exc:
            console.print(
                f"[yellow]Invalid regex for criterion '{criterion.name}': {exc}[/]"
            )
            matched = False

        scores[criterion.name] = 10.0 if matched else 0.0
        notes.append(
            f"{criterion.name}: {'pass' if matched else 'fail'} (pattern={pattern!r})"
        )

    return scores, " | ".join(notes)


# ---------------------------------------------------------------------------
# Score dispatcher
# ---------------------------------------------------------------------------


async def _score_record(
    result_record: dict[str, Any],
    eval_config: EvaluationConfig,
    experiment_dir: Path,
    provider_cache: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Dispatch each criterion to its appropriate scoring method.

    When ``eval_config.method`` is ``"composite"`` or ``"auto"``, criteria are
    routed individually.  Otherwise the top-level method is applied to all
    criteria that do not carry their own explicit ``method`` override.

    Args:
        result_record: A single raw result from ``results/*.jsonl``.
        eval_config: Evaluation configuration from ``plan.yaml``.
        experiment_dir: Experiment root used to locate ``custom_checks.py``.
        provider_cache: Shared dict for reusing provider instances.
        semaphore: Concurrency limiter for LLM judge calls.

    Returns:
        Score record containing ``cell_id``, ``input_id``, ``scores``,
        ``composite_score``, and ``judge_reasoning``.
    """
    top_method = eval_config.method.lower()
    all_criteria = eval_config.criteria

    scores: dict[str, float] = {}
    reasoning_parts: list[str] = []

    # Group criteria by the method that will handle them.
    # For per-criterion routing (composite / auto) each criterion is
    # resolved independently; for single-method modes every criterion
    # uses the top-level method unless it has its own override.
    per_criterion_routing = top_method in ("composite", "auto")

    # Buckets populated during routing.
    llm_criteria: list[EvaluationCriterion] = []
    regex_criteria: list[EvaluationCriterion] = []
    code_criteria: list[EvaluationCriterion] = []
    ground_truth_criteria: list[EvaluationCriterion] = []

    for criterion in all_criteria:
        if per_criterion_routing:
            method = _resolve_criterion_method(criterion)
        else:
            # Single-method mode: honour explicit per-criterion override if
            # set, otherwise use the top-level method.
            explicit = (criterion.method or "").lower()
            if explicit and explicit != "auto":
                method = explicit
            else:
                method = top_method

        if method == "llm_judge":
            llm_criteria.append(criterion)
        elif method == "regex":
            regex_criteria.append(criterion)
        elif method == "code":
            code_criteria.append(criterion)
        elif method == "ground_truth":
            ground_truth_criteria.append(criterion)
        else:
            # Unknown methods default to llm_judge with a warning.
            console.print(
                f"[yellow]Unknown method '{method}' for criterion "
                f"'{criterion.name}' — defaulting to llm_judge.[/]"
            )
            llm_criteria.append(criterion)

    # --- LLM judge batch (one API call for all llm_judge criteria) ----------
    if llm_criteria:
        j_scores, j_reasoning = await _score_with_llm_judge(
            result_record,
            eval_config,
            provider_cache,
            semaphore,
            criteria_override=llm_criteria,
        )
        scores.update(j_scores)
        if j_reasoning:
            reasoning_parts.append(f"judge: {j_reasoning}")

    # --- Regex (synchronous, no I/O) ----------------------------------------
    if regex_criteria:
        r_scores, r_notes = _score_with_regex(result_record, regex_criteria)
        scores.update(r_scores)
        if r_notes:
            reasoning_parts.append(f"regex: {r_notes}")

    # --- Code checks (synchronous, no I/O) ----------------------------------
    for criterion in code_criteria:
        score = _score_with_code(result_record, criterion, experiment_dir)
        scores[criterion.name] = score

    # --- Ground-truth (may call LLM for semantic mode) ----------------------
    gt_tasks = [
        _score_with_ground_truth(
            result_record, criterion, eval_config, provider_cache, semaphore
        )
        for criterion in ground_truth_criteria
    ]
    if gt_tasks:
        gt_results = await asyncio.gather(*gt_tasks, return_exceptions=True)
        for criterion, result in zip(ground_truth_criteria, gt_results):
            if isinstance(result, Exception):
                console.print(
                    f"[yellow]Ground-truth check failed for '{criterion.name}': {result}[/]"
                )
                scores[criterion.name] = 0.0
            else:
                scores[criterion.name] = float(result)

    weights = {c.name: c.weight for c in all_criteria}
    composite = compute_composite_score(scores, weights) if scores else 0.0

    return {
        "cell_id": result_record.get("cell_id", "unknown"),
        "input_id": result_record.get("input_id", "unknown"),
        "template_id": result_record.get("template_id", ""),
        "param_id": result_record.get("param_id", ""),
        "model": result_record.get("model", ""),
        "model_id": result_record.get("model_id", result_record.get("model", "")),
        "provider": result_record.get("provider", ""),
        "scores": scores,
        "composite_score": composite,
        "judge_reasoning": " | ".join(reasoning_parts),
        "cost_usd": result_record.get("cost_usd", 0.0),
        "latency_ms": result_record.get("latency_ms", 0.0),
        "ttft_ms": result_record.get("ttft_ms"),
        "tokens_in": result_record.get("tokens_in", 0),
        "tokens_out": result_record.get("tokens_out", 0),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Default custom_checks.py template
# ---------------------------------------------------------------------------

_DEFAULT_CUSTOM_CHECKS = '''\
"""Custom evaluation checks for this experiment.

Each function must match the signature:

    def check_name(output: str, input_data: dict, expected) -> float

Return a float in the range 0.0 (worst) to 10.0 (best).

Reference the built-ins already available without this file:
    json_valid, json_schema, contains_expected, keywords_in_input, length_check
"""

from __future__ import annotations

import json
import re
from typing import Any


def example_custom_check(output: str, input_data: dict, expected: Any) -> float:
    """Replace this with your own logic.

    Args:
        output: The model\'s raw output string.
        input_data: The original test-case input dict.
        expected: The value from the criterion\'s ``expected`` field in plan.yaml.

    Returns:
        Score between 0.0 and 10.0.
    """
    # Example: reward non-empty output.
    return 10.0 if output.strip() else 0.0
'''


def _ensure_custom_checks_file(experiment_dir: Path) -> None:
    """Write a default ``custom_checks.py`` if none exists.

    Args:
        experiment_dir: Path to the experiment directory.
    """
    checks_path = experiment_dir / "custom_checks.py"
    if not checks_path.exists():
        checks_path.write_text(_DEFAULT_CUSTOM_CHECKS)
        console.print(
            f"[dim]Created default custom_checks.py at {checks_path}[/]"
        )


# ---------------------------------------------------------------------------
# Main evaluation driver
# ---------------------------------------------------------------------------


async def evaluate_experiment(experiment_dir: Path) -> None:
    """Load results, score every record, and write evaluations/ artefacts.

    Args:
        experiment_dir: Path to the experiment directory.

    Raises:
        FileNotFoundError: If ``plan.yaml`` or the results directory are absent.
    """
    experiment_dir = experiment_dir.resolve()
    plan_path = experiment_dir / "plan.yaml"

    if not plan_path.exists():
        raise FileNotFoundError(f"plan.yaml not found at {plan_path}")

    console.rule("[bold blue]PromptForge Evaluator[/]")
    console.print(f"Experiment: [cyan]{experiment_dir.name}[/]")

    config: ExperimentConfig = load_experiment_config(experiment_dir)
    eval_config: EvaluationConfig = config.evaluation

    console.print(f"Method     : {eval_config.method}")
    console.print(f"Criteria   : {[c.name for c in eval_config.criteria]}")

    # Generate a default custom_checks.py if any criterion uses "code" method
    # and the file is missing — makes it easy for users to extend.
    needs_code = eval_config.method.lower() in ("composite", "auto") or any(
        _resolve_criterion_method(c) == "code" for c in eval_config.criteria
    )
    if needs_code:
        _ensure_custom_checks_file(experiment_dir)

    # ------------------------------------------------------------------
    # Gather all raw result records
    # ------------------------------------------------------------------
    results_dir = experiment_dir / "results"
    if not results_dir.exists():
        raise FileNotFoundError(
            f"results/ directory not found at {results_dir}. "
            "Run run_experiment.py first."
        )

    all_records: list[dict[str, Any]] = []
    for jsonl_path in sorted(results_dir.glob("*.jsonl")):
        try:
            all_records.extend(read_jsonl(jsonl_path))
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]Could not read {jsonl_path}: {exc}[/]")

    if not all_records:
        console.print("[yellow]No result records found — nothing to evaluate.[/]")
        return

    console.print(f"Records    : {len(all_records)} to evaluate")

    # ------------------------------------------------------------------
    # Score each record
    # ------------------------------------------------------------------
    evals_dir = experiment_dir / "evaluations"
    evals_dir.mkdir(parents=True, exist_ok=True)
    scores_path = evals_dir / "scores.jsonl"

    # Truncate any prior scores file so we write a clean slate.
    scores_path.write_text("")

    provider_cache: dict[str, Any] = {}
    semaphore = asyncio.Semaphore(config.execution.max_concurrent)

    scored_records: list[dict[str, Any]] = []

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

    async def _score_and_persist(
        record: dict[str, Any],
        task_id: Any,
    ) -> None:
        score_record = await _score_record(
            record, eval_config, experiment_dir, provider_cache, semaphore
        )
        append_jsonl(scores_path, score_record)
        scored_records.append(score_record)
        progress.advance(task_id)

    with progress:
        task_id = progress.add_task("Scoring records…", total=len(all_records))
        await asyncio.gather(
            *[_score_and_persist(r, task_id) for r in all_records],
            return_exceptions=True,
        )

    console.print(f"Scores written to [cyan]{scores_path}[/]")

    # ------------------------------------------------------------------
    # Statistical summary
    # ------------------------------------------------------------------
    df = pd.DataFrame(scored_records)

    # Rankings
    rankings_df = compute_rankings(df, score_column="composite_score")
    rankings_list = rankings_df.to_dict(orient="records")

    # Per-axis effects
    axis_columns = [
        col
        for col in ["template_id", "param_id", "model", "provider"]
        if col in df.columns
    ]
    axis_effects = compute_axis_effects(df, axes=axis_columns)

    # Per-cell detailed stats
    cell_stats: dict[str, Any] = {}
    for cell_id, group in df.groupby("cell_id"):
        group_records = group.to_dict(orient="records")
        shaped = [
            {
                "scores": rec.get("scores", {}),
                "composite_score": rec.get("composite_score", 0.0),
            }
            for rec in group_records
        ]
        cell_stats[str(cell_id)] = compute_cell_stats(shaped)

    # Overall best combination
    best_cell: str = rankings_list[0]["cell_id"] if rankings_list else "n/a"
    best_score: float = float(rankings_list[0]["mean"]) if rankings_list else 0.0

    summary: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_method": eval_config.method,
        "total_records": len(all_records),
        "total_scored": len(scored_records),
        "best_cell": best_cell,
        "best_mean_composite_score": round(best_score, 4),
        "rankings": rankings_list,
        "axis_effects": axis_effects,
        "cell_stats": cell_stats,
    }

    # Convert numpy types to native Python (numpy.float64 -> float, etc.)
    # so YAML serializes cleanly without tagged objects.
    def _to_native(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _to_native(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_native(v) for v in obj]
        if hasattr(obj, "item"):  # numpy scalar
            return obj.item()
        return obj

    summary = _to_native(summary)

    summary_path = evals_dir / "summary.yaml"
    save_yaml(summary_path, summary)
    console.print(f"Summary written to [cyan]{summary_path}[/]")

    # ------------------------------------------------------------------
    # Update state.yaml
    # ------------------------------------------------------------------
    state_path = experiment_dir / "state.yaml"
    state: dict[str, Any] = load_yaml(state_path) if state_path.exists() else {}
    state["EVALUATE"] = "completed"
    state["evaluate_completed_at"] = summary["evaluated_at"]
    save_yaml(state_path, state)

    # ------------------------------------------------------------------
    # Display rankings table
    # ------------------------------------------------------------------
    table = Table(title="Cell Rankings (top 10)", show_header=True)
    table.add_column("Rank", justify="right")
    table.add_column("Cell ID")
    table.add_column("Mean Score", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("N", justify="right")

    for row in rankings_list[:10]:
        table.add_row(
            str(row["rank"]),
            str(row["cell_id"]),
            f"{row['mean']:.3f}",
            f"{row.get('std', 0.0):.3f}",
            str(row["count"]),
        )

    console.print(table)

    # ------------------------------------------------------------------
    # Display per-axis best levels
    # ------------------------------------------------------------------
    if axis_effects:
        axis_table = Table(title="Best Level per Axis", show_header=True)
        axis_table.add_column("Axis")
        axis_table.add_column("Best Level")
        axis_table.add_column("Mean Score", justify="right")

        for axis, info in axis_effects.items():
            best_level = info.get("best", "n/a")
            best_level_score = info.get("levels", {}).get(best_level, 0.0)
            axis_table.add_row(axis, str(best_level), f"{best_level_score:.3f}")

        console.print(axis_table)

    console.print(
        f"\n[bold green]Best overall:[/] {best_cell} "
        f"(mean composite score: {best_score:.4f})"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evaluate",
        description="Evaluate experiment outputs and produce ranked summaries.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        type=Path,
        metavar="DIR",
        help="Path to the experiment directory (must contain plan.yaml and results/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — parses args and drives the async evaluator."""
    args = _parse_args(argv)

    try:
        asyncio.run(evaluate_experiment(args.experiment))
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()

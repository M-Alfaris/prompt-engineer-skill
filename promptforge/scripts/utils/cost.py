"""Token cost calculation.

Pricing can be sourced from two places (in priority order):

1. **Dynamic** — a ``model_config`` dict passed directly to
   :func:`calculate_cost`, containing ``cost_per_million_input`` and
   ``cost_per_million_output`` fields.  This lets the research / planning phase
   discover and record pricing at experiment-design time without requiring a
   central config update.

2. **Static fallback** — ``configs/default_config.yaml``, under the
   ``cost_per_1k_tokens`` key.  This is the original behaviour and remains
   the fallback for any model not covered by a dynamic config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.utils.config import load_yaml

_COST_TABLE: dict[str, dict[str, float]] | None = None


def _load_cost_table() -> dict[str, dict[str, float]]:
    """Load and cache the static pricing table from ``default_config.yaml``.

    Returns:
        Mapping of model name → ``{"input": float, "output": float}`` dicts.
    """
    global _COST_TABLE
    if _COST_TABLE is None:
        config_path = (
            Path(__file__).parent.parent.parent / "configs" / "default_config.yaml"
        )
        config = load_yaml(config_path)
        _COST_TABLE = config.get("cost_per_million_tokens", {}) or config.get("cost_per_1k_tokens", {})
    return _COST_TABLE


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    model_config: dict[str, Any] | None = None,
) -> float:
    """Calculate the USD cost for a single API call.

    Pricing resolution order:

    1. If *model_config* supplies both ``cost_per_million_input`` and
       ``cost_per_million_output``, those values are used directly.
    2. Otherwise the static ``configs/default_config.yaml`` table is
       consulted by model name.
    3. If neither source has pricing for the model, ``0.0`` is returned so
       that missing pricing never blocks experiment execution.

    Args:
        model: Model identifier (e.g. ``"gpt-4o"`` or
            ``"meta-llama/Llama-4-70b"``).  Used only for the static-table
            lookup; ignored when *model_config* provides dynamic pricing.
        input_tokens: Number of prompt / input tokens consumed.
        output_tokens: Number of completion / output tokens generated.
        model_config: Optional model configuration dict.  When present and it
            contains ``cost_per_million_input`` and ``cost_per_million_output`` float
            fields, those override the static table entirely.

    Returns:
        Estimated cost in USD, rounded to six decimal places.
        Returns ``0.0`` when no pricing information is available.
    """
    # 1. Dynamic pricing from model_config.
    if model_config is not None:
        dynamic_input = model_config.get("cost_per_million_input")
        dynamic_output = model_config.get("cost_per_million_output")
        if dynamic_input is not None and dynamic_output is not None:
            input_cost = (input_tokens / 1_000_000) * float(dynamic_input)
            output_cost = (output_tokens / 1_000_000) * float(dynamic_output)
            return round(input_cost + output_cost, 6)

    # 2. Static table fallback.
    table = _load_cost_table()
    costs = table.get(model)
    if costs is None:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * costs.get("input", 0.0)
    output_cost = (output_tokens / 1_000_000) * costs.get("output", 0.0)
    return round(input_cost + output_cost, 6)

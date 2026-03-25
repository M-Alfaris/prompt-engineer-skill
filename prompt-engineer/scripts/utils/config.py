"""Configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return as dict."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Save a dict to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


class BudgetConfig(BaseModel):
    max_cost_usd: float = 10.0
    max_api_calls: int = 1000
    warn_at_usd: float | None = None


class EvaluationCriterion(BaseModel):
    """A single scored dimension of an evaluation plan.

    Attributes:
        name: Unique criterion identifier used as the score dict key.
        description: Human-readable description sent to LLM judges or used
            as a regex pattern when prefixed with ``pattern:``.
        weight: Relative weight in the composite score (default 1.0).
        method: Explicit evaluation method — one of ``"llm_judge"``,
            ``"code"``, ``"ground_truth"``, or ``"regex"``.  When ``None``
            the dispatcher auto-detects the method from the other fields.
        check: Built-in or custom check function name used with
            ``method="code"``.  Examples: ``"json_valid"``,
            ``"keywords_in_input"``.
        comparison: Comparison mode for ``method="ground_truth"``.  One of
            ``"exact_match"``, ``"contains"``, ``"f1_token"``,
            ``"jaccard"``, or ``"semantic"``.
        expected_field: Name of the field in the test input dict that holds
            the ground-truth answer (e.g. ``"expected_decision"``).
        expected: Static expected value passed directly to code checks such
            as ``"json_schema"`` (list of required keys) or
            ``"length_check"`` (``{"min": N, "max": M}`` dict).
    """

    name: str
    description: str
    weight: float = 1.0
    method: str | None = None
    check: str | None = None
    comparison: str | None = None
    expected_field: str | None = None
    expected: Any = None


class JudgeModelConfig(BaseModel):
    """Full provider config for the evaluation judge model."""

    name: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    base_url: str | None = None
    api_key_env: str | None = None


class EvaluationConfig(BaseModel):
    method: str = "llm_judge"
    judge_model: str | dict[str, Any] = "claude-sonnet-4-20250514"
    criteria: list[EvaluationCriterion] = Field(default_factory=list)

    def get_judge_model_config(self) -> dict[str, Any]:
        """Return judge model as a dict suitable for get_provider()."""
        if isinstance(self.judge_model, dict):
            return self.judge_model
        # Backward-compatible: infer provider from model name prefix
        name = self.judge_model
        if name.startswith("claude"):
            return {"provider": "anthropic", "name": name}
        elif name.startswith("gpt"):
            return {
                "provider": "openai",
                "name": name,
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            }
        elif name.startswith("gemini"):
            return {"provider": "google", "name": name}
        else:
            return {"provider": "anthropic", "name": name}


class ParameterSet(BaseModel):
    """A named set of inference parameters to test in the matrix.

    Only ``id``, ``temperature``, ``max_tokens``, and ``top_p`` are typed fields.
    Everything else is accepted as-is and passed through to the provider API.

    This means the research phase can discover ANY parameter for ANY provider
    and include it in a parameter set without code changes. Examples:

        - id: "json-deterministic"
          temperature: 0.0
          max_tokens: 512
          json_mode: true           # OpenAI, Groq
          seed: 42                  # OpenAI, Groq

        - id: "thinking-mode"
          temperature: 0.0
          max_tokens: 4096
          thinking: true            # Anthropic
          thinking_budget: 2000     # Anthropic

        - id: "creative-penalized"
          temperature: 0.8
          max_tokens: 512
          top_k: 40                 # Anthropic, Google
          frequency_penalty: 0.5    # OpenAI, Groq
          repeat_penalty: 1.2       # Ollama

        - id: "custom-provider-params"
          temperature: 0.3
          max_tokens: 512
          some_future_param: "value" # any param, any provider
    """
    model_config = {"extra": "allow"}  # Pydantic: accept any field not listed below

    id: str
    temperature: float = 0.5
    max_tokens: int = 512
    top_p: float = 1.0


class ModelConfig(BaseModel):
    """Configuration for a single model axis entry in a plan.

    Attributes:
        id: Short identifier used to label matrix cells
            (e.g. ``"gpt4o"``).
        name: Full model identifier forwarded to the provider API
            (e.g. ``"gpt-4o"`` or ``"meta-llama/Llama-4-70b"``).
        provider: Provider routing key.  Use ``"anthropic"`` or
            ``"google"`` for those native SDKs; any other value
            (``"openai"``, ``"together"``, ``"fireworks"``, ``"groq"``,
            ``"ollama"``, ``"local"``, ``"vllm"``, or a custom name)
            routes to :class:`OpenAICompatibleProvider`.
        base_url: Base URL of the OpenAI-compatible API endpoint.
            Required for every provider except ``"anthropic"`` and
            ``"google"``.  Examples:

            * OpenAI   — ``https://api.openai.com/v1``
            * Together — ``https://api.together.xyz/v1``
            * Ollama   — ``http://localhost:11434/v1``
        api_key_env: Name of the environment variable that holds the
            API key for this provider.  Set to ``None`` for local
            unauthenticated endpoints.
        cost_per_million_input: Optional input-token price in USD per 1 000
            tokens.  When set, overrides the static pricing table in
            ``default_config.yaml``.
        cost_per_million_output: Optional output-token price in USD per 1 000
            tokens.  When set alongside ``cost_per_million_input``, overrides
            the static pricing table.
    """

    id: str
    name: str
    provider: str
    base_url: str | None = None
    api_key_env: str | None = None
    cost_per_million_input: float | None = None
    cost_per_million_output: float | None = None


class TemplateRef(BaseModel):
    id: str
    file: str


class ExperimentAxes(BaseModel):
    templates: list[TemplateRef] = Field(default_factory=list)
    parameters: list[ParameterSet] = Field(default_factory=list)
    models: list[ModelConfig] = Field(default_factory=list)


class ExecutionConfig(BaseModel):
    strategy: str = "full"
    repetitions: int = 3
    randomize_order: bool = True
    max_concurrent: int = 5


class ExperimentConfig(BaseModel):
    experiment_id: str
    name: str = ""
    description: str = ""
    goal: dict[str, str] = Field(default_factory=dict)
    axes: ExperimentAxes = Field(default_factory=ExperimentAxes)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)


def load_experiment_config(experiment_dir: Path) -> ExperimentConfig:
    """Load and validate an experiment's plan.yaml."""
    plan_path = experiment_dir / "plan.yaml"
    raw = load_yaml(plan_path)

    # Flatten nested structure if present
    flat: dict[str, Any] = {}
    if "experiment" in raw:
        flat["experiment_id"] = raw["experiment"]["id"]
        flat["name"] = raw["experiment"].get("name", "")
        flat["description"] = raw["experiment"].get("description", "")
    else:
        flat["experiment_id"] = raw.get("experiment_id", experiment_dir.name)

    flat["goal"] = raw.get("goal", {})
    flat["axes"] = raw.get("axes", {})
    flat["evaluation"] = raw.get("evaluation", {})
    flat["execution"] = raw.get("execution", {})
    flat["budget"] = raw.get("budget", {})

    return ExperimentConfig(**flat)

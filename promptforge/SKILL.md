---
name: promptforge
description: Systematic prompt engineering experimentation framework that tests massive combinations of prompt templates, parameters, and LLM models to discover the optimal formula for any task. Make sure to use this skill whenever the user mentions prompt optimization, prompt testing, prompt comparison, A/B testing prompts, finding the best model, benchmarking models, prompt experiments, testing different prompt strategies, improving prompt quality, comparing few-shot vs zero-shot, testing prompt variations, or evaluating LLM performance — even if they don't explicitly say "experiment" or "matrix." Also trigger when users want to test multiple models on the same task, find the cheapest model that still works, or systematically improve any AI-powered feature. Supports full factorial, fractional, and adaptive matrix strategies with LLM-as-judge evaluation, budget tracking, and structured JSON output for dashboards.
---

# PromptForge

Autonomous experimentation pipeline. User provides a goal — the skill researches current LLMs, prompt techniques, and domain context, then runs a combinatorial experiment to find the winning formula.

---

## Where Files Go

**EVERYTHING is created in the user's project directory** (current working directory). Nothing is hidden in the skill folder. The user sees all files in their project:

```
{user's project}/
  .env                         # API keys (user creates from .env.example)
  requirements.txt             # Python deps (copied from skill if not present)
  experiments/
    2026-03-25-keyword-extraction/
      state.yaml               # Pipeline progress
      research_brief.md        # What was discovered
      plan.yaml                # What will be tested
      templates/*.yaml         # The prompt variants
      data/test_inputs.yaml    # Test data
      matrix.yaml              # All combinations
      results/*.jsonl          # Every API call (input + output + tokens + cost)
      all_results.jsonl        # Consolidated for analysis
      execution_summary.yaml   # Total cost, calls, errors
      evaluations/
        scores.jsonl           # Every score per criterion
        summary.yaml           # Rankings and axis effects
      report.md                # Final report
      report_data.json         # Dashboard data
      winner.yaml              # Production-ready winning prompt
      winner.json              # Same, JSON
```

The scripts live inside the skill folder (read-only). They are called with full paths. All output goes to the user's project.

---

## Pipeline

1. **RESEARCH** — Read `references/phase-research.md`. Web search for LLMs, techniques, domain context. Ingest everything the user provides.
2. **PLAN** — Read `references/phase-plan.md`. Assemble axes from research. Show cost estimate. **Wait for user approval.**
3. **BUILD** — Read `references/phase-build.md`. Create templates + test data. **Decide execution mode** (see below).
4. **MATRIX → EXECUTE → EVALUATE** — Run scripts or custom code depending on execution mode.
5. **REPORT** — Read `references/phase-report.md`. Present winning prompt with scores and cost analysis.

Load ONLY the phase file for the current stage. Unload before advancing.

---

## Setup (first time in a project)

Before running any experiment, ensure the user's project has:

1. **requirements.txt** — copy from this skill if not present, then `pip install -r requirements.txt`
2. **.env** — copy `.env.example` from this skill, user fills in their API keys
3. **scripts/** — copy the entire `scripts/` folder from this skill into the user's project (so scripts run from the project root)

This only happens once per project. After setup, all commands run from the user's project root.

---

## Execution Mode Decision (during BUILD)

### Standard mode — use the bundled scripts
Use when inputs are **text-only or multi-field text** (vast majority of cases).

```bash
python scripts/generate_matrix.py --experiment experiments/{id}/
python scripts/run_experiment.py --experiment experiments/{id}/
python scripts/evaluate.py --experiment experiments/{id}/
# or all at once:
python scripts/run_pipeline.py --experiment experiments/{id}/
```

### Adapted mode — for non-text inputs
Use when inputs involve **vision, tool calling, multi-turn conversations, or file processing**.

Read `references/input-types.md` for the exact API formats. Write a custom execution script in the experiment folder. It outputs the same JSONL format so EVALUATE and REPORT work unchanged.

| Input type | Mode | What to do |
|-----------|------|------------|
| Text → text | Standard | Run scripts |
| Multi-field text (RAG) | Standard | Templates use multiple `{{ variables }}` |
| Image + text | Adapted | Read `references/input-types.md` |
| Tool calling | Adapted | Read `references/input-types.md` |
| Multi-turn conversation | Adapted | Read `references/input-types.md` |
| File inputs (PDF, CSV) | Standard | Extract text during BUILD |

---

## Quick Start

**Required:** A goal (one sentence enough)
**Optional:** Preferred LLMs, prompt types, budget, existing prompts or template folder, prior results, test data, domain docs

```
> "Optimize content moderation prompts for my e-commerce platform."
> "Find the best prompt for data extraction. Use Claude and GPT-4o. Budget: $15."
> "Test 5 models on keyword extraction. Use Groq."
> "I have templates in prompts/ — find the best variations. Budget: $20."
> "Classify these images into categories. Use vision models."
```

1. Setup: copy scripts/, requirements.txt, .env.example to user's project (first time only)
2. Create `experiments/YYYY-MM-DD-slug/` in the user's project root, init `state.yaml`
3. Research autonomously — look things up, don't ask questions
4. Ingest everything the user provided (prompts, data, docs, prior results)
5. After PLAN, pause: "N templates x N params x N models = N cells, ~$X"
6. After approval, BUILD → MATRIX → EXECUTE → EVALUATE → REPORT automatically
7. Present the winning prompt with scores, cost analysis, and deployment recommendation

---

## Scripts

```bash
# Full pipeline
python scripts/run_pipeline.py --experiment experiments/{id}/
python scripts/run_pipeline.py --experiment experiments/{id}/ --dry-run
python scripts/run_pipeline.py --experiment experiments/{id}/ --from EVALUATE

# Individual stages
python scripts/generate_matrix.py --experiment experiments/{id}/
python scripts/run_experiment.py --experiment experiments/{id}/
python scripts/evaluate.py --experiment experiments/{id}/

# Utilities
python scripts/validate.py --experiment experiments/{id}/
python scripts/preview_prompt.py --experiment experiments/{id}/ --template t01 --input input_001
python scripts/export_winner.py --experiment experiments/{id}/
python scripts/generate_report.py --experiment experiments/{id}/
```

All scripts support `--json` for structured output.

---

## Key Concepts

**Provider routing** — Any LLM with an OpenAI-compatible API works. Models specify `base_url` and `api_key_env` in plan.yaml. Anthropic and Google use native SDKs; everything else routes through the OpenAI-compatible provider.

**Budget safety** — Hard ceiling in `plan.yaml budget.max_cost_usd`. Every call logs tokens, cost, latency. Script stops when ceiling hit.

**Evaluation methods** — Each criterion uses its own method (read `references/phase-evaluate.md`):
- `llm_judge` — subjective quality
- `code` — deterministic checks (JSON valid, keywords in text)
- `ground_truth` — compare against expected answers (exact match, F1, Jaccard)
- `regex` — pattern matching

**Per-model parameters** — json_mode, top_k, thinking, frequency_penalty, seed, etc. are only sent to models that support them. Research phase discovers each model's supported parameters.

---

## Progressive Disclosure

- Load ONLY the current phase file. Unload before advancing.
- `references/input-types.md` — load when inputs involve images, tools, conversations, or files
- `references/prompt-methodologies.md`, `references/llm-notes.md` — fallbacks when web search fails
- `references/workflow-iterative.md` — "iterate", "refine", "improve"
- `references/workflow-fast-test.md` — "quick test", "smoke test"

---

## State & Resume

`experiments/{id}/state.yaml` tracks progress. Resume from `current_stage` if interrupted.

---

## Environment

Python 3.10+. `.env` with API keys. `configs/default_config.yaml` for rate limits and concurrency.

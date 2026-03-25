---
name: prompt-engineer
description: Systematic prompt engineering experimentation framework that tests massive combinations of prompt templates, parameters, and LLM models to discover the optimal formula for any task. Make sure to use this skill whenever the user mentions prompt optimization, prompt testing, prompt comparison, A/B testing prompts, finding the best model, benchmarking models, prompt experiments, testing different prompt strategies, improving prompt quality, comparing few-shot vs zero-shot, testing prompt variations, or evaluating LLM performance — even if they don't explicitly say "experiment" or "matrix." Also trigger when users want to test multiple models on the same task, find the cheapest model that still works, or systematically improve any AI-powered feature. Supports full factorial, fractional, and adaptive matrix strategies with LLM-as-judge evaluation, budget tracking, and structured JSON output for dashboards.
---

# Prompt Engineer

Autonomous experimentation pipeline. User provides a goal — the skill researches current LLMs, prompt techniques, and domain context, then runs a combinatorial experiment to find the winning formula.

---

## Pipeline

1. **RESEARCH** — Read `references/phase-research.md`. Web search for LLMs, techniques, domain context. Ingest everything the user provides (existing prompts, prior results, templates, domain docs, test data, golden answers).
2. **PLAN** — Read `references/phase-plan.md`. Assemble axes from research. Show cost estimate. **Wait for user approval.**
3. **BUILD** — Read `references/phase-build.md`. Create templates + test data. **Decide execution mode** (see below).
4. **MATRIX → EXECUTE → EVALUATE** — Run scripts or custom code depending on execution mode.
5. **REPORT** — Read `references/phase-report.md`. Present winning prompt with scores and cost analysis.

Load ONLY the phase file for the current stage. Unload before advancing.

---

## Execution Mode Decision (critical — make this during BUILD)

After creating templates and test data, determine which execution path to use:

### Standard mode — use the bundled scripts
Use when inputs are **text-only or multi-field text** (the vast majority of cases).

```bash
python scripts/generate_matrix.py --experiment experiments/{id}/
python scripts/run_experiment.py --experiment experiments/{id}/
python scripts/evaluate.py --experiment experiments/{id}/
# or all at once:
python scripts/run_pipeline.py --experiment experiments/{id}/
```

The standard scripts handle: any number of LLMs (via OpenAI-compatible API), any text-based templates with Jinja2 variables, budget enforcement, rate limiting, token tracking, LLM-judge + code + ground_truth evaluation.

### Adapted mode — for non-text inputs
Use when inputs involve **vision, tool calling, multi-turn conversations, or file processing**.

Read `references/input-types.md` — it has the exact API formats for each provider and input type. Use it to write a custom execution script during BUILD. The custom script outputs the same JSONL format, so EVALUATE and REPORT work unchanged.

**Decision table:**

| Input type | Mode | What to do |
|-----------|------|------------|
| Text prompt → text response | Standard | Run the scripts |
| Multiple text fields (RAG: context + query) | Standard | Templates use multiple `{{ variables }}` |
| Image + text | Adapted | Read `references/input-types.md` for provider image formats |
| Tool calling | Adapted | Read `references/input-types.md` for tool definition formats |
| Multi-turn conversation | Adapted | Read `references/input-types.md` for message array format |
| File inputs (PDF, CSV) | Standard | Extract file content to text during BUILD, then standard pipeline |

---

## Quick Start

**Required from user:** A goal (one sentence enough)
**Optional:** Preferred LLMs, prompt types, budget, existing prompts, prior experiment results, test data, domain docs, golden answers

```
> "Optimize content moderation prompts for my e-commerce platform."
> "Find the best prompt for data extraction. Use Claude and GPT-4o. Budget: $15."
> "Test 5 models on keyword extraction. Use Groq."
> "I have these prompts that aren't working well — test variations and find the best one."
```

1. Create `experiments/YYYY-MM-DD-slug/`, init `state.yaml`
2. Research autonomously — don't ask the user questions, look things up
3. Ingest everything the user provided (prompts, data, docs, prior results)
4. After PLAN, pause and show: "N templates x N params x N models = N cells, ~$X"
5. After approval, BUILD → decide execution mode → MATRIX → EXECUTE → EVALUATE → REPORT
6. Present the winning prompt with scores, cost analysis, and deployment recommendation

---

## Bundled Scripts

```bash
# Full pipeline (standard mode)
python scripts/run_pipeline.py --experiment experiments/{id}/
python scripts/run_pipeline.py --experiment experiments/{id}/ --dry-run    # cost preview
python scripts/run_pipeline.py --experiment experiments/{id}/ --from EVALUATE  # resume

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

**Extended parameters** — `json_mode`, `top_k`, `frequency_penalty`, `presence_penalty`, `thinking`, `thinking_budget`, `seed`, `stop_sequences`. Research phase discovers which each model supports.

---

## Progressive Disclosure

- Load ONLY the current phase file. Unload before advancing.
- `references/input-types.md` — load when inputs involve images, tools, conversations, or files
- `references/prompt-methodologies.md`, `references/llm-notes.md` — fallbacks when web search fails
- `references/workflow-iterative.md` — "iterate", "refine", "improve"
- `references/workflow-fast-test.md` — "quick test", "smoke test"

---

## State, Environment, Output

**State:** `experiments/{id}/state.yaml` tracks progress. Resume from `current_stage` if interrupted.

**Environment:** Python 3.10+, `pip install -r requirements.txt`, `.env` with API keys.

**Output:**
```
experiments/{id}/
  state.yaml              research_brief.md       plan.yaml
  templates/*.yaml        data/test_inputs.yaml   matrix.yaml
  results/*.jsonl          all_results.jsonl       execution_summary.yaml
  evaluations/scores.jsonl evaluations/summary.yaml
  report.md               report_data.json        winner.yaml  winner.json
```

# Phase: Research

## Purpose

Autonomous intelligence-gathering engine. The user provides a goal (and optionally: preferred LLMs, prompt types, budget, existing prompts, test data). This phase discovers everything else via web research: current LLMs with APIs and pricing, up-to-date prompt engineering techniques and strategies, domain-specific context, and best practices. The output is a rich research brief that all downstream phases consume.

## Input from User

Extract everything the user provides. Do NOT ask for things they didn't mention — research it instead.

- **Goal** (required): The task to optimize prompts for. One sentence is enough.
- **Preferred LLMs** (optional): Lock these in. Skip model research for specified models.
- **Preferred prompt types** (optional): Include these. Still research additional ones.
- **Budget** (optional): Default $10.
- **Existing prompts** (optional): Analyze strengths, weaknesses, technique used. Use as a baseline template.
- **Test data** (optional): Use if provided. Otherwise generate in BUILD phase.
- **Previous experiment results** (optional): If user shares a prior report.md, summary.yaml, or scores.jsonl — read them. Extract: which combos won, which failed, what the scores were. Use this to narrow the search space (don't re-test known losers).
- **Existing templates** (optional): If user provides .yaml template files, ingest them as-is. Add them to the template axis alongside new ones.
- **Domain docs** (optional): API docs, style guides, company policies, schemas. Include in the research brief for the BUILD phase to reference when writing templates.
- **Example outputs** (optional): If user shares good/bad examples, use them to calibrate evaluation criteria and few-shot examples.
- **Golden answers dataset** (optional): If user provides a Q&A dataset with correct answers, route evaluation to `ground_truth` method.

## Detecting Input Complexity

Before researching, identify the input type. This determines what the pipeline needs to support:

**Text-only inputs** (default): Single text string per test input. Standard pipeline works as-is.

**Multi-field inputs** (e.g., RAG context + query): Multiple text fields per test input. Templates use multiple variables (`{{ context }}`, `{{ query }}`). Test data needs all fields. The pipeline handles this — just define variables in templates and matching fields in test data.

**Image + text inputs** (vision): Requires vision-capable models (GPT-4o, Claude Sonnet/Opus, Gemini). The standard scripts don't send image content blocks — Claude should write a custom `run_experiment.py` variant or `custom_checks.py` that handles image encoding. Note this in the research brief so BUILD phase adapts.

**Tool calling** (function definitions): Requires tool-capable models. The standard scripts don't send tool definitions — Claude should write a custom execution script that includes `tools` parameter. Note this in the research brief.

**Multi-turn conversations**: Requires conversation history. The standard scripts send single system+user turn. Claude should write a custom execution script that sends multi-turn message arrays. Note this in the research brief.

**File inputs** (PDF, CSV, images): Claude should read/process files during BUILD to extract content into the test data YAML, or write a custom execution script that handles file embedding.

When non-standard input types are detected, add a section to the research brief:

```markdown
## Input Complexity
Type: {text_only | multi_field | vision | tool_calling | multi_turn | file_input}
Custom execution needed: {yes/no}
What to customize: {description of what run_experiment.py needs to handle differently}
```

The BUILD phase reads this and either uses the standard pipeline or writes custom scripts.

Do NOT ask a long list of questions. If the goal is clear, start researching immediately. Only ask if the goal itself is ambiguous.

## Steps

### 0. Check Available API Keys

Before researching any models, read the `.env` file to see which providers the user has access to:

```bash
cat .env
```

This determines which models and judges you can recommend. Read `references/input-types.md` "Step 0" for the full key-to-provider mapping. Only recommend models from providers the user has keys for. Also read `references/input-types.md` "Picking the Judge Model" and "Parameter-Provider Compatibility" — you'll need this info when writing the research brief.

### 1. Research Current LLM Landscape

**Skip this step ONLY if the user locked in specific models.**

Use `WebSearch` to discover currently available LLMs, their capabilities, pricing, and API access. **Only research models from providers the user has API keys for** (from Step 0):

**Search queries:**
- "best LLM models {current_year} comparison pricing API"
- "Claude vs GPT vs Gemini {current_year} benchmark"
- "{task_domain} best LLM model to use"
- "LLM API pricing comparison {current_year}"

**For each discovered model, record these fields (required by plan.yaml):**

```yaml
- id: "sonnet"
  name: "claude-sonnet-4-20250514"
  provider: "anthropic"
  base_url: null                             # null for native SDK providers
  api_key_env: "ANTHROPIC_API_KEY"
  cost_per_million_input: 3.00
  cost_per_million_output: 15.00
  context_window: 200000
  strengths: "strong reasoning, low cost"
  best_for: "classification, analysis"
  supported_params:                          # REQUIRED — what this model supports
    - temperature
    - max_tokens
    - top_p
    - top_k
    - stop_sequences
    - thinking
    - thinking_budget
```

**The `supported_params` field is critical.** It tells the PLAN phase which parameters can be tested on this model. Research each model's API docs or search "{model_name} API parameters" to fill this accurately. The PLAN phase uses this to create per-model parameter sets — parameters are NOT applied uniformly across all models.

**IMPORTANT — Provider routing:**
- `"anthropic"` = uses Anthropic SDK (unique API)
- `"google"` = uses Google GenAI SDK (unique API)
- Everything else (including `"openai"`, `"together"`, `"fireworks"`, `"groq"`, `"ollama"`, `"vllm"`, any custom) = uses OpenAI-compatible SDK with the specified `base_url`

**Search for provider documentation:**
- "Anthropic Claude API documentation"
- "OpenAI API documentation"
- "Google Gemini API documentation"
- "{provider_name} API documentation OpenAI compatible"
- "{provider_name} base URL endpoint"
- "{model_name} API pricing per token"

Record the base_url, API key env var name, and pricing per million tokens. These flow directly into plan.yaml and the execution engine uses them.

**Discover as many viable models as possible across tiers. More models = more signal. The user's budget determines how many make it into the plan — your job is to surface options, not pre-filter:**
- Budget tier (fast, cheap): e.g., Haiku, GPT-4o-mini, Gemini Flash
- Balanced tier (good quality/cost): e.g., Sonnet, GPT-4o, Gemini Pro
- Premium tier (best quality): e.g., Opus, o3, o4-mini

### 2. Research Prompt Engineering Techniques

Use `WebSearch` to find the latest prompt engineering techniques, strategies, and frameworks:

**Search queries:**
- "prompt engineering techniques {current_year}"
- "best prompt strategies for {task_type}" (e.g., "best prompt strategies for classification")
- "prompt engineering research papers {current_year}"
- "{task_domain} prompt engineering best practices"
- "system prompt vs user prompt best practices"
- "few-shot vs zero-shot vs chain-of-thought when to use"

**For each discovered technique, record:**

```
Technique: {name}
How it works: {1-2 sentence description}
When to use: {task types and conditions}
Prompt setup: {system prompt structure, user prompt structure, example count if few-shot}
Strengths: {what it improves}
Weaknesses: {cost, latency, failure modes}
Source: {URL where found}
```

**Also research prompt setup strategies:**
- System prompt vs user prompt — what goes where
- Instruction ordering — does order matter for this model?
- Output format enforcement — JSON mode, schema enforcement, format instructions
- Temperature and sampling — what settings work for this task type
- Token limits — how max_tokens affects quality

**Fallback:** If web search is unavailable or insufficient, read `references/prompt-methodologies.md`.

### 3. Research Domain-Specific Context

Use `WebSearch` to understand the specific domain of the user's task:

**Search queries:**
- "{task_domain} industry standards"
- "{task_domain} common edge cases"
- "{task_domain} input output format"
- "{task_domain} LLM use cases examples"
- "{task_domain} evaluation metrics"

**Gather:**
- What input formats are standard in this domain
- What output formats are expected
- Common edge cases and failure modes
- How quality is typically measured
- Any regulatory or compliance requirements

**Apply task-type research pattern:**

| Task Type | Research Focus |
|-----------|---------------|
| Classification | Label definitions, decision boundaries, borderline cases, FP/FN tradeoffs |
| Generation | Tone standards, length expectations, hallucination risks, style constraints |
| Extraction | Schema standards, field definitions, handling missing/malformed data |
| Reasoning | Error patterns, CoT effectiveness, verification criteria |
| Multi-step | Action space, failure recovery, timeout conditions |

### 4. Research Parameter Strategies

Use `WebSearch` to find recommended parameter settings for this task type:

**Search queries:**
- "best temperature setting for {task_type} LLM"
- "LLM temperature top_p settings {task_domain}"
- "deterministic vs creative LLM output {task_type}"
- "{provider_name} API parameters reference"
- "json mode structured output {provider_name}"

**Record recommended ranges for core parameters:**
- Temperature: what range works best for this task type
- top_p: whether to vary or fix
- max_tokens: minimum needed for expected output

**Also discover extended parameters per provider:**
- `json_mode`: Does the provider support JSON output mode? (OpenAI, Groq → response_format: json_object)
- `top_k`: Available on Anthropic, Google, Ollama
- `frequency_penalty` / `presence_penalty`: Available on OpenAI, Groq
- `thinking` / `thinking_budget`: Available on Anthropic Claude (extended thinking mode)
- `seed`: Available on OpenAI, Groq (for reproducibility)
- `stop_sequences`: Supported by most providers

Record which extended parameters each discovered model supports. These go into plan.yaml parameter sets so the matrix can test them.

**Parameter set examples with extended params:**
```yaml
parameters:
  - id: "deterministic"
    temperature: 0.0
    max_tokens: 512
    json_mode: true       # force JSON output
  - id: "with-thinking"
    temperature: 0.0
    max_tokens: 1024
    thinking: true         # Anthropic extended thinking
    thinking_budget: 500
  - id: "diverse"
    temperature: 0.7
    max_tokens: 512
    top_k: 40
    frequency_penalty: 0.3
```

### 5. Analyze Existing Prompts (if provided)

If the user shared existing prompts:
- Identify what technique(s) the prompt uses
- Assess strengths and weaknesses
- Flag injection risks, ambiguous instructions, missing constraints
- Note what to preserve vs what to experiment with

### 6. Produce the Research Brief

Write `experiments/{id}/research_brief.md`. This is the MASTER DOCUMENT that all downstream phases read. It must be comprehensive.

```markdown
# Research Brief: {task name}

## Task Definition
One precise paragraph describing what the model must do.

## Task Type
{classification | generation | extraction | reasoning | multi-step}

## Inputs
- Format: {free text | JSON | structured form | etc.}
- Examples: {2-3 realistic input examples}
- Edge cases: {list discovered edge cases}

## Outputs
- Format: {paragraph | JSON | bullet list | code | etc.}
- Schema: {exact output schema if structured}
- Validation rules: {what makes output valid/invalid}
- Examples of ideal output: {2-3 examples}

## Success Criteria
Measurable criteria. Each must be testable.
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Constraints
- Content: {forbidden topics, required disclaimers}
- Latency: {max response time if applicable}
- Cost: {budget per query in production, experiment budget}
- Schema: {strict schema compliance requirements}
- Regulatory: {compliance requirements if any}

## Current State (if applicable)
- Existing prompt analysis: {strengths, weaknesses}
- Known issues: {what's failing}

---

## Discovered LLM Models

### Budget Tier
| Model | Provider | base_url | api_key_env | $/1M in | $/1M out | Context | Best For |
|-------|----------|----------|-------------|---------|----------|---------|----------|
| ... | ... | ... | ... | ... | ... | ... | ... |

### Balanced Tier
| Model | Provider | base_url | api_key_env | $/1M in | $/1M out | Context | Best For |
|-------|----------|----------|-------------|---------|----------|---------|----------|
| ... | ... | ... | ... | ... | ... | ... | ... |

### Premium Tier
| Model | Provider | base_url | api_key_env | $/1M in | $/1M out | Context | Best For |
|-------|----------|----------|-------------|---------|----------|---------|----------|
| ... | ... | ... | ... | ... | ... | ... | ... |

### Per-Model Parameter Support

For EACH recommended model, document exactly which parameters it supports. This drives the PLAN phase to create per-model parameter sets.

```
Model: llama-3.1-8b-instant (Groq)
  Supported: temperature, max_tokens, top_p, json_mode, seed, frequency_penalty, presence_penalty, stop
  NOT supported: thinking, thinking_budget, top_k

Model: claude-sonnet-4-20250514 (Anthropic)
  Supported: temperature, max_tokens, top_p, top_k, stop_sequences, thinking, thinking_budget
  NOT supported: json_mode (use tool_use instead), frequency_penalty, presence_penalty, seed

Model: gpt-4o (OpenAI)
  Supported: temperature, max_tokens, top_p, json_mode, seed, frequency_penalty, presence_penalty, stop
  NOT supported: thinking, thinking_budget, top_k
```

This information MUST be in the research brief because the PLAN phase reads it to create model-specific parameter sets. If you skip this, parameters will be applied to models that don't support them, causing API errors.

### Recommended Models for This Task
{Recommend all models worth testing. Include every model the user has API access for that could plausibly perform this task. The budget determines how many run — don't pre-limit here.}

---

## Discovered Prompt Techniques

For each technique discovered (list all that are relevant):

### {Technique Name}
- **How it works:** {description}
- **Prompt setup:** {system prompt structure, user prompt structure}
- **Why it fits this task:** {justification}
- **Expected cost impact:** {low/medium/high token overhead}
- **Source:** {URL}

### Recommended Techniques for This Task
{Recommend all techniques worth testing for this task, with one-sentence justification each. Include user-specified techniques plus all research-discovered ones that are relevant. More techniques = more signal — the budget determines how many run.}

---

## Recommended Parameter Strategy

| Parameter | Values to Test | Rationale |
|-----------|---------------|-----------|
| temperature | {e.g., 0.0, 0.3, 0.7} | {why these values} |
| max_tokens | {e.g., 256, 512} | {based on expected output size} |
| top_p | {e.g., 1.0} | {whether to vary} |

---

## Test Data Strategy

{If user provided test data: "User provided test data at {path}. Use as-is."}
{If no test data: "Generate test data in BUILD phase. Include:
- {N} easy cases (clear-cut expected behavior)
- {N} hard cases (ambiguous, requires nuance)
- {N} edge cases (adversarial, unusual formats, boundary conditions)
Specific edge cases to include: {list based on domain research}"}

## Open Questions
{Only if something genuinely blocks progress. Otherwise: "None — sufficient to proceed."}
```

## Output

`experiments/{id}/research_brief.md`

## Handoff

Print a one-paragraph summary: task type, number of discovered models, number of discovered techniques, recommended parameter ranges. Immediately proceed to PLAN phase.

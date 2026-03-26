# Phase: Plan

## Purpose

Translate the research brief into an executable experiment plan. The research brief already contains discovered models, techniques, parameter strategies, and domain context. This phase assembles them into axes and validates the matrix fits within budget.

## Steps

### 1. Read the Research Brief

Read `experiments/{id}/research_brief.md`. Extract:
- **Recommended models** from "Discovered LLM Models" section
- **Recommended techniques** from "Discovered Prompt Techniques" section
- **Parameter strategy** from "Recommended Parameter Strategy" section
- **Success criteria** and **output format** for evaluation design
- **Test data strategy** — user-provided or needs generation
- **Budget** from constraints

### 2. Define Template Axis (from Research)

For each recommended technique in the research brief, define one template variant:
- Assign a short ID: `t01-{technique}` (e.g., `t01-zero-shot`, `t02-few-shot-5`, `t03-cot`)
- Templates are created in the BUILD phase. Record only IDs and filenames here.
- Include all user-specified techniques plus research-discovered ones

### 3. Define Model Axis (from Research)

Use the models from the research brief's "Recommended Models for This Task" section:
- If user specified models, use those (already in the research brief)
- If research-discovered, include the recommended 3-5 models
- Each entry needs: id, full model name, provider

### 4. Define Parameter Axis (Per-Model, Not Generalized)

Read the research brief's "Per-Model Parameter Support" section. Create parameter sets that are **compatible with each model** — do not apply parameters a model doesn't support.

**Approach: shared core + model-specific extras**

1. Define **core parameter sets** using only universally-supported params (temperature, max_tokens, top_p):
   ```yaml
   - id: "deterministic"
     temperature: 0.0
     max_tokens: 512
   - id: "creative"
     temperature: 0.7
     max_tokens: 512
   ```

2. For each model that supports extra params, create **model-specific parameter sets** that include both core + extras:
   ```yaml
   - id: "groq-json-deterministic"
     temperature: 0.0
     max_tokens: 512
     json_mode: true        # Groq supports this
     seed: 42               # Groq supports this
     applicable_models: ["llama-8b", "llama-70b"]  # only these

   - id: "anthropic-thinking"
     temperature: 0.0
     max_tokens: 2048
     thinking: true          # only Anthropic
     thinking_budget: 1024   # only Anthropic
     applicable_models: ["sonnet"]  # only this
   ```

3. The matrix generator will cross each parameter set with only its `applicable_models` (if specified) or all models (if not specified). This prevents json_mode from being sent to models that don't support it.

If all models are from the same provider (e.g., all Groq), you can use the same parameter sets for all — just make sure the params are supported by that provider.

### 5. Design Evaluation Criteria

Derive evaluation criteria from the research brief's success criteria:
- Map each success criterion to a scoreable evaluation criterion (1-10 scale)
- Assign weights that reflect the user's priorities (accuracy usually highest)
- For classification tasks: always include decision_accuracy and false_positive_safety
- For generation tasks: always include relevance and format_compliance
- For extraction tasks: always include schema_compliance and field_accuracy
- Weights must sum to 1.0

### 6. Estimate Matrix Size and Cost

Compute:
```
total_cells = templates x parameter_sets x models
total_runs  = total_cells x inputs x repetitions
```

Estimate cost using pricing from the research brief's model table:
- avg input tokens (estimate from research brief input examples)
- avg output tokens (estimate from output format)
- per-model pricing from the discovered models table

This is a rough estimate for the user approval checkpoint. The script will compute a more precise estimate after the matrix is generated (`generate_matrix.py --dry-run`).

**Important:** Every model in plan.yaml must have `cost_per_million_input` and `cost_per_million_output` fields filled in from the research brief. The execution script uses these for real-time cost tracking. If pricing is missing, cost tracking shows $0 and the budget guard won't work.

**Don't forget to include judge model cost.** The LLM judge makes 1 API call per result per LLM-judge criterion. If you have 720 results and 3 LLM-judge criteria, that's 2,160 extra API calls. Use a cheap, fast model as judge to minimize this overhead.

**If total_cost > budget:**
- First try: reduce repetitions to 2
- Then try: drop the most expensive model
- Then try: switch to fractional factorial strategy
- Document what was cut and why

### 7. Write plan.yaml

Write `experiments/{id}/plan.yaml`:

```yaml
experiment_id: "YYYY-MM-DD-slug"

goal:
  task: "From research brief Task Definition"
  task_type: "classification | generation | extraction | reasoning | multi-step"
  input_format: "From research brief Inputs section"
  output_format: "From research brief Outputs section"
  success_definition: "From research brief Success Criteria"

axes:
  templates:
    - id: "t01-zero-shot"
      file: "templates/t01-zero-shot.yaml"
      technique: "zero_shot"
    # ... one per recommended technique
  parameters:
    # Core sets (apply to all models)
    - id: "deterministic"
      temperature: 0.0
      max_tokens: 512
    - id: "creative"
      temperature: 0.7
      max_tokens: 512
    # Model-specific sets (apply only to listed models)
    - id: "groq-json"
      temperature: 0.0
      max_tokens: 512
      json_mode: true
      applicable_models: ["llama-8b", "llama-70b"]  # only models that support json_mode
    - id: "anthropic-thinking"
      temperature: 0.0
      max_tokens: 2048
      thinking: true
      thinking_budget: 1024
      applicable_models: ["sonnet"]  # only Anthropic models
  models:
    - id: "sonnet"
      name: "claude-sonnet-4-20250514"
      provider: "anthropic"
      supported_params: [temperature, max_tokens, top_p, top_k, thinking, thinking_budget, stop_sequences]
    # ... from research brief recommended models

evaluation:
  method: "composite"
  criteria:
    - name: "accuracy"
      description: "Derived from research brief success criteria"
      weight: 0.4
    # ... one per success criterion
  judge_model: "claude-sonnet-4-20250514"

execution:
  strategy: "full"              # full | fractional | latin_square | adaptive
  repetitions: 3
  randomize_order: true
  max_concurrent: 5

budget:
  max_cost_usd: 10.00
  max_api_calls: 1000

data:
  source: "user_provided | generate"  # from research brief test data strategy
  user_data_path: ""                   # path if user provided
  generate_count: 20                   # if generating: how many inputs
  distribution: "40% easy, 30% hard, 30% edge"

# Research sources (for traceability)
research_sources:
  models_from: "web_research | user_specified | references/llm-notes.md"
  techniques_from: "web_research | user_specified | references/prompt-methodologies.md"
  parameters_from: "web_research | references/default"
```

### 8. Validate

Before saving, verify:
- All template IDs are unique
- All model IDs are unique
- Criterion weights sum to 1.0
- Estimated cost <= budget.max_cost_usd
- strategy matches matrix size (full if <500 cells, fractional if 500-5000)

## Output

`experiments/{id}/plan.yaml`

## Handoff

Summarize the plan: "{N} templates x {N} param sets x {N} models = {N} cells x {N} inputs x {N} reps = {total} API calls. Estimated cost: ${X}. Strategy: {full/fractional}."

Pause here for user confirmation. This is the only mandatory checkpoint before execution.

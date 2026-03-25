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

### 4. Define Parameter Axis (from Research)

Use the parameter strategy from the research brief:
- Create 2-4 named parameter sets from the recommended ranges
- Example: "deterministic" (t=0.0), "balanced" (t=0.3), "creative" (t=0.7)
- Set max_tokens based on expected output size from research brief

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
    - id: "deterministic"
      temperature: 0.0
      max_tokens: 512
      top_p: 1.0
    # ... from research brief parameter strategy
  models:
    - id: "sonnet"
      name: "claude-sonnet-4-20250514"
      provider: "anthropic"
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

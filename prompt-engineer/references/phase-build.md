# Phase: Build

## Purpose

Create prompt templates and test data. Templates are constructed using the techniques, model details, and domain knowledge discovered in the research phase. Test data is generated if the user didn't provide any.

## Steps

### 1. Read Inputs

Read `experiments/{id}/plan.yaml` and `experiments/{id}/research_brief.md`. Extract:
- Template IDs and their assigned techniques from plan.yaml
- Full technique descriptions (how it works, prompt setup) from research brief's "Discovered Prompt Techniques" section
- Output format, schema, and validation rules from research brief
- Constraints from research brief
- Success criteria from research brief (templates must be designed so these are testable)
- Data source from plan.yaml (`user_provided` or `generate`)

### 2. Create Templates Directory

Ensure `experiments/{id}/templates/` exists.

### 3. Build Templates from Research

For each template ID in `plan.yaml axes.templates`:

**Step 3a — Read the technique's prompt setup** from the research brief. The research phase documented how each technique works and what the prompt structure looks like. Use this as the blueprint.

**Step 3a-check — Verify all techniques are covered.** Count the techniques listed in plan.yaml `axes.templates`. Compare to the "Recommended Techniques" in the research brief. Every recommended technique must have a template — do not silently drop techniques. If you need to cut for budget reasons, document which technique was cut and why in the plan.yaml comments.

**Step 3b — Derive the template structure** from the research brief's output requirements:
- Read "Outputs" section — the template needs to produce output matching this exact format, because the evaluation engine parses it programmatically and mismatches cause scoring failures
- Read "Constraints" section — every constraint becomes an explicit instruction
- Read "Success Criteria" — design the prompt so each criterion is addressable

**Step 3c — Write the template** applying exactly one technique:

```yaml
id: "t01-zero-shot"
name: "Zero-Shot Baseline"
description: "What this template tests and why"
technique: "zero_shot"
system_prompt: |
  {Derived from technique setup + domain constraints + output format}
user_prompt: |
  {Derived from technique setup + input format}
variables:
  - name: "input"
    required: true
    description: "The content to process"
```

**Rules:**
- One technique per template (isolates effects in the matrix)
- Every template must include explicit output format instructions from the research brief
- Every template must include all constraints from the research brief
- Use the exact variable names that the execution engine expects: `{{ input }}` for the test input
- For few-shot templates: generate examples that match the task domain using research brief's input/output examples
- For CoT templates: include step-by-step reasoning instructions specific to the task type
- For role templates: derive the role from the domain context in the research brief
- If user provided existing templates: follow the approach decided in the research brief's "Current State" section (baseline, variations, extract-and-rebuild, few-shot source, or a combination)
- If user provided domain docs: reference key constraints/rules from those docs in templates

### 3d. Handle Complex Input Types

Check the research brief's "Input Complexity" section. If the input type is NOT `text_only`:

**Multi-field inputs** (RAG, structured): Use multiple template variables. Example:
```yaml
user_prompt: |
  Context: {{ context }}

  Question: {{ query }}
```
Test data must have matching fields: `{"context": "...", "query": "..."}`.
The execution engine maps all test data fields to template variables automatically.

**Vision inputs** (image + text): The standard execution engine only sends text. Write a custom execution script at `experiments/{id}/custom_run.py` that:
- Reads image files or URLs from test data
- Encodes images as base64 content blocks
- Sends multi-modal messages to vision-capable models
- Uses the same output format (JSONL with tokens_in, tokens_out, cost_usd, latency_ms)
Update the run_pipeline.py call or run the custom script directly.

**Tool calling**: Write a custom execution script that includes `tools` parameter in API calls. Define tool schemas in a `experiments/{id}/tools.yaml` file. Templates become tool-selection strategies rather than prompt text.

**Multi-turn conversations**: Write test data as conversation arrays instead of single strings:
```yaml
inputs:
  - id: "conv_001"
    messages:
      - {role: "user", content: "Hi, I need help with my order"}
      - {role: "assistant", content: "I'd be happy to help! What's your order number?"}
      - {role: "user", content: "It's #12345, the item arrived damaged"}
```
Write a custom execution script that sends the full message array.

**File inputs**: During BUILD, read/process files and extract content into test_inputs.yaml. For PDFs: extract text. For CSVs: serialize rows. For images: store file paths for the custom execution script.

The key principle: the standard pipeline handles text-only and multi-field inputs out of the box. For vision, tool calling, multi-turn, and file inputs — Claude writes a custom execution script during BUILD that follows the same output format so EVALUATE and REPORT still work unchanged.

### 4. Validation Checklist

For each template verify:
- [ ] Every `{{ variable }}` in prompts is declared in `variables` list
- [ ] No unused variables
- [ ] Output format instructions match research brief's "Outputs" schema exactly
- [ ] All constraints from research brief are included as instructions
- [ ] One technique per template (check `technique` field)
- [ ] No prompt injection risks (user input variables not in system_prompt unless intended)
- [ ] YAML parses without errors

### 5. Generate Test Data (if needed)

Check `plan.yaml data.source`:

**If `user_provided`:** Read the user's test data file. Validate it has `id` and `text` fields. Copy or symlink to `experiments/{id}/data/test_inputs.yaml`.

**If `generate`:** Create `experiments/{id}/data/test_inputs.yaml` with test inputs.

**How to generate test data:**

Read the research brief's "Inputs" section (format, examples, edge cases) and "Discovered Domain Context."

Generate **at least 15 inputs** (15-25 is ideal). Fewer than 15 doesn't give enough statistical power to distinguish models that score within 0.5 points of each other — you'd be making deployment decisions based on noise.

Distribution:
- **Easy cases (~40% = 6-10 inputs):** Clear-cut inputs where the correct output is obvious.
- **Hard cases (~30% = 5-7 inputs):** Ambiguous inputs that require nuance.
- **Edge cases (~30% = 4-6 inputs):** Unusual, adversarial, or boundary-testing inputs.

```yaml
inputs:
  - id: "input_001"
    text: "The actual input content"
    expected_decision: "APPROVE"        # ground truth if known (classification)
    expected_output: "exact expected"   # ground truth if known (extraction/generation)
    metadata:
      category: "easy"                  # easy | hard | edge
      description: "Why this input is included"
  # ... 15-25 inputs total
```

**Rules:**
- Every input needs a unique `id` and non-empty `text` — the execution engine keys results on input_id, so duplicates cause data overwrites
- Format the `text` field to match the research brief's documented input format
- Include `expected_decision` or `expected_output` when ground truth is determinable — this improves LLM-judge scoring accuracy significantly
- For classification tasks: balance across all output categories
- For generation tasks: vary complexity, length, and domain
- For extraction tasks: include clean inputs, messy inputs, and inputs with missing fields
- Use real-world patterns discovered during domain research, not generic placeholders

### 6. Self-Review Test Data

After generating test data, review it before moving on:
- Are the inputs realistic for this domain? (not generic placeholder text)
- Are expected answers correct? (wrong ground truth = wrong evaluation)
- Is the difficulty distribution balanced? (not all easy or all hard)
- Do edge cases actually test boundary conditions? (not just unusual formatting)
- For classification: are all output categories represented?

If anything looks weak, fix it now. Bad test data wastes the entire experiment budget.

### 7. Update plan.yaml

Confirm all file paths in `plan.yaml axes.templates` match actual files. Update `plan.yaml data.test_inputs` to point to the generated/provided file.

## Output

- `experiments/{id}/templates/{template_id}.yaml` — one per variant
- `experiments/{id}/data/test_inputs.yaml` — test dataset

## Handoff

List templates created (IDs, techniques) and test data summary (count, distribution). Proceed immediately to MATRIX phase. No user confirmation needed here — user already approved the plan.

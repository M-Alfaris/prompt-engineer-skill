# Workflow: Fast Smoke Test

## Purpose

Validate a prompt idea in under 5 minutes using a single template, default model, and minimal inputs. Use this before committing to a full experiment. Use it also after editing a prompt to confirm no regressions.

---

## When to Use

- You have a draft prompt and want a quick sanity check before investing in a full matrix run.
- You have just edited a winning prompt from a previous experiment and need to confirm it still works.
- Budget is very limited and you need a directional signal only (not statistical certainty).
- You want to demo a capability to a stakeholder quickly.

Do not use this workflow as a substitute for the full iterative workflow. A smoke test confirms that a prompt is plausible — it does not identify the optimal prompt.

---

## Steps

### 1. Select the Template

Pick the single most promising prompt template. Apply the following priority order:
1. If you have a winning template from a previous experiment, use that.
2. If starting fresh, default to a few-shot template using the top technique from `references/prompt-methodologies.md` for the task type.
3. If uncertain, use a zero-shot baseline — it is the fastest to write and provides the lowest bar to beat.

Write the template to `experiments/{id}-smoke/templates/t01-smoke.yaml` using the standard template schema from `references/phase-build.md`.

### 2. Select the Model

Use `claude-sonnet-4-20250514` as the default. Do not experiment with model selection during a smoke test — the goal is to validate the prompt, not the model.

Override the default only if:
- The user has a hard cost constraint that requires a budget model
- The task explicitly targets a specific production model

### 3. Set Default Parameters

Use these fixed parameters. Do not vary them during a smoke test.

```yaml
temperature: 0.3
max_tokens: 512
top_p: 1.0
```

Increase `max_tokens` only if the task clearly requires a longer output (e.g., report generation). Keep temperature at 0.3 for a balance of reliability and natural language quality.

### 4. Prepare 3 Test Inputs

Select exactly 3 test inputs. They must be diverse:
- **Input A — Typical:** A representative example of the most common real-world input.
- **Input B — Edge case:** An unusual or boundary input (very short, very long, missing a field, unexpected format).
- **Input C — Adversarial:** An input designed to probe a likely failure mode (ambiguous phrasing, off-topic content, potential injection attempt).

Write the inputs inline. Do not retrieve them from a file.

### 5. Run the Test

Execute 3 API calls — one per input. Do not use repetitions. Record each response.

```
Run A: template t01-smoke + Input A → Response A
Run B: template t01-smoke + Input B → Response B
Run C: template t01-smoke + Input C → Response C
```

### 6. Evaluate

Use LLM-as-judge with a single criterion: **overall quality**.

Send one evaluation request per response using this simplified judge prompt:

```
You are an expert evaluator. Score this AI response on overall quality on a scale from 1 to 10.

Scoring guide:
10 = Perfect. Fully fulfills the task with no issues.
7-9 = Good. Minor gaps but clearly useful.
4-6 = Partial. Some value but notable problems.
1-3 = Poor. Fails the task.

Task given to the AI:
{{ task_instruction }}

Input:
{{ user_input }}

AI response:
{{ model_response }}

Respond with ONLY: {"score": <integer>, "rationale": "<one sentence>"}
```

### 7. Print Results to Console

Print the following directly in the chat response. Do not write a report file for a smoke test.

```
=== SMOKE TEST RESULTS ===
Experiment: {id}-smoke
Template:   t01-smoke
Model:      claude-sonnet-4-20250514
Parameters: temperature=0.3, max_tokens=512

--- Input A (Typical) ---
Score: {score}/10
Rationale: {rationale}
Response preview: {first 100 chars of response}...

--- Input B (Edge Case) ---
Score: {score}/10
Rationale: {rationale}
Response preview: {first 100 chars of response}...

--- Input C (Adversarial) ---
Score: {score}/10
Rationale: {rationale}
Response preview: {first 100 chars of response}...

--- Summary ---
Mean score: {mean}/10
Lowest score: {min}/10 (Input {letter})
Recommendation: {PASS | REVISE | FAIL}
```

**Recommendation logic:**
- PASS: All three scores are >= 7. Proceed to full experiment or deployment.
- REVISE: Mean score >= 6 but at least one score is < 7. Fix the failing case and re-run the smoke test.
- FAIL: Mean score < 6 or any score <= 3. Do not proceed. Redesign the template and return to the research phase.

---

## Time Budget

| Step | Target Time |
|---|---|
| Write template | 3-5 minutes |
| Prepare 3 inputs | 2-3 minutes |
| Run 3 API calls | < 30 seconds |
| Evaluate 3 responses | < 30 seconds |
| Print results | immediate |
| **Total** | **< 10 minutes** |

---

## Limitations

- 3 inputs is not statistically significant. A PASS on a smoke test does not guarantee production quality.
- Single-criterion evaluation misses format compliance, safety, and domain-specific criteria.
- No repetitions means variance is not measured.
- Treat a PASS as "worth a full experiment" not as "ready to deploy."

# Phase: Evaluate

## Purpose

Score all experiment results using the right evaluation method for each criterion. The system supports 4 methods that can be mixed per-criterion. Claude picks the best method for each criterion based on the task type and what data is available.

## Choosing the Judge Model

The judge model evaluates every result for every LLM-judge criterion. This adds up fast:
- 720 results x 3 LLM-judge criteria = 2,160 judge API calls
- At $0.01/call that's $21 just for evaluation

**Rules for picking the judge:**
1. Use a **cheap, fast model** — the judge prompt is simple (score 1-10), it doesn't need a premium model
2. Use a **different model** from the ones being tested — avoids self-evaluation bias
3. Use the **same provider** as the experiment when possible — avoids needing a second API key
4. Judge output is short (just JSON with score + one sentence) — set `max_tokens: 150` for the judge

**Good defaults by provider:**
- Testing on Groq → judge with the cheapest Groq text model (e.g., llama-8b-instant)
- Testing on OpenAI → judge with gpt-4o-mini
- Testing on Anthropic → judge with Haiku
- Testing multiple providers → judge with whichever is cheapest

**In plan.yaml:**
```yaml
evaluation:
  judge_model:
    name: "llama-3.1-8b-instant"    # cheap and fast
    provider: "groq"
    base_url: "https://api.groq.com/openai/v1"
    api_key_env: "GROQ_API_KEY"
```

## Evaluation Methods

### 1. `llm_judge` — LLM scores the output 1-10
- A judge model reads the original prompt + model output + criterion definition
- Returns a 1-10 integer score with one-sentence reasoning
- **Use for:** subjective quality — relevance, tone, reasoning quality, completeness, style
- **Cost:** 1 API call per result per LLM-judge criterion (expensive at scale — minimize by using cheap judge and fewer LLM-judge criteria)
- **Accuracy:** Good for nuanced judgment, but inconsistent across runs (~0.5-1.0 point variance)

### 2. `code` — Programmatic check returns 0-10
- Runs a Python function against the output
- Built-in checks (no custom code needed):
  - `json_valid` — is the output valid JSON?
  - `json_schema` — does the JSON have expected keys?
  - `contains_expected` — do expected values appear in output?
  - `keywords_in_input` — do extracted keywords exist in the source text?
  - `length_check` — is output within character/token limits?
- Custom checks: write `experiments/{id}/custom_checks.py` with functions matching `def check_name(output, input_data, expected) -> float`
- **Use for:** objective, deterministic checks — format compliance, field presence, value validation
- **Cost:** Zero API calls
- **Accuracy:** 100% consistent, no variance

### 3. `ground_truth` — Compare against expected answers
- Compares model output against a reference answer from the test data
- Comparison modes:
  - `exact_match` — output == expected (case-insensitive)
  - `contains` — expected string appears in output
  - `f1_token` — token-level F1 score (good for extraction tasks)
  - `jaccard` — Jaccard similarity of token sets
  - `semantic` — uses LLM to judge semantic equivalence (falls back to llm_judge)
- **Use for:** tasks where you have correct answers — Q&A datasets, classification labels, extraction targets
- **Cost:** Zero for exact/contains/f1/jaccard. One API call for semantic.
- **Accuracy:** Depends on comparison mode. exact_match is binary. f1_token captures partial credit.

### 4. `regex` — Pattern match pass/fail
- Applies a regex pattern to the output
- Pass = 10, Fail = 0
- **Use for:** simple format checks — "starts with {", "contains keyword X"
- **Cost:** Zero
- **Accuracy:** Binary, no partial credit

## How to Pick Methods (Decision Guide for Claude)

Read the research brief's success criteria and task type. For each criterion, pick the method using this logic:

**Step 1: Is there a correct answer?**
- User provided `expected_output`, `expected_decision`, or `expected_keywords` in test data → **ground_truth**
- User provided a Q&A dataset → **ground_truth**
- No correct answer exists → go to Step 2

**Step 2: Is the check objective or subjective?**
- Can a Python function check it deterministically? (JSON valid, keyword in text, length limit, field exists) → **code**
- Can a regex check it? (output starts with X, contains pattern Y) → **regex**
- Requires human-like judgment? (relevance, quality, tone, accuracy) → **llm_judge**

**Step 3: Cost/speed tradeoff**
- If budget is tight: maximize `code` and `ground_truth`, minimize `llm_judge`
- If accuracy matters most: use `llm_judge` for subjective + `code` for objective
- If speed matters: avoid `llm_judge` entirely, use `code` + `ground_truth`

### Examples by Task Type

**Classification (content moderation, sentiment):**
```yaml
criteria:
  - name: "decision_accuracy"
    method: "ground_truth"
    comparison: "exact_match"
    expected_field: "expected_decision"
    weight: 0.40
  - name: "json_valid"
    method: "code"
    check: "json_valid"
    weight: 0.20
  - name: "reasoning_quality"
    method: "llm_judge"
    weight: 0.20
  - name: "no_false_positives"
    method: "llm_judge"
    weight: 0.20
```

**Extraction (keyword extraction, data parsing):**
```yaml
criteria:
  - name: "keyword_relevance"
    method: "llm_judge"
    weight: 0.25
  - name: "keyword_completeness"
    method: "ground_truth"
    comparison: "f1_token"
    expected_field: "expected_keywords"
    weight: 0.25
  - name: "json_valid"
    method: "code"
    check: "json_valid"
    weight: 0.20
  - name: "no_hallucination"
    method: "code"
    check: "keywords_in_input"
    weight: 0.15
  - name: "ranking_quality"
    method: "llm_judge"
    weight: 0.15
```

**Generation (chatbot, summarization, writing):**
```yaml
criteria:
  - name: "relevance"
    method: "llm_judge"
    weight: 0.30
  - name: "completeness"
    method: "llm_judge"
    weight: 0.25
  - name: "tone"
    method: "llm_judge"
    weight: 0.20
  - name: "length_ok"
    method: "code"
    check: "length_check"
    expected: {"min": 50, "max": 500}
    weight: 0.15
  - name: "no_hallucination"
    method: "llm_judge"
    weight: 0.10
```

**Q&A with golden answers:**
```yaml
criteria:
  - name: "answer_accuracy"
    method: "ground_truth"
    comparison: "f1_token"
    expected_field: "expected_output"
    weight: 0.50
  - name: "answer_contains_key"
    method: "ground_truth"
    comparison: "contains"
    expected_field: "expected_output"
    weight: 0.20
  - name: "reasoning_quality"
    method: "llm_judge"
    weight: 0.20
  - name: "format_compliance"
    method: "code"
    check: "json_valid"
    weight: 0.10
```

## Steps

### 1. Read Config
Read `plan.yaml` evaluation section. Identify which methods are needed.

### 2. If method is "auto" — Select Methods per Criterion
Read each criterion and auto-detect the best method:
- Has `check` field → `code`
- Has `comparison` + `expected_field` → `ground_truth`
- Description starts with `pattern:` → `regex`
- Everything else → `llm_judge`

If no explicit methods are set, design them using the decision guide above and the research brief's task type.

### 3. Run the Evaluation Script
```bash
python scripts/evaluate.py --experiment experiments/{id}/
```

The script handles all routing automatically based on the criterion config.

### 4. Verify
- All results scored (check evaluations/scores.jsonl line count matches results)
- No scores outside 1-10 range
- summary.yaml contains rankings and axis effects

## Output
- `experiments/{id}/evaluations/scores.jsonl`
- `experiments/{id}/evaluations/summary.yaml`

## Handoff
Report: top combo, its score, any high-variance cells. Proceed to REPORT.

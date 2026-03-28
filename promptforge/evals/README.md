# Prompt-Engineer Skill — Eval System

## What Are Evals?

Evals (evaluations) are automated checks that verify the prompt-engineer skill behaves
correctly. Each eval is a test case that specifies an input prompt, the behaviors that
must occur, and the behaviors that must not occur. Running evals gives you a pass/fail
signal across the full pipeline before you trust it with real experiments.

Following the Claude blog's guidance on skill testing, this eval system separates three
concerns:

1. **Trigger tests** — Does the skill activate for the right prompts and stay quiet for
   the wrong ones?
2. **Phase correctness tests** — Does each pipeline stage produce the right artifacts
   with the right structure?
3. **End-to-end tests** — Does the full 7-stage pipeline produce a usable result within
   budget?

---

## File Map

```
evals/
  README.md              # This file
  test_cases.yaml        # Full test case definitions (all categories)
  trigger_tests.yaml     # Trigger-only tests (fast, no execution required)

scripts/
  run_evals.py           # Run test_cases.yaml checks programmatically
  run_benchmarks.py      # Run evals, capture metrics, write benchmark JSON

benchmarks/
  YYYY-MM-DD-HH-MM.json  # Historical benchmark snapshots (auto-generated)
```

---

## What the Evals Test

### Trigger tests (`category: trigger`)

Verify that the skill activates for prompt-engineering tasks (optimize, A/B test,
compare models, run experiments) and does NOT activate for unrelated requests (write
a single prompt, debug code, summarize a document, answer a question).

These tests do not require running the pipeline. They are fast and can be run in CI.

### Research phase tests (`category: research`)

Verify that `research_brief.md` is produced with all required sections, that
user-specified models are respected, and that the document is non-empty and parseable.

### Plan phase tests (`category: plan`)

Verify that `plan.yaml` is valid YAML, that criterion weights sum to 1.0, that
estimated cost fits within budget, and that the file has the minimum required axes
(at least 2 templates, 2 parameter sets, 1 model).

### Build phase tests (`category: build`)

Verify that each template uses exactly one technique, includes output format
instructions, and that test inputs cover easy/hard/edge categories with the required
fields.

### Execute phase tests (`category: execute`)

Verify that `validate.py` runs cleanly before execution, that the budget guard stops
the run when the ceiling is hit, and that every result record contains the required
cost and latency fields.

### Evaluate phase tests (`category: evaluate`)

Verify that every result has a composite score in the 1-10 range, that `summary.yaml`
exists with rankings and axis effects, and that the best cell is identified.

### Report phase tests (`category: report`)

Verify that `report.md` contains all 9 required sections, that the winning prompt text
is present and copy-pasteable, and that `report_data.json` is generated.

### End-to-end tests (`category: end_to_end`)

Verify the complete pipeline from user prompt to final report, including artifact
existence checks and budget constraint enforcement.

---

## How to Run Evals

### Run all non-execution tests (fast, no API calls)

```bash
python scripts/run_evals.py
```

### Run only one category

```bash
python scripts/run_evals.py --category research
python scripts/run_evals.py --category plan
python scripts/run_evals.py --category trigger
```

### Run against a specific experiment directory

```bash
python scripts/run_evals.py --experiment experiments/2026-03-24-ecommerce-content-moderation/
```

### Include tests that require pipeline execution (makes real API calls)

```bash
python scripts/run_evals.py --execute --experiment experiments/my-experiment/
```

### Output as JSON (for CI integration)

```bash
python scripts/run_evals.py --json
```

Example output:
```json
{
  "total": 24,
  "passed": 21,
  "failed": 2,
  "skipped": 1,
  "results": [
    {"id": "plan-001", "passed": true, "message": "Criterion weights sum to 1.0"},
    {"id": "plan-002", "passed": false, "message": "Estimated cost $22.50 exceeds budget $20.00"}
  ]
}
```

---

## How to Run Benchmarks

Benchmarks run all evals, collect timing and token-usage metrics, and write a snapshot
to `benchmarks/`.

```bash
python scripts/run_benchmarks.py
```

### Compare against a previous run

```bash
python scripts/run_benchmarks.py --compare benchmarks/2026-03-01-10-00.json
```

This prints a diff showing which tests regressed (newly failing) and which improved
(newly passing) since the previous snapshot.

---

## Tests That Require Execution

Some tests cannot be verified from static file inspection alone — they require actually
running the pipeline. These are marked `requires_execution: true` in `test_cases.yaml`
and are skipped by default.

Tests that require execution include:
- Budget guard stops execution when ceiling is reached
- `validate.py` passes before execution starts
- All result records contain tokens_in, tokens_out, cost_usd, latency_ms

To run these, pass `--execute` and point at a real experiment directory with API keys
configured in `.env`.

---

## Adding New Tests

1. Add a new entry to `evals/test_cases.yaml` following the schema.
2. If it is a trigger test, also add it to `evals/trigger_tests.yaml`.
3. If the check can be verified programmatically (file existence, schema, numeric
   validation), implement the check in `scripts/run_evals.py` in the appropriate
   `_check_*` function.
4. If the check requires pipeline execution, set `requires_execution: true`.

---

## Interpreting Results

| Outcome | Meaning |
|---------|---------|
| PASSED  | The check ran and the condition was met |
| FAILED  | The check ran and the condition was NOT met — this is a bug |
| SKIPPED | The check requires execution and `--execute` was not passed |

A healthy skill should show 100% pass rate on all non-execution tests. A pass rate
below 90% on execution tests indicates a pipeline reliability problem.

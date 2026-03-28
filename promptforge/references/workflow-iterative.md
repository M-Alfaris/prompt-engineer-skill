# Workflow: Iterative Refinement

## Purpose

A multi-round experimental loop that progressively narrows from broad exploration to fine-grained optimization. Use this workflow when quality must be maximized and budget permits more than one experiment run.

## Overview

```
Round 1: Broad Exploration  →  select top 5
Round 2: Focused Refinement →  mutate winners, re-evaluate
Round 3: Parameter Sweep    →  fine-tune around best params
Round 4: Cross-Validation   →  confirm on held-out inputs
Terminate when: improvement < 2%, budget exhausted, or user satisfied
```

---

## Round 1: Broad Exploration

**Goal:** Identify which techniques, models, and parameter regions are worth investing in.

**Steps:**
1. Run the full pipeline: research → plan → build → select → matrix → evaluate.
2. Use a full or fractional factorial strategy depending on matrix size.
3. Cover all techniques from the research brief (typically 4-8 templates).
4. Use a broad parameter grid: temperature at [0.0, 0.3, 0.7].
5. Include at least one budget model and one balanced model.
6. Use 3 repetitions per cell.

**Output:**
- Ranked results table in `experiments/{id}-r1/report.md`
- Top 5 combinations by composite score

**Exit criteria:** Identify the top 5 (template, model, parameters) combinations. Compute their mean scores and confidence intervals. If the top 5 have overlapping confidence intervals with the bottom half, increase repetitions before proceeding.

---

## Round 2: Focused Refinement

**Goal:** Improve the top performers through targeted mutations.

**Steps:**
1. Take the top 5 combinations from Round 1.
2. For each winner, create 3 mutant templates:
   - **Rephrase mutation:** Rewrite the instructions using different vocabulary and sentence structure. Keep the semantic meaning identical.
   - **Example mutation:** Add 2 examples to a zero-shot template, remove examples from a few-shot template, or replace existing examples with higher-quality ones.
   - **Specificity mutation:** Make the instructions more specific (add explicit rules, schema, or constraints) or less specific (remove constraints that may be limiting useful responses).
3. Run only the mutant templates against the top-performing model and parameter set from Round 1.
4. Use 3 repetitions per cell.

**Output:**
- Ranked comparison of originals vs. mutants
- New top combination if any mutant outperforms its parent

**Exit criteria:** If no mutant scores more than 2% above its parent's mean score, skip further mutation and proceed to Round 3.

---

## Round 3: Parameter Sweep

**Goal:** Fine-tune the parameter values around the winning region.

**Steps:**
1. Take the winning template and model from Round 2 (or Round 1 if Round 2 produced no improvement).
2. Define a narrow parameter grid centered on the Round 1 winning temperature:
   - If Round 1 winner used temperature 0.3: test [0.1, 0.2, 0.3, 0.4, 0.5]
   - If Round 1 winner used temperature 0.0: test [0.0, 0.05, 0.1, 0.15]
3. Optionally sweep max_tokens if the output length was borderline in Round 1.
4. Use 5 repetitions per cell (increased for tighter confidence intervals).

**Output:**
- Score vs. temperature curve
- Final recommended parameter set
- Stability analysis (std dev across repetitions per temperature)

**Exit criteria:** Select the temperature with the highest mean score. If two temperatures are within 2% of each other, prefer the lower temperature for stability.

---

## Round 4: Cross-Validation

**Goal:** Confirm that the winning combination generalizes to unseen inputs.

**Steps:**
1. Collect a held-out test set of at least 10 inputs that were not used in any previous round. These should include:
   - Typical cases (representative of the most common real-world inputs)
   - Edge cases (unusual formatting, ambiguous phrasing, empty inputs)
   - Adversarial cases (inputs designed to trigger failure modes)
2. Run only the final winning combination (template + model + parameters) against this test set.
3. Use 3 repetitions per input.
4. Evaluate using the same criteria and judge model as previous rounds.

**Output:**
- Cross-validation score (mean composite score on held-out inputs)
- Comparison to Round 1/2/3 scores (overfitting check)
- List of inputs where score dropped more than 1.5 points below the mean

**Exit criteria:** If the cross-validation score is within 0.5 points of the Round 3 mean, the result is valid. If the gap is larger, the prompt is overfit to the development inputs. Return to Round 2 with a less specific mutation strategy.

---

## Termination Conditions

Stop iterating when any of the following is true:

1. **Improvement threshold:** The best score improvement between consecutive rounds is less than 2% (e.g., Round 2 top score is 8.85, Round 3 top score is 8.97 — improvement is 1.4%, stop).
2. **Budget exhausted:** Cumulative API spend across all rounds reaches `budget.max_cost_usd`.
3. **User satisfied:** The user explicitly approves the current best combination after reviewing the report.
4. **Cross-validation passed:** Round 4 validates the winner and no critical failure modes were found.

---

## Round Naming Convention

Name experiment folders sequentially:
- `experiments/YYYY-MM-DD-slug-r1/`
- `experiments/YYYY-MM-DD-slug-r2/`
- `experiments/YYYY-MM-DD-slug-r3/`
- `experiments/YYYY-MM-DD-slug-r4/`

Each round has its own plan.yaml, matrix.yaml, and report.md. The research_brief.md from Round 1 is reused in all subsequent rounds unless the task definition changes.

---

## Cross-Round Summary

After all rounds complete, write a single `experiments/YYYY-MM-DD-slug-summary.md` that:
- Lists the winning combination from each round with its score
- Shows the score progression across rounds as a table
- States the final recommended combination
- Notes any unresolved failure modes from Round 4

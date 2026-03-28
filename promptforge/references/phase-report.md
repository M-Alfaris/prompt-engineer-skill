# Phase: Report

## Purpose

Synthesize all experiment data into a human-readable report that delivers a clear recommendation and is ready to hand off to engineering or product teams.

## Two-Step Process

**Step A — Run the script first:**
```bash
python scripts/generate_report.py --experiment experiments/{id}/
```
This produces `report_data.json` (structured data for dashboards) and a draft `report.md` with rankings tables, axis analysis, and cost-performance data. The script does all the mechanical aggregation.

**Step B — Then write the narrative sections yourself:**
The script's report.md has placeholder sections that need your judgment: Executive Summary, Methodology context, Interaction Effects interpretation, Winning Prompt explanation, and Recommendations. Read the script's output, then add or rewrite these narrative sections.

## Steps

### 1. Read All Inputs

Run `generate_report.py` first, then read:
- `experiments/{id}/plan.yaml` — experiment configuration
- `experiments/{id}/research_brief.md` — original task definition and success criteria
- `experiments/{id}/matrix.yaml` — cell definitions and statuses
- `experiments/{id}/scores.jsonl` — per-cell criterion scores
- `experiments/{id}/summary.yaml` — aggregated statistics and axis effects

Identify the winning cell: the (template, model, parameters) combination with the highest mean composite score. Load the actual prompt text from its template file.

### 2. Write report.md

Write `experiments/{id}/report.md` with the following sections in order.

---

### Section 1: Executive Summary

State the single best-performing combination. Give its composite score and the headline metric (e.g., "93% accuracy at $0.0018 per query"). Describe in two sentences what this combination does and why it wins. Include a one-line deployment recommendation.

### Section 2: Methodology

Describe what was tested and how. Include:
- Number of templates tested and which techniques were applied
- Parameter ranges tested (temperature, max_tokens)
- Models evaluated
- Evaluation method used (LLM-as-judge / regex / composite)
- Number of repetitions per cell
- Execution strategy (full / fractional / latin_square / adaptive)
- Total API calls made and total cost incurred

### Section 3: Results Overview

Produce a ranked table of all cells by mean composite score. Include at minimum:

| Rank | Cell ID | Template | Model | Temp | Mean Score | Std Dev | Cost/Call | Latency (ms) | TTFT (ms) | Tokens In | Tokens Out |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | cell-012 | t02-few-shot | claude-sonnet-4 | 0.3 | 8.74 | 0.31 | $0.0021 | 1240.5 | 285.3 | 312 | 156 |
| ... | | | | | | | |

Flag any cells with std dev > 1.5 as unstable.

### Section 4: Axis Analysis

Report the best value for each individual axis:

**Best Template:** State which template ID and technique won. Give its mean score averaged across all models and parameter sets. Compare to the worst-performing template.

**Best Temperature:** State which temperature setting produced the highest mean score. Note if there is a trade-off between score and stability (std dev).

**Best Model:** State which model produced the highest mean score. State which model produced the best score per dollar. State which model had the lowest latency and TTFT.

### Section 5: Interaction Effects

Identify the two strongest positive interaction effects: pairs of axis values that outperform what their individual axis scores would predict. Explain in one sentence why the combination likely works (e.g., "Chain-of-thought reasoning benefits from the higher reasoning capacity of Sonnet, yielding a 1.2-point boost above either axis mean").

If no significant interaction effects are found, state that explicitly.

### Section 6: Cost-Performance Tradeoff

Identify the Pareto-efficient combinations: those where no other combination is both cheaper and higher-scoring. Present these as a short table:

| Combination | Mean Score | Cost/Call | Latency (ms) | TTFT (ms) | Tokens In | Tokens Out | Notes |
|---|---|---|---|---|---|---|---|
| t01 + m01 + p01 | 7.2 | $0.0004 | 320.1 | 78.2 | 180 | 95 | Best budget option |
| t02 + m02 + p02 | 8.7 | $0.0021 | 1240.5 | 285.3 | 312 | 156 | Best balanced option |
| t03 + m03 + p02 | 9.1 | $0.0089 | 2810.3 | 520.7 | 520 | 280 | Best quality, premium cost |

Recommend which Pareto point to use based on the budget constraint in plan.yaml.

### Section 7: Winning Prompt

Print the full, deployment-ready prompt text for the winning combination. Render all Jinja2 variables with their descriptions (do not fill in actual values — show the variable placeholders with a comment explaining each).

Include:
- System prompt (full text)
- User prompt template (full text with variable annotations)
- Recommended parameter values (temperature, max_tokens, top_p)
- Recommended model

### Section 8: Recommendations

Provide 3-5 concrete next steps. Prioritize by expected impact. Format as an ordered list:

1. **Immediate deployment action** — what to do right now
2. **Next experiment** — what to test in the next iteration based on this experiment's findings
3. **Parameter refinement** — any narrow parameter sweep that could improve the winner
4. **Edge case hardening** — specific input types that showed lower scores and how to address them
5. **Cost optimization** — if the winner uses a premium model, describe conditions under which the balanced-tier model is sufficient

### Section 9: Raw Data Reference

List all data files produced by this experiment:

- `experiments/{id}/research_brief.md`
- `experiments/{id}/plan.yaml`
- `experiments/{id}/matrix.yaml`
- `experiments/{id}/templates/*.yaml`
- `experiments/{id}/results/*.jsonl`
- `experiments/{id}/scores.jsonl`
- `experiments/{id}/summary.yaml`

---

### 3. Formatting Rules

- Use Markdown headers (##, ###)
- Use tables for ranked results, axis analysis, and cost-performance
- Use bold for the winning combination everywhere it appears
- Keep the executive summary under 150 words
- The winning prompt section must be copy-pasteable without modification

## Output

`experiments/{id}/report.md`

## Handoff

Print the executive summary directly in the chat response. Provide the full path to report.md. Ask the user if they want to proceed to the next experiment iteration or begin deployment.

# Phase: Matrix

## Purpose

Generate the combinatorial experiment matrix from plan.yaml axes. This is done by a Python script, not manually.

## Steps

### 1. Run the matrix generator

```bash
python scripts/generate_matrix.py --experiment experiments/{id}/
```

The script:
- Reads `plan.yaml` axes (templates x parameters x models)
- Computes the full cartesian product with repetitions
- Estimates cost using model pricing from `configs/default_config.yaml`
- Applies the execution strategy (full or fractional factorial)
- Randomizes cell order if `execution.randomize_order: true`
- Writes `matrix.yaml` with all cells
- Updates `state.yaml`

### 2. Review the output

The script prints a cost estimate table. Review:
- Total cells and API calls
- Estimated cost vs budget ceiling
- Cost breakdown by model

### 3. If cost exceeds budget

Options:
- Re-run with `--strategy fractional` (runs 25% of combinations while ensuring coverage)
- Edit plan.yaml to remove expensive models or reduce repetitions
- Increase the budget in plan.yaml

### 4. Dry run option

```bash
python scripts/generate_matrix.py --experiment experiments/{id}/ --dry-run
```

Prints stats without writing matrix.yaml. Use to preview before committing.

## Matrix strategies

| Strategy | When | What the script does |
|----------|------|---------------------|
| `full` | <500 cells | Every combination of template x params x model x reps |
| `fractional` | 500-5000 cells | 25% sample, every axis level appears at least once |

## Output

`experiments/{id}/matrix.yaml` — list of cells, each with: cell_id, template_id, model_id, param_id, repetition, status, parameters.

## Handoff

Proceed to EXECUTE. No user confirmation needed — cost was already approved in PLAN.

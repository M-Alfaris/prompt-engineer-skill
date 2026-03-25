# Reference: Advanced Model Selection

This file is NOT a pipeline stage. Model selection is handled by the RESEARCH phase (discovers models via web search) and PLAN phase (assembles the model axis). Load this file ONLY if deeper model analysis is needed — e.g., when the budget is tight and you need to make precise cost/quality tradeoffs.

## Decision Framework

Evaluate task complexity on three dimensions:

| Dimension | Low | Medium | High |
|-----------|-----|--------|------|
| Reasoning depth | Single lookup or transform | Multi-step logic | Complex inference, planning |
| Output length | <100 tokens | 100-500 tokens | 500+ tokens |
| Format strictness | Free text | Structured with validation | Schema-critical |

### Tier Selection

**Budget tier** — all dimensions Low, or one Medium:
- Fast, cheap, high throughput. Good for classification, simple extraction.

**Balanced tier** — any dimension Medium:
- Best default for most tasks. Good quality/cost ratio.

**Premium tier** — any dimension High, task cannot be decomposed:
- Use sparingly. Only when balanced tier measurably fails.

### Multi-Model Strategy

- Always include at least 2 models (one balanced, one budget) to establish a cost-performance baseline
- Add premium only if budget explicitly allows AND task warrants it
- If provider diversity matters (failover, compliance): one model per provider

### Local Model Consideration

Include Ollama when:
- Privacy requirements prohibit external APIs
- User confirmed Ollama is available
- Task doesn't need the largest context windows

## Cost Estimation Formula

```
cost_per_cell = (avg_input_tokens / 1M * input_price) + (avg_output_tokens / 1M * output_price)
total_cost = cost_per_cell * total_cells * repetitions * num_inputs
```

Use pricing from the research brief's "Discovered LLM Models" table.

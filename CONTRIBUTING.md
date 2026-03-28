# Contributing

Thanks for your interest in contributing to the Prompt Engineer Skill.

## Getting Started

1. Fork and clone the repo
2. Install dependencies: `cd prompt-engineer && pip install -r requirements.txt`
3. Ensure your project root has a `.env` with at least one API key (see `.env.example` for the format)

## Running the Eval Suite

The skill includes 24+ test cases across 7 categories in `prompt-engineer/evals/`:

```bash
# Run trigger tests (fast, no API calls)
python -m scripts.run_evals --experiment evals/ --suite trigger

# Run full eval suite (requires API keys)
python -m scripts.run_evals --experiment evals/
```

Test categories: trigger recognition, research output, plan validation, template quality, execution correctness, scoring stability, report completeness.

## Submitting Changes

1. Create a branch for your change
2. Make your changes
3. Run the eval suite to verify nothing breaks
4. Open a PR with a clear description of what changed and why

## What to Contribute

- New evaluation methods (beyond LLM-judge, code, ground_truth, regex)
- Provider support (new OpenAI-compatible endpoints)
- Template techniques (new prompt engineering strategies)
- Bug fixes and edge case handling
- Documentation improvements

## Code Style

- Python 3.10+ with type hints
- Async where possible (the execution engine is fully async)
- Budget safety: never make API calls without cost tracking

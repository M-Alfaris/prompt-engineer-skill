# Prompt Engineering Experimentation Framework

This project contains the `prompt-engineer` skill — a modular experimentation system built following Anthropic's skill-creator guidelines.

## Skill Location

The skill lives at `prompt-engineer/`. It follows Anthropic's standard skill structure:

```
prompt-engineer/
  SKILL.md              # Orchestrator (8-stage pipeline)
  references/           # Phase guides, knowledge docs, workflow templates
  scripts/              # Python execution layer (async runners, evaluation)
  configs/              # Default and example configurations
  data/                 # Sample test inputs
  experiments/          # Output directory (one subfolder per experiment)
  ui/                   # Browser-based report viewer
```

## Quick Start

1. `cd prompt-engineer && pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add API keys
3. Follow `SKILL.md` to run an experiment

## Conventions

- Configs: YAML | Results: JSONL | Reports: Markdown | Templates: Jinja2
- Experiment IDs: `YYYY-MM-DD-slug`
- API keys in env vars only, never committed
- Budget ceiling enforced per experiment

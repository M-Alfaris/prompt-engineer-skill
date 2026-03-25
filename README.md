# Prompt Engineer Skill

### Stop guessing. Start experimenting. Find the formula.

Most teams test 5-10 prompt variations per week by hand. This skill runs **1,000+ combinations per day** — every template, every model, every parameter setting — and tells you exactly which formula wins, why, and at what cost.

---

## The Problem

You're building an AI feature. You try a prompt. It kind of works. You tweak it. Better? Worse? Hard to tell. You try a different model. Is it worth the price difference? You adjust the temperature. Did it help or did you just get lucky on that one test?

**This is not engineering. This is guessing.**

## The Solution

Give Claude one sentence — your goal. The skill does the rest:

1. **Researches** current LLMs (pricing, APIs, capabilities) and prompt techniques via web search
2. **Builds** a matrix of every combination: prompt templates x parameter sets x models
3. **Executes** the full matrix against real APIs with budget enforcement
4. **Scores** every result using LLM-as-judge, programmatic checks, and ground truth comparison
5. **Reports** the winning formula with cost-performance analysis, ready to deploy

**One experiment. Hundreds of combinations. One clear winner.**

---

## What You Get

From a single prompt like *"optimize keyword extraction for my search engine"*:

| What | Output |
|------|--------|
| Best prompt template | Full text, copy-paste ready (`winner.yaml`) |
| Best model | With latency and cost per call |
| Best parameters | Temperature, top_p, json_mode, etc. |
| Full rankings | Every combination ranked by composite score |
| Cost-performance analysis | Pareto frontier: best quality per dollar |
| Axis analysis | Which template wins? Which model? Which temperature? |
| Raw data | Every API call with input, output, tokens, cost, latency (`all_results.jsonl`) |
| Dashboard data | Structured JSON for visualization (`report_data.json`) |

All results are stored and reusable. The next experiment builds on previous findings — it skips known losers and narrows the search space, reducing cost over time.

---

## Real Results

720 real API calls on Groq. 4 prompt strategies. 3 models. 2 temperature settings. $0.07 total:

| Rank | Template + Model + Params | Score | Latency | Cost |
|------|--------------------------|-------|---------|------|
| 1 | Few-shot + Llama 70B + t=0.0 | **9.31** | 590ms | $0.0006/call |
| 2 | Few-shot + Llama 8B + t=0.0 | **9.21** | 110ms | $0.00005/call |
| 3 | Zero-shot + Llama 70B + t=0.0 | **9.07** | 590ms | $0.0006/call |
| ... | ... | ... | ... | ... |
| 24 | Zero-shot + GPT-OSS-120B + t=0.3 | **1.05** | 711ms | broken |

The 8B model at 110ms is nearly as good as the 70B at **5x the speed and 12x cheaper**. And GPT-OSS-120B returned empty responses 75% of the time — a critical finding you'd never get from manual testing.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/m-alfaris/prompt-engineer-skill.git
cd prompt-engineer-skill/prompt-engineer
pip install -r requirements.txt

# Add your API keys (any or all providers)
cp .env.example .env
# Edit .env: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
```

### 2. Use with Claude Code

```bash
claude skill install ./prompt-engineer
```

Then just say what you need:

```
> "Test different prompt strategies for customer support chatbot"
> "Find the cheapest model for sentiment analysis with 85%+ accuracy"
> "Optimize my content moderation prompts. Use Groq. Budget $5."
> "I have these prompts that aren't working — find the best variation"
```

Claude takes over: researches, plans, builds, executes, evaluates, reports.

### 3. Use Standalone

```bash
python -m scripts.run_pipeline --experiment experiments/my-experiment/
python -m scripts.run_pipeline --experiment experiments/my-experiment/ --dry-run  # cost preview
```

---

## What Gets Tested

### The Combinations Matrix

Every experiment is a cross-product of three axes:

```
TEMPLATES (how you ask)          MODELS (who you ask)           PARAMETERS (how they answer)
  zero-shot                        Claude Sonnet                  temperature: 0.0
  few-shot (3 examples)            GPT-4o                         temperature: 0.3
  chain-of-thought                 Llama 70B on Groq              temperature: 0.7
  role + constraints               GPT-4o-mini                    json_mode: true
  hybrid few-shot + CoT            Gemini Flash                   thinking: true (Claude)
                                   Any OpenAI-compatible          top_k: 40
```

**5 templates x 3 parameter sets x 4 models = 60 combinations**. Each tested against 15-25 diverse inputs with 2-3 repetitions. That's **1,800-4,500 scored data points** from a single experiment.

### Evaluation Metrics

Every result is scored on:

- **Relevance / accuracy** — does the output actually solve the task?
- **Format compliance** — valid JSON, correct schema, right length?
- **Consistency** — same input, same quality across runs?
- **Latency** — milliseconds per call, per model
- **Cost** — dollars per call, per model, total experiment cost
- **Token usage** — input and output tokens per call
- **Custom criteria** — whatever matters for your task

Each criterion uses the best scoring method automatically:
- Subjective quality → LLM-as-judge (cheap model, different from test models)
- Format checks → programmatic code (instant, 100% consistent)
- Correct answers → ground truth comparison (F1, exact match, Jaccard)

---

## Supported Models

Works with **any LLM that has an API**:

| Provider | Models | How |
|----------|--------|-----|
| Anthropic | Claude Haiku, Sonnet, Opus | Native SDK |
| OpenAI | GPT-4o, GPT-4o-mini, o3, o4-mini | Native SDK |
| Google | Gemini Flash, Gemini Pro | Native SDK |
| Groq | Llama, Mixtral, Qwen, Gemma | OpenAI-compatible |
| Together AI | Llama, Mistral, Qwen | OpenAI-compatible |
| Fireworks | Llama, Mixtral | OpenAI-compatible |
| Ollama | Any local model | OpenAI-compatible |
| vLLM | Any self-hosted model | OpenAI-compatible |
| Any provider | Any model | If it speaks OpenAI protocol |

The skill auto-detects which API keys you have and only recommends models you can access.

---

## Supported Input Types

| Input | Pipeline | Preparation |
|-------|----------|-------------|
| Text | Standard (automatic) | None |
| Multi-field text (RAG) | Standard (automatic) | Define template variables |
| Images + text | Adapted script | Claude encodes images for each provider's format |
| Audio | Transcribe first | Whisper via Groq/OpenAI, then standard pipeline |
| Video | Extract frames + transcribe | Key frames + audio transcript |
| Tool calling | Adapted script | Define tools, Claude writes execution script |
| Multi-turn conversations | Adapted script | Structure as message arrays |
| Files (PDF, CSV) | Extract text | PDFplumber/CSV reader during build |

---

## How Costs Shrink Over Time

| Experiment | What happens | Cost |
|-----------|-------------|------|
| First run | Full matrix: 5 templates x 3 params x 4 models | $1.50 |
| Iteration 1 | Drop 2 losing templates, 1 bad model. Narrow params. | $0.40 |
| Iteration 2 | Fine-tune winning combo. Test edge cases only. | $0.15 |
| Future experiments | Start from known winners. Skip proven losers. | $0.10 |

Previous experiment results are stored and reused. The research phase reads prior `summary.yaml` and `report.md` to avoid retesting what's already been measured.

---

## Project Structure

```
prompt-engineer/
  SKILL.md                    # Orchestrator — Claude reads this first
  references/                 # Phase guides loaded on demand
    phase-research.md         #   Discover LLMs, techniques, domain context
    phase-plan.md             #   Design experiment from research
    phase-build.md            #   Create templates + test data
    phase-evaluate.md         #   Choose scoring methods per criterion
    phase-report.md           #   Synthesize findings
    input-types.md            #   Vision, audio, tools, conversations
    prompt-methodologies.md   #   15 techniques (fallback for no web)
  scripts/                    # Deterministic execution
    run_pipeline.py           #   Full pipeline, one command
    generate_matrix.py        #   Build combination matrix
    run_experiment.py         #   Execute API calls (async, budget-enforced)
    evaluate.py               #   Score results (LLM judge + code + ground truth)
    generate_report.py        #   Dashboard JSON + markdown report
    export_winner.py          #   Production-ready prompt file
    validate.py               #   Pre-flight check
    preview_prompt.py         #   See exact prompt before running
  configs/                    # Defaults + example experiment
  experiments/                # One folder per experiment (all results stored)
  ui/viewer.html              # Browser-based result viewer
```

---

## Built With

Built following [Anthropic's official skill-creator guidelines](https://github.com/anthropics/skills). Tested with 1,440+ real API calls across 3 Groq models.

## License

MIT

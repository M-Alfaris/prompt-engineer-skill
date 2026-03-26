<div align="center">

# Prompt Engineer Skill

### Stop guessing. Start experimenting. Find the formula.

*The first open-source prompt engineering experimentation framework for the Agent Skills ecosystem.*
*One goal. Thousands of combinations. One winning formula.*

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-Compatible-8A2BE2)](https://agentskills.io)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Ready-F97316)](https://claude.ai/code)
[![Cursor](https://img.shields.io/badge/Cursor-Ready-00D1FF)](https://cursor.com)
[![OpenAI Codex](https://img.shields.io/badge/OpenAI_Codex-Ready-412991)](https://developers.openai.com/codex)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://python.org)

<br/>

**Most teams test 5-10 prompt variations per week by hand.**
**This skill runs 1,000+ combinations per day — every template, every model, every parameter — and tells you exactly which formula wins, why, and at what cost.**

<br/>

</div>

---

## Works With 30+ AI Coding Tools

Built on the [Agent Skills](https://agentskills.io) open standard — install once, use everywhere.

| Tool | Type | Tool | Type |
|------|------|------|------|
| **Claude Code** | CLI | **Cursor** | IDE |
| **VS Code Copilot** | IDE | **GitHub Copilot** | IDE |
| **OpenAI Codex** | CLI | **Gemini CLI** | CLI |
| **OpenCode** | CLI | **Kiro (AWS)** | IDE |
| **Roo Code** | Extension | **Junie (JetBrains)** | IDE |
| **Amp** | CLI | **Goose (Block)** | CLI |
| **Mistral Vibe** | CLI | **TRAE (ByteDance)** | CLI |
| **OpenHands** | Agent | **Qodo** | IDE |
| **Databricks** | Platform | **Snowflake** | Platform |
| **Spring AI** | Framework | **Letta** | Framework |
| **Factory** | CLI | **Laravel Boost** | CLI |

[Full list of 32 supported tools →](https://agentskills.io)

---

## How It Works

You say: *"Optimize keyword extraction prompts for my search engine"*

The skill:
1. **Researches** current LLMs (pricing, APIs, capabilities) and prompt techniques via web search
2. **Builds** a matrix of every combination: prompt templates x parameter sets x models
3. **Executes** the full matrix against real APIs with budget enforcement
4. **Scores** every result using LLM-as-judge, programmatic checks, and ground truth comparison
5. **Reports** the winner with full cost-performance analysis and a production-ready prompt file

**One experiment. Hundreds of combinations. One clear winner.**

---

## Real Results

720 real API calls on Groq. 4 prompt strategies. 3 models. 2 temperature settings. **$0.07 total:**

| Rank | Template + Model + Params | Score | Latency | Cost/call |
|------|--------------------------|-------|---------|-----------|
| 1 | Few-shot + Llama 70B + t=0.0 | **9.31** | 590ms | $0.0006 |
| 2 | Few-shot + Llama 8B + t=0.0 | **9.21** | 110ms | $0.00005 |
| 3 | Zero-shot + Llama 70B + t=0.0 | **9.07** | 590ms | $0.0006 |

The 8B model at 110ms is nearly as good as the 70B at **5x the speed and 12x cheaper**.

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

### 2. Use with Your AI Tool

**Claude Code:**
```bash
claude skill install ./prompt-engineer
```

**Cursor / VS Code / Any Agent Skills tool:**
Drop the `prompt-engineer/` folder into your project — the tool picks up `SKILL.md` automatically.

Then just say what you need:
```
> "Test different prompt strategies for customer support chatbot"
> "Find the cheapest model for sentiment analysis with 85%+ accuracy"
> "Optimize my content moderation prompts. Use Groq. Budget $5."
```

### 3. Standalone (without any AI tool)

```bash
python -m scripts.run_pipeline --experiment experiments/my-experiment/
python -m scripts.run_pipeline --experiment experiments/my-experiment/ --dry-run  # cost preview
```

---

## The Combinations Matrix

Every experiment is a cross-product of three axes:

```
TEMPLATES (how you ask)          MODELS (who you ask)           PARAMETERS (how they answer)
  zero-shot                        Claude Sonnet                  temperature: 0.0, 0.3, 0.7
  few-shot (3 examples)            GPT-4o                         json_mode: true (if supported)
  chain-of-thought                 Llama 70B on Groq              thinking: true (Claude only)
  role + constraints               GPT-4o-mini                    top_k: 40 (if supported)
  hybrid few-shot + CoT            Gemini Flash                   frequency_penalty: 0.3
                                   Any model, any provider        seed: 42 (for reproducibility)
```

**5 templates x 3 parameter sets x 4 models = 60 combinations**, each tested against 15-25 inputs with 2-3 repetitions = **1,800-4,500 scored data points** from a single experiment.

Parameters are applied **per-model** — `json_mode` only goes to models that support it, `thinking` only to Claude, `top_k` only to providers that accept it. No wasted API calls.

---

## Evaluation Metrics

Every result is scored on:

| Metric | How |
|--------|-----|
| **Relevance / accuracy** | LLM-as-judge (subjective quality) |
| **Format compliance** | Programmatic code checks (deterministic) |
| **Correctness** | Ground truth comparison (F1, Jaccard, exact match) |
| **Consistency** | Std deviation across repetitions |
| **Latency** | Milliseconds per call |
| **Cost** | Dollars per call, per model |
| **Token usage** | Input + output tokens per call |

Each criterion uses the best method automatically. Judge model is always the cheapest available — different from the models being tested.

---

## Supported Models

Works with **any LLM that has an API:**

| Provider | How | Example Models |
|----------|-----|----------------|
| **Anthropic** | Native SDK | Claude Haiku, Sonnet, Opus |
| **OpenAI** | Native SDK | GPT-4o, GPT-4o-mini, o3, o4-mini |
| **Google** | Native SDK | Gemini Flash, Gemini Pro |
| **Groq** | OpenAI-compatible | Llama, Mixtral, Qwen |
| **Together AI** | OpenAI-compatible | Llama, Mistral, Qwen |
| **Fireworks** | OpenAI-compatible | Llama, Mixtral |
| **OpenRouter** | OpenAI-compatible | 100+ models |
| **Ollama / vLLM** | OpenAI-compatible | Any local model |

Auto-detects which API keys you have. Only recommends models you can access.

---

## Supported Input Types

| Input | How |
|-------|-----|
| **Text** | Standard pipeline (automatic) |
| **Multi-field** (RAG: context + query) | Standard pipeline (automatic) |
| **Images + text** | Agent writes adapted script per provider format |
| **Audio** | Transcribed via Whisper first, then standard pipeline |
| **Tool calling** | Agent writes tool definitions + adapted script |
| **Multi-turn conversations** | Agent writes adapted script |
| **Files** (PDF, CSV) | Extracted to text during build phase |

---

## How Costs Shrink Over Time

| Experiment | What Happens | Cost |
|-----------|-------------|------|
| First run | Full matrix: 5 templates x 3 params x 4 models | ~$1.50 |
| Iteration 1 | Drop losers, narrow parameters | ~$0.40 |
| Iteration 2 | Fine-tune winner, edge cases only | ~$0.15 |
| Future runs | Start from known winners, skip proven losers | ~$0.10 |

Previous results are stored and reused. The research phase reads prior experiments to avoid retesting.

---

## Project Structure

```
prompt-engineer/
  SKILL.md                    # Orchestrator — your AI tool reads this
  references/                 # Phase guides loaded on demand
    phase-research.md         #   Discover LLMs, techniques, domain context
    phase-plan.md             #   Design experiment from research
    phase-build.md            #   Create templates + test data
    phase-evaluate.md         #   Choose scoring methods per criterion
    phase-report.md           #   Synthesize findings
    input-types.md            #   Vision, audio, tools, conversations
  scripts/                    # Deterministic execution
    run_pipeline.py           #   Full pipeline, one command
    generate_matrix.py        #   Build combination matrix
    run_experiment.py         #   Execute API calls (async, budget-enforced)
    evaluate.py               #   Score results (multi-method)
    generate_report.py        #   Dashboard JSON + markdown report
    export_winner.py          #   Production-ready prompt file
    validate.py               #   Pre-flight check
    preview_prompt.py         #   See exact prompt before running
  configs/                    # Defaults + example experiment
  experiments/                # One folder per experiment (all results stored)
```

---

## Built With

Built following [Anthropic's skill-creator guidelines](https://github.com/anthropics/skills) and the [Agent Skills open standard](https://agentskills.io). Tested with 1,440+ real API calls.

## License

MIT

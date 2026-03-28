<div align="center">

# PromptForge

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

<!-- TODO: Add screenshot of experiment report or dashboard -->
<!-- <img src="docs/assets/demo.png" alt="Experiment results showing ranked combinations with scores, costs, and latency" width="700"/> -->

</div>

---

## What Makes This Different

**Autonomous research, not just execution.** Most prompt testing tools require you to already know what to test — write YAML configs, build datasets, pick models. This skill starts from a single sentence, researches current LLMs and prompt techniques via web search, and designs the experiment for you.

**Every combination, not just the ones you thought of.** Full factorial design crosses every template with every model and every parameter set. No cherry-picking, no gut feelings.

**Multiple evaluation methods, not just vibes.** LLM-as-judge for subjective quality, programmatic code checks for format compliance, ground truth comparison (F1, Jaccard, exact match) for accuracy, and regex pattern matching.

**Cost is a first-class metric.** Every API call logs token count, latency, and cost. Budget enforcement stops execution at your ceiling. Pareto analysis shows you the cheapest option at every quality level.

---

## How It Works

You say: *"Optimize keyword extraction prompts for my search engine"*

The skill:
1. **Researches** current LLMs (pricing, APIs, capabilities) and prompt techniques via web search
2. **Plans** a matrix of every combination — shows you the cost estimate, waits for approval
3. **Builds** prompt templates, test data, and evaluation criteria from the research
4. **Executes** the full matrix against real APIs with budget enforcement
5. **Reports** the winner with scores, cost-performance analysis, and a production-ready prompt file

**Bring your own templates** — drop existing prompts and the skill decides how to use them: as baselines for comparison, as starting points for variations, as pattern sources for new templates, or as few-shot material.

**Two workflow modes** — full factorial for thorough exploration, or fast-test for a quick smoke test on a single template.

---

## Real Experiment Results

910 real API calls on Groq. 4 prompt strategies. 3 models. 2 temperature settings. 10 test inputs with golden answers. **$0.08 total:**

| Winner | Template | Model | Temp | Score | Cost/call |
|--------|----------|-------|------|-------|-----------|
| **#1** | Few-shot (3 examples) | Llama 8B | 0.3 | **6.61** | $0.000013 |
| #2 | Few-shot (3 examples) | Llama 8B | 0.0 | 6.38 | $0.000013 |
| #3 | Few-shot (3 examples) | Llama 4 Scout | 0.3 | 6.29 | $0.000067 |

**Key findings:**
- The **8B model beat the 70B** — keyword extraction rewards speed, not reasoning depth
- **Few-shot dominated** all other techniques by a clear margin across every model
- Temperature 0.0 vs 0.3 made almost no difference (0.01 points) for this deterministic task
- **qwen3-32b failed on 22/24 cells** due to json_mode incompatibility — a production risk caught automatically before deployment
- At $0.000013/call, the winner costs **$13 per million extractions**

This experiment also ran against a content moderation task (60 cells, 2,400 evaluations, Claude Sonnet scored 9.16/10) and an ML training plan feedback task (35 cells across Groq models).

Open `viewer.html` with any experiment's `report_data.json` for an interactive dashboard.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/m-alfaris/promptforge.git
cd promptforge
pip install -r requirements.txt
```

The skill reads API keys from the `.env` file in your project root (the directory you run experiments from). If you don't have one yet, copy the example:

```bash
cp .env.example /path/to/your/project/.env
# Edit .env: GROQ_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
```

### 2. Use with Your AI Tool

**Claude Code:**
```bash
claude skill install ./promptforge
```

**Cursor / VS Code / Any Agent Skills tool:**
Drop the `promptforge/` folder into your project — the tool picks up `SKILL.md` automatically.

Then say what you need:
- "Optimize content moderation prompts for my e-commerce platform"
- "Find the best prompt for extracting data from invoices. Use Claude and GPT-4o"
- "Compare few-shot vs chain-of-thought for sentiment analysis"
- "Test 5 models to find the best one for code review prompts"
- "I have templates in prompts/ — find the best variations. Budget $20"
- "My current summarization prompt has 70% accuracy. Help me improve it through testing"

<details>
<summary><strong>3. Standalone (without any AI tool)</strong></summary>

```bash
python -m scripts.run_pipeline --experiment experiments/my-experiment/
python -m scripts.run_pipeline --experiment experiments/my-experiment/ --dry-run  # cost preview
```

</details>

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

**5 templates x 4 parameter sets x 4 models = 80 combinations**, each tested against 15-25 inputs with 3 repetitions = **3,600-6,000 scored data points** from a single experiment.

Parameters are applied **per-model** — `json_mode` only goes to models that support it, `thinking` only to Claude, `top_k` only to providers that accept it. No wasted API calls.

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

[Full list of 32 supported tools](https://agentskills.io)

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

<details>
<summary><strong>Supported Input Types</strong></summary>

| Input | How |
|-------|-----|
| **Text** | Standard pipeline (automatic) |
| **Multi-field** (RAG: context + query) | Standard pipeline (automatic) |
| **Images + text** | Agent writes adapted script per provider format |
| **Audio** | Transcribed via Whisper first, then standard pipeline |
| **Tool calling** | Agent writes tool definitions + adapted script |
| **Multi-turn conversations** | Agent writes adapted script |
| **Files** (PDF, CSV) | Extracted to text during build phase |

</details>

<details>
<summary><strong>Evaluation Methods</strong></summary>

| Method | When Used | How |
|--------|-----------|-----|
| **LLM-as-judge** | Subjective quality (relevance, coherence) | Cheap model scores 1-10 with rationale |
| **Code checks** | Format compliance (valid JSON, length) | Deterministic programmatic validation |
| **Ground truth** | Known correct answers | F1, Jaccard, exact match comparison |
| **Regex** | Pattern matching | Custom regex per criterion |
| **Cost tracking** | Every call | Token count, latency, cost per call |

Each criterion uses the best method automatically. Judge model is always the cheapest available — different from the models being tested.

</details>

---

## How Costs Shrink Over Time

| Experiment | What Happens | Cost |
|-----------|-------------|------|
| First run | Full matrix: 5 templates x 4 params x 4 models | ~$1.50 |
| Iteration 1 | Drop losers, narrow parameters | ~$0.40 |
| Iteration 2 | Fine-tune winner, edge cases only | ~$0.15 |
| Future runs | Start from known winners, skip proven losers | ~$0.10 |

Previous results are stored and reused. The research phase reads prior experiments to avoid retesting.

---

## Project Structure

```
promptforge/
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
  ui/
    viewer.html               #   Interactive dashboard for report_data.json
  evals/                      #   24+ test cases across 7 categories
  configs/                    # Defaults + example experiment
  experiments/                # One folder per experiment (all results stored)
```

---

## FAQ

<details>
<summary><strong>How much does an experiment cost?</strong></summary>

Typical range: **$0.07 to $1.50** depending on models and matrix size. Budget enforcement is built in — set a ceiling in the plan and execution stops when it's hit. The skill estimates cost before running and asks for approval.

</details>

<details>
<summary><strong>What API keys do I need?</strong></summary>

Any single provider works. The skill auto-detects available keys from your `.env` file and only recommends models you can access. You can run a full experiment with just a Groq API key (free tier).

</details>

<details>
<summary><strong>Can I use my own existing prompts?</strong></summary>

Yes. Provide template files or a folder of prompts. The skill analyzes them and decides the best approach: use as-is for baseline comparison, generate variations, extract patterns to build new templates, or mine them as few-shot examples.

</details>

<details>
<summary><strong>How long does an experiment take?</strong></summary>

A fast-test (1 template, 1 model, 5 inputs) runs in under 2 minutes. A full matrix (5 templates x 4 models x 20 inputs x 3 reps) takes 15-45 minutes depending on API rate limits and concurrency settings.

</details>

<details>
<summary><strong>Can I use local models (Ollama)?</strong></summary>

Yes. Any model accessible via an OpenAI-compatible endpoint works — Ollama, vLLM, or any custom server. Point the `base_url` to your local endpoint.

</details>

<details>
<summary><strong>What happens if a model fails mid-experiment?</strong></summary>

Failed calls are logged and skipped. Partial results are preserved. The report flags incomplete cells and works with whatever data completed successfully. You never lose progress.

</details>

---

## Contributing

Contributions welcome. The skill includes an eval system with 24+ test cases across 7 categories (trigger recognition, phase outputs, scoring stability, report completeness). See [`evals/`](promptforge/evals/) for the test suite.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Built With

Built following [Anthropic's skill-creator guidelines](https://github.com/anthropics/skills) and the [Agent Skills open standard](https://agentskills.io).

## License

[MIT](LICENSE)

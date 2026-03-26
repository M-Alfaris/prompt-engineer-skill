# Prompt Engineer Skill — Launch Copy (Ready to Post)

All copy below is ready to post. GitHub: https://github.com/M-Alfaris/prompt-engineer-skill

---

## TWITTER/X THREAD

### Tweet 1 (Hook)

Stop guessing the best prompt that works with your LLM and parameter settings.

I built an open-source skill that tests every combination for you — templates x models x parameters — and tells you which formula wins.

1,440 real API calls. $0.07 total. Works with Claude Code, Cursor, VS Code Copilot, and 29 more tools.

github.com/M-Alfaris/prompt-engineer-skill

### Tweet 2 (Problem)

The way most teams optimize prompts:

- Pick one model (gut feeling)
- Write 3 prompts (vibes)
- Test on a few examples (spreadsheet)
- Cherry-pick the "best" (confirmation bias)
- Ship it (hope it works)

This takes weeks and you're probably wrong.

### Tweet 3 (Solution)

What this skill does instead:

1. You say: "optimize keyword extraction for my search engine"
2. It web searches for current LLMs, pricing, prompt techniques
3. Builds 60+ combinations (templates x params x models)
4. Runs ALL of them against real APIs
5. Scores every result (LLM judge + code checks + ground truth)
6. Hands you the winner

### Tweet 4 (Proof)

Real experiment on Groq:

Few-shot + Llama 8B + t=0.0 = 9.21/10
Few-shot + Llama 70B + t=0.0 = 9.31/10

The 8B model at 110ms is nearly as good as 70B at 5x the speed and 12x cheaper.

Also found: gpt-oss-120b returns empty 75% of the time.

These findings cost $0.07 to discover.

### Tweet 5 (Parameters)

It doesn't just test temperature.

Each model gets its own parameter sets based on what it actually supports:

- json_mode (Groq, OpenAI)
- thinking mode (Claude only)
- top_k (Anthropic, Google)
- frequency_penalty (OpenAI, Groq)
- seed for reproducibility

Parameters are NEVER sent to models that don't support them.

### Tweet 6 (Ecosystem)

Built on the Agent Skills open standard (agentskills.io).

Works with 30+ tools:
Claude Code, Cursor, VS Code, GitHub Copilot, OpenAI Codex, Gemini CLI, OpenCode, Kiro, Roo Code, Goose, Databricks, Snowflake...

Install once. Use with any of them.

### Tweet 7 (CTA)

Open source. MIT license.

github.com/M-Alfaris/prompt-engineer-skill

Give it a goal. Get the winning prompt. Deploy.

Stop guessing.

---

## LINKEDIN POST

Stop guessing which prompt works best with your LLM and parameter settings.

Most teams manually test a handful of prompt variations, cherry-pick results, and hope the winning prompt generalizes to production. It takes weeks. It's biased. And it leaves money on the table — because you never tested the cheaper model that might work just as well.

I built an open-source skill that automates this entire process.

You describe your goal. The skill autonomously researches current LLMs and prompt techniques, builds a matrix of every combination (templates x parameters x models), executes hundreds of real API calls, scores every result using multiple evaluation methods, and delivers a report with the winning formula ready to deploy.

Real results from a keyword extraction experiment on Groq:
- 720 API calls, 4 prompt strategies, 3 models, 2 temperature settings
- Total cost: $0.07
- Finding: the 8B model at $0.00005/call scored 9.21/10 — nearly matching the 70B model at 12x the price
- Also discovered: one model returned empty responses 75% of the time (a critical production risk you'd never catch testing manually)

The skill supports per-model parameter testing — json_mode only goes to models that support it, thinking mode only to Claude, top_k only to Anthropic/Google. No wasted API calls on unsupported parameters.

Evaluation uses 4 methods per criterion: LLM-as-judge for subjective quality, programmatic code checks for format compliance, ground truth comparison for accuracy, and regex for pattern matching.

Built on the Agent Skills open standard (agentskills.io). Works with 30+ AI coding tools including Claude Code, Cursor, VS Code Copilot, GitHub Copilot, OpenAI Codex, Gemini CLI, and more.

Open source: github.com/M-Alfaris/prompt-engineer-skill

#PromptEngineering #LLM #AI #OpenSource #AgentSkills

---

## REDDIT r/MachineLearning

**Title:** [P] Open-source skill that tests 1000+ prompt/model/parameter combinations to find the optimal formula

We built an open-source Agent Skills-compatible tool that automates prompt engineering experimentation at scale.

**What it does:** You give it a task (e.g., "optimize keyword extraction"). It researches current LLMs and prompt techniques via web search, builds a combinatorial matrix (templates x parameter sets x models), executes all cells against real APIs with budget enforcement, scores every result using multiple methods (LLM-as-judge, programmatic checks, ground truth F1/Jaccard, regex), and produces a ranked report with the winning prompt.

**What makes it different from just prompting an LLM to "write a good prompt":**
- Systematic: tests every combination, not just the first one that looks good
- Multi-method evaluation: 4 scoring methods per criterion, not just vibes
- Per-model parameters: json_mode only sent to models that support it, thinking mode only to Claude
- Cost tracking: every API call logged with tokens, cost, latency
- Budget enforcement: hard stop when ceiling hit
- Reproducible: all configs, results, and scores stored as YAML/JSONL

**Real experiment:** 720 Groq API calls, 4 prompt strategies, 3 models. $0.07 total. Found that llama-8b (cheapest, fastest) scored 9.21 vs llama-70b's 9.31 — 5x faster at 12x less cost for a 1% quality difference.

Works with 30+ tools via the Agent Skills standard (agentskills.io): Claude Code, Cursor, VS Code, GitHub Copilot, OpenAI Codex, etc.

GitHub: https://github.com/M-Alfaris/prompt-engineer-skill

---

## REDDIT r/ClaudeAI

**Title:** Built a skill that automatically finds the best prompt + model + parameters for any task

Instead of manually testing prompts, this skill does it systematically:

1. Tell it your goal ("optimize my customer support chatbot")
2. It researches current LLMs and prompt techniques via web search
3. Builds a matrix of all combinations
4. Runs them against real APIs ($0.07 for 720 calls on Groq)
5. Scores everything with mixed evaluation (LLM judge + code checks + ground truth)
6. Gives you the winning prompt ready to deploy

It checks your .env to see which API keys you have and only recommends models you can actually use. Parameters are per-model — json_mode only for models that support it.

Tested with 1440+ real API calls. Works with Claude Code and 29 other tools via the Agent Skills standard.

https://github.com/M-Alfaris/prompt-engineer-skill

---

## HACKER NEWS

**Title:** Show HN: Open-source prompt engineering experimentation at scale

**Comment:**

I kept running into the same problem: testing prompts by hand is slow, biased, and misses the cheaper model that might work just as well.

This is an Agent Skills-compatible tool that builds a combinatorial matrix of prompt templates x parameter sets x models, executes all cells against real APIs, and scores results using LLM-as-judge + programmatic checks + ground truth comparison.

Key design decisions:
- Parameters are per-model (json_mode only sent to models that support it)
- Any OpenAI-compatible provider works (Groq, Together, Fireworks, Ollama, etc.)
- Budget enforcement stops execution when ceiling hit
- All results stored as JSONL for downstream analysis

Real test: 720 Groq API calls, $0.07 total. Found that llama-8b at $0.00005/call scored 9.21 vs llama-70b's 9.31.

Works with 30+ tools via agentskills.io: Claude Code, Cursor, VS Code Copilot, OpenAI Codex, Gemini CLI, etc.

https://github.com/M-Alfaris/prompt-engineer-skill

---

## PRODUCT HUNT

**Tagline:** Stop guessing which prompt works. Test them all.

**Description:**

Prompt Engineer Skill is an open-source Agent Skills-compatible tool that automates prompt engineering experimentation.

Give it a goal. It researches current LLMs, builds a matrix of every combination (templates x parameters x models), runs them all, scores every result, and hands you the winning formula.

- 1,000+ combinations tested per day
- $0.07 for a full experiment on Groq
- Works with 30+ AI tools (Claude Code, Cursor, VS Code, Copilot, etc.)
- 4 evaluation methods: LLM judge, code checks, ground truth, regex
- Per-model parameters (no unsupported params sent)
- All results stored for future experiments

MIT licensed. Built on the Agent Skills open standard.

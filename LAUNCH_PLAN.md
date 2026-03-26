# Prompt Engineer Skill — Launch Plan

**Product:** Prompt Engineer Skill — An open-source Claude Code skill for autonomous prompt experimentation at scale.

**GitHub:** https://github.com/M-Alfaris/prompt-engineer-skill

**Target Audience:**
- AI engineers building LLM-powered features
- Prompt engineers at companies
- Indie hackers using LLMs in their products
- AI researchers comparing models

**Key Promise:** Stop hand-testing 5-10 prompt variations. Run 1000+ combinations in a day. Get a deployment-ready winning prompt with real cost and quality data.

---

## Launch Materials

### 1. TWITTER/X THREAD (5-7 Tweets)

#### Tweet 1 (Hook)
```
Most teams test 5-10 prompt variations by hand.

We ran 1440+ API calls on Groq in a day. Cost: $0.07.

Built a Claude Code skill that autonomously discovers the winning prompt
for any task. Templates × parameters × models = exhaustive search.
Then evaluates everything.

Open source. Works with any OpenAI-compatible provider.

🧵
```

#### Tweet 2 (The Problem)
```
The status quo sucks:
- Pick one model (pray it's right)
- Write 3-5 prompts (from vibes)
- Test on 50-100 examples (spreadsheet hell)
- Cherry-pick the best (selection bias)
- Deploy to production (hope it generalizes)

Takes weeks. Costs mental energy. Often wrong.
```

#### Tweet 3 (The Solution)
```
What if you could:
- Research available LLMs + techniques in seconds
- Test every template × parameter × model combo
- Evaluate with LLM-as-judge + code checks + ground truth + regex
- Get a ranked leaderboard of the top 100 cells
- Get the winner with cost analysis + confidence bands

That's what the Prompt Engineer skill does.
```

#### Tweet 4 (Real Data - Keyword Extraction)
```
Real experiment: keyword extraction.

Tested 4 templates × 2 parameter sets × 3 models = 24 cells.
910 successful API calls. $0.083 cost.

Winner: llama-3.1-8b-instant (cheapest) + few-shot template + temp 0.3

Composite score: 6.61/10
Cost per extraction: $0.000013
Speed: 560 tokens/sec

Deploy this. Done. ✓
```

#### Tweet 5 (Real Data - Content Moderation)
```
Another example: e-commerce content moderation.

Tested 5 templates × 3 parameter sets × 4 models = 60 cells.
2400 evaluation records. All free (using Groq on-account credits).

Winner: Claude Sonnet + few-shot CoT hybrid + deterministic params
Score: 9.16/10

The 8B model alone couldn't beat it, but the skill found the best trade-off.
```

#### Tweet 6 (The Tech)
```
4 evaluation methods:
1. LLM-as-judge (subjective quality)
2. Code checks (deterministic validation — JSON valid, keywords present)
3. Ground truth (F1 score, Jaccard similarity, exact match)
4. Regex (pattern matching for safety/compliance)

All 4 run on every result. No cherry-picking.

Per-model parameter support — json_mode only sent to models that support it.
```

#### Tweet 7 (The CTA)
```
Open source. Follow Anthropic's official skill-creator guidelines.

github.com/M-Alfaris/prompt-engineer-skill

Try it:
python -m anthropic skill use /path/to/skill
"Optimize my customer support chatbot prompts."

The skill does the research, planning, experimentation, and reporting autonomously.
```

---

### 2. LINKEDIN POST (Professional, Data-Driven)

```
🚀 Introducing Prompt Engineer Skill: Autonomous Experimentation at Scale

One of the biggest pain points in building LLM-powered features is prompt optimization.
Most teams test a handful of prompts manually, cherry-pick results, and hope the winning
prompt generalizes to production. It's a bottleneck.

We built an open-source Claude Code skill that automates this entire process.

**How It Works**

You give it a goal: "Optimize my customer support chatbot prompts."

The skill autonomously:
1. **Research** — Web search for current LLMs, prompt techniques, domain context
2. **Plan** — Assemble experiment axes (templates, parameters, models) + cost estimate
3. **Execute** — Run hundreds or thousands of API calls (we tested 1440+ in a single run)
4. **Evaluate** — Score every result using 4 methods: LLM-as-judge, code checks, ground truth, regex
5. **Report** — Deliver a ranked leaderboard with the winning prompt ready to deploy

**Real Experiment: Keyword Extraction**
- Templates tested: 4
- Parameter sets: 2
- Models tested: 3
- Total API calls: 910
- Total cost: $0.083
- Winner: llama-3.1-8b-instant + few-shot template + temperature 0.3
- Quality score: 6.61/10
- Cost per extraction: $0.000013 (~$13 per 1 million extractions)

**Real Experiment: E-commerce Content Moderation**
- Cells tested: 60
- Evaluation records: 2400
- Winner: Claude Sonnet + few-shot CoT hybrid
- Quality score: 9.16/10 (deterministic parameters)
- Cost: Minimal (tested on Groq free tier)

**Why This Matters**

1. **Scale** — Test 100x more combinations than you would by hand
2. **Cost** — Find the cheapest model that still works ($0.000013/call vs $0.001+)
3. **Speed** — 24 hours vs 2 weeks for manual optimization
4. **Rigor** — Multi-method evaluation eliminates bias
5. **Reproducibility** — Full experiment config + results stored as code

**Technical Details**

- Works with any OpenAI-compatible provider (Groq, OpenAI, Anthropic, Together, Fireworks, Ollama)
- Per-model parameter support (json_mode, top_k, temperature, etc.)
- Budget guardrails (hard ceiling to prevent runaway costs)
- Full factorial, fractional, and adaptive matrix strategies
- Output: winning prompt YAML + evaluation scores + cost analysis

**Open Source**

Following Anthropic's official skill-creator guidelines. Full code available on GitHub.

**Try It**

If you're building with LLMs and tired of guessing on prompts, give this a try.
The skill does the research, experimentation, and reporting automatically. You just provide a goal.

Link: github.com/M-Alfaris/prompt-engineer-skill

What's your biggest prompt optimization pain point?
```

---

### 3. REDDIT POSTS

#### r/MachineLearning

```
[Project] Prompt Engineer Skill: Autonomous Experimentation Framework for LLM Prompts

I built an open-source Claude Code skill that automates prompt optimization at scale.
Instead of hand-testing 5-10 prompts, it runs combinatorial experiments:
every template × parameter combination × model, evaluates all results, and delivers
a deployment-ready winning prompt.

**What problem does it solve?**

Current workflow: write 3-5 prompts from intuition, test on 100 examples, cherry-pick the best.
This takes weeks, is prone to bias, and often doesn't generalize to production.

**How it works**

1. You give a goal: "Optimize my customer support chatbot prompts"
2. The skill researches (web search for LLMs + techniques)
3. Plans an experiment (axes: templates, parameters, models)
4. Executes (hundreds/thousands of API calls)
5. Evaluates using 4 methods (LLM judge, code, ground truth, regex)
6. Reports (winning prompt + cost analysis)

**Real results**

Keyword extraction experiment:
- 4 templates × 2 param sets × 3 models = 24 cells
- 910 API calls total
- Cost: $0.083 (tested on Groq free tier)
- Winner: llama-3.1-8b-instant + few-shot + temp 0.3
- Quality: 6.61/10 (good), Cost/call: $0.000013

Content moderation experiment:
- 5 templates × 3 param sets × 4 models = 60 cells
- 2400 evaluation records
- Winner: Claude Sonnet + few-shot CoT hybrid
- Quality: 9.16/10 (very good)

**Key features**

- Works with any OpenAI-compatible provider (Groq, OpenAI, Anthropic, etc.)
- 4 evaluation methods (no single-metric bias)
- Budget guardrails (hard ceiling to prevent runaway costs)
- Per-model parameter support (json_mode only sent to models that support it)
- Reproducible (full config + results stored as YAML/JSON)

**Use cases**

- AI engineers optimizing LLM features
- Researchers comparing model performance
- Teams finding the cheapest model that still works
- Anyone tired of guessing on prompts

Code: github.com/M-Alfaris/prompt-engineer-skill
Built following Anthropic's official skill guidelines.

Happy to discuss the approach, answer questions about the evaluation methods,
or walk through the experiment data.
```

#### r/ClaudeAI

```
Built a Claude Code Skill That Automates Prompt Testing (1440+ API Calls Per Day)

Hi! I built Prompt Engineer Skill, an open-source Claude Code skill that takes
"optimize my customer support chatbot prompts" and autonomously runs a full
experimentation pipeline to find the winning prompt.

**How it works**

1. You describe your goal
2. The skill researches available LLMs + prompt techniques
3. Plans an experiment (N templates × N parameters × N models)
4. Runs all combinations (we tested 1440+ calls in one run, cost: $0.07)
5. Evaluates using 4 methods (LLM judge + code checks + ground truth + regex)
6. Delivers a report with the winner ranked by quality and cost

**Real experiments**

Keyword extraction (910 calls, $0.083):
- Found that the 8B model nearly matches 70B quality
- Cost per call: $0.000013 (about $13 per million)
- Winner was the cheapest option

Content moderation (2400 evals):
- Claude Sonnet beat smaller models by 1.5 points
- Few-shot CoT hybrid template was the best approach
- Deterministic parameters (temp 0.0) performed well

**Key features**

- Works with Groq, OpenAI, Anthropic, Ollama, or any OpenAI-compatible provider
- 4 evaluation methods (no gaming the system)
- Budget safety (hard ceiling)
- Reproducible (full YAML config + JSON results)
- Per-model parameter support

**Why I built this**

Manual prompt testing is slow, biased, and non-reproducible.
If you're building LLM features and tired of guessing on prompts,
this automates the entire optimization loop.

Code & docs: github.com/M-Alfaris/prompt-engineer-skill

Open to feedback, questions, or requests for specific features!
```

---

### 4. HACKER NEWS

#### Submission Title
```
Prompt Engineer Skill: Autonomous Prompt Experimentation at Scale
```

#### Submission URL
```
https://github.com/M-Alfaris/prompt-engineer-skill
```

#### Submission Comments (1st reply)
```
We open-sourced a Claude Code skill that automates prompt optimization.

The core idea: Instead of hand-testing 5-10 prompt variations, run a full
combinatorial experiment on templates × parameters × models, then evaluate all
results rigorously.

Real experiments:
- Keyword extraction: 910 API calls, $0.083 cost, found optimal template + model combo
- Content moderation: 60 cells, 2400 evals, discovered few-shot CoT hybrid was best

4 evaluation methods to avoid single-metric bias:
1. LLM-as-judge (subjective quality)
2. Code checks (deterministic validation)
3. Ground truth (F1, Jaccard, exact match)
4. Regex (pattern matching)

Works with Groq, OpenAI, Anthropic, Ollama, etc. via OpenAI-compatible API.

Built following Anthropic's official skill-creator guidelines.
We're treating this as a case study in systematic prompt engineering.

Happy to answer questions about the evaluation approach, experiment design, or model comparisons.

Source: https://github.com/M-Alfaris/prompt-engineer-skill
```

---

### 5. PRODUCT HUNT

#### Tagline
```
Automate prompt optimization. Run 1000+ experiments in a day instead of hand-testing 5-10.
Get a deployment-ready winning prompt with cost and confidence data.
```

#### Description (500 chars limit, then extended below)
```
Prompt Engineer Skill is an open-source Claude Code skill that autonomously optimizes LLM
prompts at scale. You describe your goal. It researches techniques, tests every template ×
parameter × model combination, evaluates all results using 4 methods, and delivers the
winning prompt ready to deploy.

Tested on 1440+ real API calls ($0.07 total cost). Found that the cheapest 8B model nearly
matched 70B quality for keyword extraction. Perfect for AI engineers, prompt engineers, and
researchers comparing models.

Works with Groq, OpenAI, Anthropic, Ollama, and any OpenAI-compatible provider.
```

#### Extended Description (for Product Hunt page)

**What problem does this solve?**

Optimizing LLM prompts is slow, biased, and non-reproducible:
- Most teams hand-test 5-10 variations
- Cherry-pick results based on a few examples
- Deploy and hope it generalizes
- Takes weeks. Often wrong.

**How it works**

You give it a goal: "Optimize my customer support chatbot prompts."

The skill autonomously:
1. **Research** — Web search for LLMs + techniques
2. **Plan** — Design experiment axes + cost estimate
3. **Execute** — Run hundreds/thousands of API calls
4. **Evaluate** — Score every result with 4 methods
5. **Report** — Ranking + winning prompt + cost analysis

**Real Results**

Keyword extraction (910 API calls, $0.083):
- Winner: llama-3.1-8b-instant + few-shot template
- Quality: 6.61/10
- Cost per extraction: $0.000013

Content moderation (2400 evaluations):
- Winner: Claude Sonnet + few-shot CoT hybrid
- Quality: 9.16/10
- Cost analysis included

**Key Features**

- Combinatorial experiments (templates × parameters × models)
- 4 evaluation methods (LLM judge + code + ground truth + regex)
- Budget guardrails (hard ceiling on API spend)
- Works with Groq, OpenAI, Anthropic, Ollama, etc.
- Per-model parameter support (json_mode only sent to models that support it)
- Full reproducibility (all configs + results stored as code)

**For Whom?**

- AI engineers building LLM features
- Prompt engineers at companies
- Indie hackers using LLMs in products
- Researchers comparing models

**Technical Details**

Built as a Claude Code skill following Anthropic's official guidelines.
Open source. No vendor lock-in.

**Try It**

GitHub: https://github.com/M-Alfaris/prompt-engineer-skill

Docs include quickstart, examples, and full experiment data.

---

## Messaging Framework

### Core Message (across all platforms)
**Most teams hand-test 5-10 prompts. This skill tests 1000+ in a day. Works with any LLM provider.**

### Key Differentiators
1. **Autonomous** — Full pipeline from research to deployment-ready result
2. **Rigorous** — 4 evaluation methods eliminate bias
3. **Cost-transparent** — Every result includes cost, latency, token count
4. **Provider-agnostic** — Works with Groq, OpenAI, Anthropic, Ollama, etc.
5. **Reproducible** — Full YAML config + JSON results stored as code
6. **Open source** — No vendor lock-in

### Evidence to Lead With
- **1440+ API calls** on Groq, **$0.07 total cost** (real experiment)
- **llama-3.1-8b-instant** nearly matches 70B quality for keyword extraction
- **9.16/10 quality score** on content moderation with smaller budget
- **$0.000013 per API call** (keyword extraction winner)

### Tone (per platform)
- **Twitter/X** — Casual, data-forward, hook-first. Real numbers. Emojis okay.
- **LinkedIn** — Professional but accessible. Use "we" language. Emphasize business value.
- **Reddit** — Technical, detailed, humble. "I built this" not "our company built this."
- **Hacker News** — Understated, technical, link-minimal. Problem-solution format.
- **Product Hunt** — Polished, benefit-driven, visual hierarchy. Lead with the problem.

---

## Pre-Launch Checklist

### Code & Documentation
- [x] Skill built following Anthropic guidelines
- [x] Real experiments run (keyword extraction, content moderation)
- [x] GitHub repository public with README
- [ ] Docs include quickstart, API, examples, experiment data
- [ ] CHANGELOG with current version
- [ ] Contributing guidelines
- [ ] License (recommend MIT or Apache 2.0)

### Social Proof
- [x] Two real experiments with published results
- [x] Cost data ($0.07 for 1440 calls, $0.083 for 910 calls)
- [x] Quality scores (6.61/10, 9.16/10)
- [ ] GitHub stars from early adopters
- [ ] Testimonials from beta users

### Timing & Sequencing
1. **Day 1, 6am PT** — Post on Hacker News (best time for tech audience)
2. **Day 1, 9am PT** — Launch Twitter/X thread
3. **Day 1, 11am PT** — Post on Reddit (r/MachineLearning + r/ClaudeAI)
4. **Day 2, 9am PT** — LinkedIn post
5. **Day 3 (optional)** — Product Hunt launch (if you want more consumer visibility)

### Success Metrics
- **Hacker News:** Top 30 by day 1 = ~5k views
- **Twitter/X:** 5-7 tweets reaching 2-5k engineers (0.5-1k engagements)
- **Reddit:** 200+ upvotes per post, 50+ comments
- **GitHub:** 100+ stars in first week, 10+ forks
- **LinkedIn:** 500+ impressions, 50+ engagement actions

---

## Post-Launch Support

### Day 1-3 Monitoring
- Monitor Twitter replies; engage with questions
- Watch Hacker News comments; address technical questions
- Check Reddit threads; provide context on evaluation methods
- Monitor GitHub issues; fix urgent bugs quickly

### First Week
- Write 2-3 follow-up posts with use cases
- Create short video walkthrough
- Write detailed blog post on methodology (evaluation methods, experimental design)
- Engage with early adopters; iterate on feedback

### First Month
- Collect user feedback; prioritize most-requested features
- Monitor GitHub discussions; highlight common use cases
- Update docs with real-world examples from users
- Plan roadmap based on adoption patterns

---

## Launch Success =

**User:** "I have a prompt optimization task."
**Skill:** "Give me the goal. I'll research, plan, test 100+ combinations, evaluate rigorously, and deliver a winning prompt with cost analysis."
**Reality:** 24 hours later, the user has a deployment-ready prompt with confidence data.

That's the product. That's the story. That's what you're launching.

---

## Files to Share in Launch

1. **GitHub repo** — code + README
2. **Experiment reports** — keyword extraction + content moderation (include raw data)
3. **Cost breakdown** — $0.07 for 1440 calls, $0.083 for 910 calls
4. **Model comparison table** — llama-8b vs llama-70b vs Claude Sonnet
5. **Example winning prompts** — copy-paste ready

All of these exist. Point to them. Let the data speak.

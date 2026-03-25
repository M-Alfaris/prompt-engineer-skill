# LLM Quick Reference

Model profiles and comparison data for experiment planning. Costs are approximate and subject to change. Verify current pricing at provider documentation before finalizing budgets.

---

## Model Profiles

### Claude Haiku 4.5
- **Provider:** Anthropic
- **Context window:** 200K tokens
- **Max output:** 8K tokens
- **Cost (input / output):** $0.00080 / $0.00400 per 1K tokens
- **Strengths:** Fastest Anthropic model. Strong instruction following. Excellent for high-volume, structured tasks.
- **Weaknesses:** Reduced reasoning depth on complex multi-step tasks compared to Sonnet/Opus.
- **Best use cases:** Classification, extraction, summarization, format conversion, high-throughput pipelines.

---

### Claude Sonnet 4
- **Provider:** Anthropic
- **Model ID:** `claude-sonnet-4-20250514`
- **Context window:** 200K tokens
- **Max output:** 16K tokens
- **Cost (input / output):** $0.00300 / $0.01500 per 1K tokens
- **Strengths:** Best balanced model in the Anthropic lineup. Strong reasoning, coding, and analysis. Reliable instruction following.
- **Weaknesses:** Higher cost than Haiku. Not needed for simple tasks.
- **Best use cases:** Code generation, analysis, complex Q&A, multi-step reasoning, judge model in LLM-as-judge evaluation.

---

### Claude Opus 4
- **Provider:** Anthropic
- **Model ID:** `claude-opus-4-20250514`
- **Context window:** 200K tokens
- **Max output:** 32K tokens
- **Cost (input / output):** $0.01500 / $0.07500 per 1K tokens
- **Strengths:** Highest reasoning capability in the Anthropic lineup. Best for nuanced, ambiguous, or high-stakes tasks.
- **Weaknesses:** Most expensive Anthropic model. Significant overkill for straightforward tasks.
- **Best use cases:** Complex research synthesis, advanced coding, legal/medical analysis, tasks requiring deep judgment.

---

### GPT-4o
- **Provider:** OpenAI
- **Context window:** 128K tokens
- **Max output:** 16K tokens
- **Cost (input / output):** $0.00250 / $0.01000 per 1K tokens
- **Strengths:** Strong multimodal capability. Fast for its tier. Wide tool/function-calling ecosystem.
- **Weaknesses:** Shorter context than Anthropic models. Output can be verbose without explicit length constraints.
- **Best use cases:** Multimodal tasks, function calling, broad general-purpose tasks, OpenAI ecosystem integrations.

---

### GPT-4o-mini
- **Provider:** OpenAI
- **Context window:** 128K tokens
- **Max output:** 16K tokens
- **Cost (input / output):** $0.00015 / $0.00060 per 1K tokens
- **Strengths:** Extremely low cost. Surprisingly capable for its price point. Good for high-volume simple tasks.
- **Weaknesses:** Noticeably weaker on reasoning and nuanced instruction following vs. GPT-4o.
- **Best use cases:** High-volume classification, simple extraction, budget experiments, smoke testing.

---

### o3
- **Provider:** OpenAI
- **Context window:** 200K tokens
- **Max output:** 100K tokens
- **Cost (input / output):** $0.01000 / $0.04000 per 1K tokens
- **Strengths:** Top-tier reasoning via chain-of-thought compute scaling. Best OpenAI model for math, science, and complex code.
- **Weaknesses:** High cost. Slower due to internal reasoning compute. Not suitable for latency-sensitive tasks.
- **Best use cases:** Advanced math, competitive programming, research-level analysis, tasks that demand maximum reasoning.

---

### o4-mini
- **Provider:** OpenAI
- **Context window:** 200K tokens
- **Max output:** 65K tokens
- **Cost (input / output):** $0.00110 / $0.00440 per 1K tokens
- **Strengths:** Strong reasoning at significantly lower cost than o3. Good balance of capability and cost for reasoning tasks.
- **Weaknesses:** Less capable than o3 on the hardest tasks. Still slower than non-reasoning models.
- **Best use cases:** Moderate-complexity reasoning, STEM tasks, cost-sensitive agentic workflows.

---

### Gemini 2.0 Flash
- **Provider:** Google
- **Context window:** 1M tokens
- **Max output:** 8K tokens
- **Cost (input / output):** $0.00010 / $0.00040 per 1K tokens
- **Strengths:** Largest context window of any model listed. Extremely low cost. Fast response times.
- **Weaknesses:** Instruction following less reliable than Anthropic/OpenAI models on complex tasks. Output quality varies.
- **Best use cases:** Long-document tasks, cost-sensitive pipelines, tasks requiring very long context, document Q&A.

---

### Gemini 2.0 Pro
- **Provider:** Google
- **Context window:** 1M tokens
- **Max output:** 8K tokens
- **Cost (input / output):** $0.00125 / $0.00500 per 1K tokens
- **Strengths:** Strongest Google model. 1M token context. Improved instruction following over Flash.
- **Weaknesses:** Still trails Anthropic and OpenAI top models on reasoning benchmarks. Limited ecosystem tooling.
- **Best use cases:** Very long document analysis, multi-document synthesis, tasks benefiting from 1M context.

---

### Llama 3 (via Ollama)
- **Provider:** Local (Meta, self-hosted)
- **Model variants:** llama3:8b, llama3:70b
- **Context window:** 8K tokens (8b), 8K tokens (70b)
- **Max output:** 4K tokens
- **Cost:** $0 per token (compute cost only)
- **Strengths:** Zero API cost. Data never leaves the machine. No rate limits.
- **Weaknesses:** Requires local GPU/CPU. 8b model significantly weaker than cloud alternatives. Setup complexity.
- **Best use cases:** Privacy-sensitive data, offline environments, cost elimination for high-volume internal tasks.

---

### Mistral Large
- **Provider:** Mistral AI
- **Context window:** 32K tokens
- **Max output:** 8K tokens
- **Cost (input / output):** $0.00200 / $0.00600 per 1K tokens
- **Strengths:** Strong multilingual performance. Good code generation. European provider for data residency compliance.
- **Weaknesses:** Smaller context window than Anthropic/Google. Narrower ecosystem support.
- **Best use cases:** Multilingual tasks, European data compliance requirements, code generation, mid-tier reasoning tasks.

---

## Comparison Table

| Model | Provider | Context | Cost/1K in | Cost/1K out | Tier | Best For |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | Anthropic | 200K | $0.00080 | $0.00400 | Budget | Volume, extraction |
| GPT-4o-mini | OpenAI | 128K | $0.00015 | $0.00060 | Budget | High-volume, cost-first |
| Gemini 2.0 Flash | Google | 1M | $0.00010 | $0.00040 | Budget | Long context, cost-first |
| o4-mini | OpenAI | 200K | $0.00110 | $0.00440 | Budget/Reasoning | Reasoning on a budget |
| Claude Sonnet 4 | Anthropic | 200K | $0.00300 | $0.01500 | Balanced | General purpose, default choice |
| GPT-4o | OpenAI | 128K | $0.00250 | $0.01000 | Balanced | Multimodal, tool use |
| Gemini 2.0 Pro | Google | 1M | $0.00125 | $0.00500 | Balanced | Long-doc analysis |
| Mistral Large | Mistral | 32K | $0.00200 | $0.00600 | Balanced | Multilingual, EU compliance |
| Claude Opus 4 | Anthropic | 200K | $0.01500 | $0.07500 | Premium | Deep reasoning, judgment |
| o3 | OpenAI | 200K | $0.01000 | $0.04000 | Premium | Math, science, hard code |
| Llama 3 70b | Local | 8K | $0.00000 | $0.00000 | Local | Privacy, offline, no budget |

---

## Tier Guidance

**Budget tier:** Use when the task is well-defined, output is structured, and volume is high. Always include a budget model as a baseline comparison.

**Balanced tier:** Default choice for most experiments. `claude-sonnet-4-20250514` is the recommended default judge model for LLM-as-judge evaluation.

**Premium tier:** Reserve for tasks where a balanced model demonstrably fails or where quality has direct business impact justifying the cost premium. Always verify the premium model outperforms the balanced model on your specific task before committing.

**Local:** Use when data privacy requirements prohibit external API calls or when budget is exhausted. Expect lower baseline quality; calibrate success thresholds accordingly.

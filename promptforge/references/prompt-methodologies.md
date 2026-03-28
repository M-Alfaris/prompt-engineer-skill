# Prompt Methodologies Encyclopedia

Reference for selecting and applying prompt engineering techniques. Each entry covers: description, when to use, example, strengths, and weaknesses.

---

## 1. Zero-Shot Prompting

**Description:** Provide a task instruction with no examples. The model relies entirely on its pre-trained knowledge to interpret and execute the task. No demonstrations or scaffolding are included.

**When to use:** The task is well-defined and within the model's training distribution. Speed and brevity matter. Use as the baseline in every experiment before adding complexity.

**Example:**
```
Classify the sentiment of this review as POSITIVE, NEGATIVE, or NEUTRAL.
Review: "The battery died after three hours."
Sentiment:
```

**Strengths:** Minimal tokens, low latency, easy to maintain, generalizes well to novel inputs.

**Weaknesses:** Fails on ambiguous tasks, niche domains, or tasks requiring implicit world knowledge the model lacks.

---

## 2. Few-Shot Prompting

**Description:** Provide 2-8 labeled examples before the target input. The examples demonstrate the expected input-output pattern without explaining it. The model infers the task from the pattern.

**When to use:** The output format is non-obvious, the task has domain-specific conventions, or zero-shot performance is inconsistent.

**Example:**
```
Input: "I love this product!" → POSITIVE
Input: "It broke immediately." → NEGATIVE
Input: "It's fine, I guess." → NEUTRAL
Input: "Worst purchase ever." →
```

**Strengths:** Dramatically improves format compliance and task understanding. Does not require model fine-tuning.

**Weaknesses:** Increases prompt length and cost. Example quality matters — bad examples degrade performance. Example selection and ordering affects results.

---

## 3. Chain-of-Thought (CoT)

**Description:** Instruct the model to reason step-by-step before producing the final answer. Either demonstrate this reasoning in few-shot examples ("Let's think step by step...") or prompt for it directly.

**When to use:** Multi-step reasoning, math problems, logical inference, or any task where the path to the answer is as important as the answer itself.

**Example:**
```
Q: A store sells apples for $0.50 each. If I buy 7 apples and pay with $5, how much change do I get?
A: Let's think step by step.
   Cost = 7 × $0.50 = $3.50
   Change = $5.00 − $3.50 = $1.50
   Answer: $1.50
```

**Strengths:** Significantly improves accuracy on reasoning tasks. Makes model reasoning auditable. Enables self-correction.

**Weaknesses:** Substantially increases output tokens and cost. Slower latency. Can produce confident-sounding but incorrect reasoning chains.

---

## 4. Tree-of-Thought (ToT)

**Description:** Extend chain-of-thought by generating multiple reasoning branches at each step, evaluating their promise, and pruning dead ends. The model explores a tree of possible reasoning paths rather than a single chain.

**When to use:** Complex planning, creative generation with constraints, or tasks where the first reasoning path is likely to be suboptimal (e.g., puzzles, multi-constraint optimization).

**Example:**
```
Generate three different approaches to solving this problem. For each approach, rate its likelihood of success (High/Medium/Low) and explain why. Then develop only the High-rated approach fully.

Problem: {{ problem_statement }}
```

**Strengths:** Finds better solutions than single-path CoT on hard tasks. Enables deliberate exploration.

**Weaknesses:** Very high token cost. Requires multiple model calls or a long single call. Overkill for simple tasks.

---

## 5. ReAct (Reason + Act)

**Description:** Interleave reasoning steps ("Thought:") with action invocations ("Action:") and observations ("Observation:"). The model plans an action, observes the result, updates its reasoning, and continues.

**When to use:** Tasks that require tool use, web search, code execution, or database lookups. Any agentic workflow where the model must interact with external systems.

**Example:**
```
Thought: I need to find the current price of AAPL stock.
Action: search("AAPL stock price today")
Observation: AAPL is trading at $189.42.
Thought: Now I can answer the question.
Answer: AAPL is currently $189.42.
```

**Strengths:** Grounds model output in real-world data. Enables dynamic, multi-step workflows.

**Weaknesses:** Requires a tool execution layer. Latency is high due to multiple turns. Error handling for failed actions must be designed explicitly.

---

## 6. Self-Consistency

**Description:** Generate the same prompt multiple times (3-10 runs) with non-zero temperature, then aggregate results by majority vote or highest-frequency answer. Exploits the diversity of model outputs to find the most reliable answer.

**When to use:** Tasks with a single correct answer where the model shows inconsistency (classification, math, factual Q&A). Useful when confidence matters more than speed.

**Example:**
Run the same math problem prompt 5 times at temperature 0.7. If 4 out of 5 runs produce "42", use 42 as the final answer.

**Strengths:** Improves reliability without changing the base prompt. Works with any prompting style.

**Weaknesses:** Multiplies API calls and cost by N. Not applicable to open-ended generation tasks where there is no single correct answer.

---

## 7. Structured Output Forcing

**Description:** Explicitly specify the output format in the prompt using a schema, template, or example structure. Instruct the model to fill slots rather than generate freely.

**When to use:** When downstream code must parse the model's response. JSON APIs, form filling, data extraction, any machine-readable output.

**Example:**
```
Extract the entities from the text below. Respond ONLY with valid JSON matching this schema exactly:
{"person": string, "organization": string, "date": string}
If a field is not found, use null.

Text: {{ input_text }}
```

**Strengths:** Near-100% format compliance when combined with model-native JSON mode. Eliminates parsing errors.

**Weaknesses:** Rigid schema can cause the model to hallucinate field values rather than admit absence. Requires explicit null handling.

---

## 8. Role Prompting

**Description:** Assign the model a functional role or professional identity in the system prompt. The role shapes the model's perspective, vocabulary, and priorities without specifying a fictional persona.

**When to use:** Technical tasks where domain framing improves precision (e.g., "You are a senior security auditor"). Effective for code review, legal drafting, medical triage, financial analysis.

**Example:**
```
You are a senior software engineer specializing in Python performance optimization. Review the code below and identify the three most impactful performance bottlenecks. Be specific and cite line numbers.
```

**Strengths:** Activates domain-specific knowledge and tone. Improves response depth on technical topics.

**Weaknesses:** Can cause the model to refuse edge-case inputs that conflict with the assigned role's norms. Over-specified roles can reduce flexibility.

---

## 9. Persona Prompting

**Description:** Assign the model a named character or audience-specific voice. Unlike role prompting (functional), persona prompting shapes communication style, assumed knowledge level, and personality.

**When to use:** Customer-facing applications where tone matters (friendly assistant, brand voice), educational tools calibrated to a reading level, or creative writing tasks.

**Example:**
```
You are Alex, a friendly and patient customer support agent for a software company. You speak in short sentences, avoid jargon, and always end responses with an offer to help further.
```

**Strengths:** Produces consistent tone across diverse inputs. Effective for brand-voice alignment.

**Weaknesses:** Persona constraints can conflict with factual accuracy requirements. A "friendly" persona may soften important warnings.

---

## 10. Constraint Prompting

**Description:** Define explicit rules the model must follow, either as a numbered list in the system prompt or as inline constraints in the user prompt. Constraints can cover content, format, length, or behavior.

**When to use:** Any production prompt that has non-negotiable requirements (e.g., response must not exceed 100 words, must not recommend specific brands, must always cite sources).

**Example:**
```
Rules you must follow:
1. Never recommend specific medication dosages.
2. Always recommend consulting a licensed physician.
3. Responses must be under 150 words.
4. Use plain language at a 6th-grade reading level.
```

**Strengths:** Directly reduces policy violations and format errors. Easy to audit and update.

**Weaknesses:** Long constraint lists consume tokens and can create conflicts (e.g., "be concise" vs. "be comprehensive"). Models do not always follow all constraints simultaneously.

---

## 11. Decomposition

**Description:** Break a complex task into smaller subtasks and instruct the model to complete them in sequence. Either chain multiple prompts or ask the model to decompose the task itself before executing.

**When to use:** Long-form generation (reports, analysis), tasks with multiple independent components, or any task that exceeds the model's reliable single-pass capability.

**Example:**
```
Complete the following task in three steps. Show your work for each step before moving to the next.
Step 1: Summarize the key claims in the document below.
Step 2: Identify evidence that supports each claim.
Step 3: Write a critical evaluation of the argument's strength.

Document: {{ document_text }}
```

**Strengths:** Improves quality on complex tasks. Makes failure points identifiable. Intermediate outputs are auditable.

**Weaknesses:** Increases prompt length. Errors in early steps propagate. Requires sequential execution.

---

## 12. Meta-Prompting

**Description:** Ask the model to generate, improve, or evaluate a prompt rather than execute a task directly. The model acts as a prompt engineer, producing optimized instructions for another model call.

**When to use:** Bootstrapping prompt creation, automating prompt iteration, or generating task-specific few-shot examples at scale.

**Example:**
```
You are an expert prompt engineer. Your task is to write a system prompt for a model that must classify customer support tickets into five categories. The prompt must be under 200 words and include two examples per category.
```

**Strengths:** Scales prompt creation. Produces prompts that are well-calibrated to model behavior. Useful for generating diverse template variants.

**Weaknesses:** Output quality depends on meta-prompt quality (circular dependency). Generated prompts require validation before deployment.

---

## 13. Emotional Prompting

**Description:** Add emotional context, stakes, or urgency to the prompt to activate more careful and thorough model behavior. Phrases like "This is very important" or "Take your time and think carefully" have been shown empirically to improve accuracy.

**When to use:** High-stakes tasks where thoroughness matters (legal, medical, financial), or when baseline outputs are superficial. Use sparingly — overuse dilutes the effect.

**Example:**
```
This analysis will be used to brief senior executives. Accuracy is critical. Please review the data carefully before responding.
```

**Strengths:** Low-cost improvement requiring only a few added tokens. Measurable accuracy gains on reasoning tasks.

**Weaknesses:** Effect size is small and inconsistent across models and task types. Not a substitute for structural improvements.

---

## 14. Retrieval-Augmented Generation (RAG)

**Description:** Inject relevant context retrieved from an external knowledge base into the prompt before the model generates a response. The model answers based on the retrieved content rather than relying solely on parametric memory.

**When to use:** Tasks requiring up-to-date information, proprietary knowledge, or domain content not in the model's training data (documentation, policies, product catalogs).

**Example:**
```
Use ONLY the context below to answer the question. If the answer is not in the context, say "I don't know."

Context:
{{ retrieved_documents }}

Question: {{ user_question }}
```

**Strengths:** Dramatically reduces hallucinations. Keeps the model grounded in verifiable sources. Allows knowledge updates without retraining.

**Weaknesses:** Requires a retrieval infrastructure (vector database, search index). Context window limits cap how much can be injected. Retrieval quality directly caps answer quality.

---

## 15. Step-Back Prompting

**Description:** Before answering the specific question, ask the model to first answer a more abstract or general version of the question ("step back"). Use that high-level reasoning as context to answer the original question.

**When to use:** Factual questions that benefit from reasoning from first principles, physics or science problems, questions where the model tends to make specific errors due to surface-level pattern matching.

**Example:**
```
Before answering, first answer this more general question: What are the general principles governing {{ topic }}?

General answer: [model fills this in]

Now use those principles to answer: {{ specific_question }}
```

**Strengths:** Reduces errors caused by overfitting to superficial question features. Improves accuracy on knowledge-intensive tasks.

**Weaknesses:** Adds one reasoning layer and increases token usage. Not beneficial for tasks that are already well-specified.

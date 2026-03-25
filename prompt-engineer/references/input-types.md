# Reference: Input Types, Provider Selection, and Preparation

Load this file during RESEARCH when detecting non-text inputs, or during PLAN when selecting models and judges.

---

## Step 0: Check What the User Has Access To

Before recommending ANY models or judges, check which API keys exist:

```bash
cat .env
```

Only recommend models from providers the user has keys for. Map keys to providers:

| Env Variable | Provider | Models Available |
|-------------|----------|-----------------|
| `ANTHROPIC_API_KEY` | Anthropic | Claude Haiku, Sonnet, Opus |
| `OPENAI_API_KEY` | OpenAI | GPT-4o, GPT-4o-mini, o3, o4-mini |
| `GOOGLE_API_KEY` | Google | Gemini Flash, Gemini Pro |
| `GROQ_API_KEY` | Groq | Llama, Mixtral, Gemma (via OpenAI-compatible) |
| `TOGETHER_API_KEY` | Together AI | Llama, Mistral, Qwen (via OpenAI-compatible) |
| `FIREWORKS_API_KEY` | Fireworks | Llama, Mixtral (via OpenAI-compatible) |
| No key needed | Ollama (local) | Any model user has pulled locally |

If the user only has `GROQ_API_KEY`:
- All experiment models must be Groq models
- The judge model must also be a Groq model
- Do NOT recommend Claude or GPT-4o — the user can't access them

If the user has multiple keys, prefer the provider they mentioned or the one with the cheapest models for the task.

---

## Picking the Judge Model

The judge must come from a provider the user has access to. Apply these rules:

1. **Read .env** — which API keys exist?
2. **Pick from those providers only** — never recommend a judge the user can't call
3. **Pick the cheapest model** from available providers — the judge prompt is simple (score 1-10 + one sentence), any model handles it
4. **Pick a different model than the ones being tested** — avoids self-evaluation bias
5. **Set judge max_tokens to 150** — the response is just JSON with a score and rationale

| If user has... | Recommended judge |
|----------------|-------------------|
| Only Groq | Cheapest Groq text model (e.g., llama-8b-instant) |
| Only OpenAI | gpt-4o-mini |
| Only Anthropic | claude-haiku |
| Only Google | gemini-flash |
| Multiple providers | Cheapest model from a provider NOT being tested |

---

## Parameter-Provider Compatibility

Not every parameter works on every provider. Only include parameters the target models support.

| Parameter | Anthropic | OpenAI | Google | Groq | Ollama |
|-----------|-----------|--------|--------|------|--------|
| temperature | yes | yes | yes | yes | yes |
| max_tokens | yes | yes | yes (as max_output_tokens) | yes | yes (as num_predict) |
| top_p | yes | yes | yes | yes | yes |
| top_k | yes | no | yes | no | yes |
| json_mode | yes (via tool_use) | yes (response_format) | yes (response_mime_type) | yes (response_format) | yes (format: json) |
| frequency_penalty | no | yes | no | yes | yes (repeat_penalty) |
| presence_penalty | no | yes | no | yes | no |
| thinking / thinking_budget | yes (Claude only) | no | no | no | no |
| seed | no | yes | no | yes | yes |
| stop_sequences | yes (stop_sequences) | yes (stop) | yes (stop_sequences) | yes (stop) | yes (stop) |

When creating parameter sets in plan.yaml, only include parameters the target models support. If testing across providers with different parameter support, create provider-specific parameter sets or omit unsupported parameters (the API will ignore unknown params in most cases, but some will error).

---

## Input Types — How to Prepare Each

### Text Only (standard pipeline)

No preparation needed. Test data has `text` field, templates use `{{ input }}`.

### Multi-Field Text (standard pipeline)

Multiple text fields per input (e.g., RAG context + query). Templates use matching variables.

```yaml
inputs:
  - id: "001"
    context: "The retrieved document text..."
    query: "What is the key finding?"
```

Template: `{{ context }}` and `{{ query }}` — standard pipeline handles this.

### Audio → Text (prepare before experiment)

Audio cannot be sent directly to most LLMs. Convert to text FIRST during BUILD:

1. **Transcribe audio** using Whisper (Groq has Whisper API, or use openai.audio.transcriptions)
   ```python
   # Groq Whisper example
   from groq import Groq
   client = Groq()
   with open("audio.mp3", "rb") as f:
       transcript = client.audio.transcriptions.create(model="whisper-large-v3", file=f)
   text = transcript.text
   ```

2. **Save transcripts as test data**:
   ```yaml
   inputs:
     - id: "call_001"
       text: "Transcribed text from the audio file..."
       source_file: "data/audio/call_001.mp3"
       transcript_model: "whisper-large-v3"
   ```

3. Run the standard pipeline on the transcripts. The experiment tests prompt quality on text, not transcription quality.

If the experiment IS about transcription quality (comparing Whisper models), that's a different type of experiment — write a custom execution script that calls audio APIs.

### Video → Text (prepare before experiment)

Video inputs need two-step preparation during BUILD:

1. **Extract frames** at key intervals (e.g., 1 frame/second or scene changes)
2. **Transcribe audio track** using Whisper (see Audio section above)
3. **Combine** into test data:
   ```yaml
   inputs:
     - id: "video_001"
       text: "Audio transcript: {transcript text}"
       images:
         - "data/frames/video_001_frame_001.png"
         - "data/frames/video_001_frame_030.png"
       source_file: "data/video/clip_001.mp4"
   ```

4. Use vision-capable models for the experiment. The text transcript + key frames give the model enough context for most video analysis tasks.

For experiments that specifically test video understanding APIs (like Gemini's native video input), write a custom execution script.

### Image + Text (adapted pipeline)

Preparation during BUILD:
- Collect images into `experiments/{id}/data/images/`
- Reference by path or URL in test data
- Ensure test models support vision

```yaml
inputs:
  - id: "001"
    text: "What product is shown?"
    image: "data/images/product_001.png"         # single image
  - id: "002"
    text: "Compare these designs"
    images: ["data/images/a.png", "data/images/b.png"]  # multiple
```

Provider-specific image formats for the custom execution script:

**OpenAI / Groq / Together:**
```python
{"role": "user", "content": [
    {"type": "text", "text": user_text},
    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64_data}"}}
]}
```

**Anthropic:**
```python
{"role": "user", "content": [
    {"type": "text", "text": user_text},
    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}}
]}
```

**Google Gemini:**
```python
Part(text=user_text), Part(inline_data=Blob(mime_type=media_type, data=image_bytes))
```

Vision-capable models: GPT-4o, Claude Sonnet/Opus, Gemini Flash/Pro. Check during RESEARCH which discovered models support vision.

### Multi-Turn Conversations (adapted pipeline)

Preparation during BUILD — structure conversations as message arrays:

```yaml
inputs:
  - id: "conv_001"
    messages:
      - {role: "user", content: "Hi, I need help with my order"}
      - {role: "assistant", content: "Sure! What's your order number?"}
      - {role: "user", content: "It's #12345, the item arrived damaged"}
    expected_intent: "damage_report"
```

The custom execution script sends the full array. The system prompt from the template is prepended as the first message. All providers accept message arrays — no format conversion needed.

### Tool Calling (adapted pipeline)

Define tools in `experiments/{id}/tools.yaml`:
```yaml
tools:
  - name: "get_weather"
    description: "Get current weather for a city"
    parameters:
      type: "object"
      properties:
        city: {type: "string"}
      required: ["city"]
```

Test data:
```yaml
inputs:
  - id: "001"
    text: "What's the weather in Paris?"
    expected_tool: "get_weather"
    expected_args: {"city": "Paris"}
```

The custom execution script includes tools in the API call. Evaluate with `ground_truth` comparing expected_tool + expected_args.

### PDF / CSV / Documents (prepare before experiment)

**Preferred approach:** Extract content to text during BUILD, then use standard pipeline.

```python
# PDF extraction
import pdfplumber
with pdfplumber.open("invoice.pdf") as pdf:
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)

# CSV serialization
import csv
with open("data.csv") as f:
    rows = list(csv.DictReader(f))
    text = "\n".join(str(row) for row in rows)
```

Save extracted text in test_inputs.yaml. The experiment then tests prompts on the extracted content, not the file handling.

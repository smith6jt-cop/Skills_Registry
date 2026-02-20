---
name: shiny-llm-chat
description: "Patterns for integrating OpenAI-compatible LLM chat into Shiny apps. Covers UF Navigator, reasoning models, streaming, fallback logic, and credential management."
author: Jordan Smith
date: 2026-02-20
---

# Shiny LLM Chat Integration

## Experiment Overview

| Item | Details |
|------|---------|
| **Date** | 2026-02-20 |
| **Goal** | Integrate AI chat assistant into Islet Explorer Shiny app using UF Navigator AI Toolkit (OpenAI-compatible API) |
| **Environment** | R 4.x, Shiny, httr2, UF Navigator API (`api.ai.it.ufl.edu`) |
| **Status** | Production — verified working with streaming + reasoning model support |

## Context

The Islet Explorer Shiny app needed an embedded AI assistant to help users interpret plots, statistics, and data patterns. The backend is UF Navigator AI Toolkit, which provides OpenAI-compatible endpoints but with important differences: non-standard model names, model access control via API key permissions, and a reasoning model (120B) that uses chain-of-thought.

## Verified Workflow

### 1. Architecture (3-file modular pattern)

```
R/
  ai_helpers.R              # API layer: credentials, request building, streaming, fallback
  mod_ai_assistant_ui.R     # UI module: chat panel, model picker, send/reset buttons
  mod_ai_assistant_server.R # Server module: history management, streaming callback, token tracking
```

- **ai_helpers.R** is sourced at app startup (not inside a module) so credentials load once
- **Module pattern**: `ai_assistant_ui("ai_chat")` + `ai_assistant_server("ai_chat")` wired in app.R
- **No shared reactive state**: Chat is self-contained, doesn't depend on other modules

### 2. Credential Loading Priority

```r
renviron_paths <- c(
  ".Renviron",                    # App directory (deployment priority)
  file.path(script_dir, ".Renviron"),
  Sys.getenv("R_ENVIRON_USER"),
  "~/.Renviron",
  "~/.Renviron.local",
  file.path(Sys.getenv("HOME"), ".Renviron")
)
```

Load with `readRenviron(path)`. Required vars: `KEY` (API key), `BASE` (API base URL, optional — defaults to OpenAI).

### 3. Discovering Available Models

```bash
curl -s "https://api.ai.it.ufl.edu/v1/models" \
  -H "Authorization: Bearer $KEY" | python3 -m json.tool
```

**Always verify model IDs against the API** before hardcoding in UI dropdowns.

### 4. Streaming with Reasoning Model Support

The streaming parser must handle both standard models and reasoning models:

```r
# Standard model: delta.content appears immediately
# Reasoning model: delta.reasoning_content first, then delta.content

piece <- delta$content
if (!is.null(piece)) {
  # Actual answer content — accumulate and display
  accumulated <- paste0(accumulated, piece)
  stream_callback(accumulated, usage)
} else if (!is.null(delta$reasoning_content)) {
  # Reasoning phase — show thinking indicator
  stream_callback("Thinking...", usage)
}
```

### 5. Model Fallback Logic

```r
# When a model returns an error, check if we should try the next candidate
fallback_due_to_model <- status_code %in% c(400, 401, 404) &&
  grepl("model", error_detail, ignore.case = TRUE) &&
  !identical(current_model, fallback_model)
```

**Critical**: Include HTTP 401 in the status code check. UF Navigator returns 401 for model access denied (not 404 like OpenAI).

### 6. UF Navigator vs OpenAI API Differences

| Feature | OpenAI | UF Navigator |
|---------|--------|-------------|
| Endpoint | `/v1/responses` + `/v1/chat/completions` | `/v1/chat/completions` only |
| Model access denied | HTTP 404 | HTTP 401 |
| Model names | `gpt-4`, `gpt-3.5-turbo` | `gpt-oss-20b`, `gpt-oss-120b` |
| Reasoning model | o1/o3 series | `gpt-oss-120b` (chain-of-thought in `reasoning_content`) |
| Rate limit | HTTP 429 | HTTP 429 |

Detect UF Navigator: `grepl("api\\.ai\\.it\\.ufl\\.edu", base_url)` and skip `/responses`.

## Failed Attempts (CRITICAL)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Used model name `gpt-oss-210b` in UI dropdown | Model doesn't exist on UF Navigator — only `gpt-oss-20b` and `gpt-oss-120b` available | **Always query `/v1/models` endpoint to verify available model IDs before hardcoding in UI** |
| Fallback logic only checked HTTP 400/404 for model errors | UF Navigator returns HTTP **401** for "key not allowed to access model", so fallback never triggered | **Include 401 in model-fallback status codes** — different providers use different codes for access denied |
| Streaming parser only checked `delta.content` | Reasoning model (120b) sends `delta.reasoning_content` chunks first with `delta.content = null`. Users saw no streaming feedback for 5-30 seconds. | **Handle `reasoning_content` in streaming parser** — show "Thinking..." indicator during reasoning phase |
| Non-streaming with low `max_tokens` (e.g., 10) | Reasoning model consumes token budget on chain-of-thought, returns `content: null` | **Set generous `max_output_tokens`** (4096+) for reasoning models — reasoning budget comes from the same pool |
| Tried `/v1/responses` endpoint on UF Navigator | 404 — endpoint doesn't exist on UF Navigator proxy | **Detect provider from base URL** and use appropriate endpoint (chat/completions for UF Navigator) |
| Used `httr2::req_body_json()` for streaming requests | JSON encoding issues with certain payload structures | **Use `req_body_raw(charToRaw(jsonlite::toJSON(...)))` for streaming** to control JSON serialization exactly |

## Final Parameters

```r
# .Renviron (for UF Navigator)
KEY=your-api-key-here
BASE=https://api.ai.it.ufl.edu

# Model defaults (env vars, optional)
OPENAI_DEFAULT_MODEL=gpt-oss-120b   # fallback model
OPENAI_FAST_MODEL=gpt-oss-20b       # auto-selection for short queries
OPENAI_TOKEN_BUDGET=100000           # optional cumulative limit

# API call parameters
temperature = 0.3          # Low for factual/analytical answers
max_output_tokens = 4096   # Must be generous for reasoning models
timeout = 120              # seconds — reasoning model needs time
max_tries = 3              # Retry on 429 and 5xx
```

## Key Insights

1. **Provider detection matters**: Different OpenAI-compatible providers (UF Navigator, Azure, etc.) have different endpoints, status codes, and model naming. Abstract the provider-specific behavior.

2. **Reasoning models change the streaming contract**: Standard models stream `content` incrementally. Reasoning models stream `reasoning_content` first (invisible to user), then `content`. Your streaming UI must handle both patterns.

3. **Verify models at runtime, not hardcode time**: Model availability changes. The UI should ideally query `/v1/models` to populate the dropdown, or at minimum, the model names should be verified against the API before deployment.

4. **Shiny streaming is callback-based**: Use `httr2::req_stream()` with a chunk callback that parses SSE `data:` lines, extracts JSON, and calls `stream_callback()` to update reactive values. Call `session$flushReact()` to push updates to the browser during long operations.

5. **Credential loading order matters in deployment**: Shiny-server runs R workers in the app directory, not the user's home. Put `.Renviron` in the app directory for production, but also search `~/.Renviron` as fallback for development.

6. **Token budget prevents runaway costs**: Track cumulative `total_tokens` from API responses and block new requests when budget is reached. Display usage to users.

## References

- UF Navigator AI Toolkit: University of Florida research computing service
- httr2 R package: https://httr2.r-lib.org/
- OpenAI Chat Completions API: https://platform.openai.com/docs/api-reference/chat
- Shiny modules: https://shiny.posit.co/r/articles/improve/modules/

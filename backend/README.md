# Enterprise AI Security Gateway Backend

FastAPI backend for the Enterprise AI Security Gateway. The product UI is served by the independent React app in `../frontend`; this service should be treated as the API server only.

## Overview

This project demonstrates how to:

- persist multi-turn chat sessions in SQLite
- scan user prompts before model calls
- detect English and Chinese sensitive data
- detect prompt injection attempts
- detect source code upload attempts
- block banned topics such as weapons, self-harm, fraud, and HR discriminatory content
- block raw sensitive content from reaching the model
- let the user either edit the prompt or send a sanitized version
- browse and delete historical chat sessions
- record high-risk sensitive prompt logs at `/log` after confirmed sends
- record blocked source-code and prompt-injection attempts in `/log`
- monitor console statistics, scanner status, and the latest scan detail from the homepage
- monitor estimated per-user token usage and TokenLimit threshold pressure from the React admin app
- show a right-bottom alert when the same user triggers scanners repeatedly
- manage provider API keys from `/keys` and switch chat behavior by selected provider/model

## Architecture

Backend modules:

- `app/main.py`: FastAPI startup and static file serving
- `app/core/`: configuration, logging, and database bootstrap
- `app/models/`: SQLAlchemy session, message, log, and scan-event tables
- `app/schemas/`: request and response models
- `app/api/`: health, session, chat, console, and log endpoints
- `app/services/guardrails/`: LLM Guard integration, Chinese regex enhancement, masking, and normalization
- `app/services/llm/`: base LLM interface, OpenAI-compatible client, provider factory
- `app/services/session_service.py`: session CRUD
- `app/services/chat_service.py`: preview/confirm orchestration and persistence
- `app/services/log_service.py`: sensitive prompt log persistence
- `app/services/scan_event_service.py`: preview/confirm scan event persistence for the console
- `app/services/console_service.py`: summary cards, scanner state, latest scan aggregation, and token usage monitoring
- `app/services/provider_credential_service.py`: provider credentials, model lists, and key management

Frontend:

- React/Vite app: `../frontend`
- Local UI URL: `http://127.0.0.1:5173`
- Login route: `/login`
- User route: `/app/chat`
- Admin route: `/admin`
- Admin token usage route: `/admin/token-usage`

## Provider Key Management

Open the key management page in the React admin app:

- `http://127.0.0.1:5173/admin/api-keys`

You can:

- save or overwrite a provider API key
- configure provider base URL
- configure the provider default model
- configure the model list shown on the console homepage
- delete a saved provider key

The homepage provider/model dropdowns use this saved configuration. When you switch a chat session to `OpenAI` or `Qwen`, the backend resolves the matching saved key and base URL automatically.

## Guardrail Flow

1. The frontend sends a prompt to `POST /api/chat/preview`.
2. The backend scans the prompt with:
   - `Privacy Filter`
   - `LLM Guard PromptInjection`
   - `LLM Guard BanCode`
   - `LLM Guard BanTopics`
   - `Business Sensitive` via local Ollama `qwen3.5:4b`
   - a Chinese/English custom regex enhancement layer
3. If the prompt looks like source code, prompt injection, a banned topic, or commercial sensitive content, preview returns `blocked` and the LLM is never called.
4. If no sensitive data is found, the frontend immediately calls `POST /api/chat/confirm`.
5. If sensitive data is found, the backend returns the original text, sanitized text, and normalized detected entities.
6. The frontend opens a modal showing masked values by default and raw values only in hover tooltips.
7. The user can only go back and edit or send the sanitized version.
8. `POST /api/chat/confirm` revalidates the original message and rejects raw sensitive bypass attempts.
9. If sensitive data was detected and the user still sends the sanitized version, the backend writes a high-risk log entry containing the original raw prompt text.
10. If a source-code upload attempt or prompt-injection attempt is blocked during preview, the backend also records it in `/log`.
11. If the assistant reply contains `[REDACTED_...]` placeholders, the backend deanonymizes the displayed reply back to the original values for the user-facing response.
12. The homepage updates its summary cards, scanner strip, latest scan detail, and repeated-trigger alert from persisted scan events.

## Active Scanners

The homepage scanner strip currently exposes these modules:

- `BanCode`
- `PromptInjection`
- `BanTopics`
- `Privacy Filter`
- `Business Sensitive`
- `Custom Regex`
- `Deanonymize`
- `Sensitive Logging`

The UI shows only scanner names and active state by default. Hover the scanner cards to see the module descriptions.

## Console APIs

- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/last-scan`
- `GET /api/console/token-usage`

The homepage uses these endpoints to render:

- total scans
- passed scans
- blocked or rejected scans
- PII redaction count
- scanner availability
- original input, sanitized input, raw assistant output, and deanonymized display output
- repeated-trigger alert state for the currently selected username

`GET /api/console/summary` also accepts an optional `username` query parameter. The homepage uses it to calculate whether the current user has triggered scanners repeatedly.

## Token Usage Monitoring

Open the token usage page in the React admin app:

- `http://127.0.0.1:5173/admin/token-usage`

The backend endpoint `GET /api/console/token-usage` estimates token usage from persisted `scan_events`, falling back to sanitized input when raw text is not stored. It uses `tiktoken` in the same local-tokenizer style as llm-guard's TokenLimit scanner:

- select the tokenizer with `encoding_for_model(model)`, falling back to `cl100k_base`
- encode input and assistant output text locally
- compare each prompt with the current 4096-token threshold
- aggregate total, input, output, max prompt, limit hits, provider/model, and 14-day trend by username

These numbers are intended for operational monitoring and guardrail pressure analysis. They are not guaranteed to match provider billing exactly; exact accounting should prefer provider response `usage` fields or official count-token APIs.

## Repeated Trigger Alert

If the same username triggers any scanner 5 or more times in a row, the homepage shows a right-bottom alert toast.

Current behavior:

- the threshold is based on consecutive triggered scans
- once the threshold is reached, the toast keeps updating on later triggers
- the toast shows the user’s total trigger count
- dismissing the toast only hides the current state; a later trigger count will show it again

This is driven by persisted `scan_events`, not only by in-memory frontend state.

## High-Risk Logs

Open the log page in the React admin app:

- `http://127.0.0.1:5173/admin/logs`

This implementation intentionally records raw sensitive prompt content when:

- the prompt contains sensitive data
- the user confirms sending it
- the prompt is blocked as a source-code upload attempt
- the prompt is blocked as a prompt-injection attempt

Each log entry stores:

- `username`
- `original_sensitive_content`
- `detected_entity_types`
- `created_at`
- `session_id`
- `message_id`

This behavior is high risk because it stores plaintext sensitive data in SQLite and displays it in the browser.

Examples of log entity types you may see:

- `EMAIL_ADDRESS`
- `CN_ID_CARD`
- `SOURCE_CODE_ATTEMPT`
- `PROMPT_INJECTION_ATTEMPT`

## Environment Variables

Copy `.env.example` to `.env` and fill in your values.

- `DEFAULT_PROVIDER=openai`
- `DEFAULT_MODEL=gpt-4.1-mini`
- `APP_HOST=127.0.0.1`
- `APP_PORT=8002`
- `OPENAI_API_KEY=`
- `OPENAI_BASE_URL=https://api.openai.com/v1`
- `DATABASE_URL=sqlite:///./ai_guard_demo.db`
- `LOCAL_MODEL_CACHE_DIR=./.model-cache`
- `PRIVACY_FILTER_ENABLED=true`
- `PRIVACY_FILTER_MODEL_PATH=./.model-cache/openai-privacy-filter`
- `PRIVACY_FILTER_AUTO_DOWNLOAD=false`
- `PRIVACY_FILTER_DEVICE=auto`
- `BUSINESS_SENSITIVE_ENABLED=true`
- `BUSINESS_SENSITIVE_MODEL=qwen3.5:4b`
- `BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434`
- `BUSINESS_SENSITIVE_TIMEOUT_SECONDS=20`

`OPENAI_API_KEY` can be left empty if you plan to manage provider keys only through `/keys`.

Note:

- the app resolves `.env` from `backend/.env`
- the app resolves SQLite to `backend/ai_guard_demo.db`
- provider-specific keys can also be managed from `/keys` instead of environment variables
- LLM Guard and Hugging Face model caches are redirected into `backend/.model-cache` by default

## Local Model Cache

This project is now configured to keep downloaded scanner models inside the project directory instead of the global user cache.

Default location:

- `backend/.model-cache/`

What this means:

- the first run can still download required models
- later restarts reuse the same local files
- models are not re-downloaded on every restart unless you delete the cache or change model revisions

The app currently redirects these caches into the project-local model directory:

- `HF_HOME`
- `HUGGINGFACE_HUB_CACHE`
- `TRANSFORMERS_CACHE`
- `TORCH_HOME`

If you want a different persistent location, set:

```env
LOCAL_MODEL_CACHE_DIR=./.model-cache
```

or point it to another absolute path.

## Install

Python 3.11 is required.

```bash
uv sync --group dev --link-mode=copy
```

This installs the main runtime stack, including:

- FastAPI
- SQLAlchemy
- OpenAI SDK
- LLM Guard
- Accelerate for Hugging Face device placement used by Qwen3Guard
- spaCy English and Chinese models
- ONNX runtime support for LLM Guard scanners that can use it

## Run The API

From the `backend/` directory:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

The backend root returns API metadata only:

- `http://127.0.0.1:8002/`

Health check:

- `http://127.0.0.1:8002/api/health`

Run the frontend from `../frontend`:

```bash
npm install
npm run dev
```

Open:

- `http://127.0.0.1:5173/login`

## Run Tests

From the `backend/` directory:

```bash
uv run pytest
```

The tests use a temporary SQLite database and a mocked LLM client.

To run the real local Ollama integration test, first make sure Ollama is serving `qwen3.5:4b`, then run:

```bash
$env:RUN_OLLAMA_INTEGRATION="1"
uv run pytest tests/test_business_sensitive_integration.py -q
```

For a quick manual validation against your local Ollama service:

```bash
uv run python scripts/validate_business_sensitive_ollama.py
```

## uv Workflow

Recommended commands:

```bash
uv sync --group dev --link-mode=copy
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
uv run pytest
```

On Windows Desktop or OneDrive-managed folders, `--link-mode=copy` avoids hardlink issues during dependency installation.

If `uv` cache permissions are unstable on your machine, you can set a project-local cache directory first:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
```

Then run:

```powershell
uv sync --group dev --link-mode=copy
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002
```

## Known Limitations

- OpenAI and Qwen are wired through the same OpenAI-compatible client path in this version, but broader provider coverage still needs more provider-specific handling.
- Chinese detection depends heavily on the custom enhancement layer and may need tuning for production traffic.
- `LLM Guard` may still miss some Chinese entities that are reliably caught by the custom regex layer.
- Some LLM Guard scanners can fall back to heuristic matching when model initialization is unavailable or unstable on the local machine.
- `BanCode` and `PromptInjection` may behave differently depending on local model availability and ONNX support.
- There is no authentication.
- There is no streaming in v1.
- `/log` stores and displays raw sensitive prompt content in plaintext by design for this requested high-risk mode.

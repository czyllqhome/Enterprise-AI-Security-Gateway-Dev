# Enterprise AI Security Gateway Backend

FastAPI backend for the Enterprise AI Security Gateway. The product UI is served by the independent React app in `../frontend`; this service is the API server.

## Overview

The backend provides:

- JWT authentication, admin authorization, and user management
- multi-turn chat sessions persisted in PostgreSQL
- prompt scanning, sensitive-data masking, prompt-injection detection, and topic restrictions
- OpenAI-compatible provider configuration for OpenAI, Qwen, OpenRouter, and Ollama
- audit logs, scanner governance, management dashboards, and token usage estimates
- Office, PDF, and image upload with extraction, OCR, and asynchronous content review
- reviewed attachments can be attached to chat prompts by `attachment_file_id`, with extracted text appended server-side
- authenticated chat, session, provider, attachment, and administration APIs

## Requirements

- Python `3.11`
- uv
- PostgreSQL 18
- Ollama with `qwen3.5:4b` for default business-sensitive and file review; Business Sensitive can also be switched to Aliyun Bailian `deepseek-v4-flash`

## PostgreSQL Setup

Connect as the PostgreSQL administrator:

```powershell
psql -U postgres -h 127.0.0.1 -p 5432
```

Create the application user and database:

```sql
CREATE USER ai_guard_user WITH PASSWORD 'change-me-strong-password';
CREATE DATABASE ai_guard OWNER ai_guard_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE ai_guard TO ai_guard_user;
\c ai_guard
GRANT USAGE, CREATE ON SCHEMA public TO ai_guard_user;
```

Verify the application user:

```powershell
psql -U ai_guard_user -h 127.0.0.1 -p 5432 -d ai_guard
```

## Environment

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Set these values in `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://ai_guard_user:change-me-strong-password@127.0.0.1:5432/ai_guard
JWT_SECRET_KEY=replace-with-a-long-random-secret
API_KEY_ENCRYPTION_SECRET=replace-with-another-long-random-secret
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
CORS_ORIGINS=http://127.0.0.1:5173
FILE_REVIEW_ACTIVE_STORAGE_PROFILE=windows
FILE_REVIEW_WINDOWS_STORAGE_PATH=./uploaded-documents
FILE_REVIEW_LINUX_STORAGE_PATH=/var/lib/ai-security-gateway/uploaded-documents
FILE_REVIEW_PER_USER_STORAGE_DIRS=true
```

The default admin is created only when `DEFAULT_ADMIN_PASSWORD` is non-empty and the configured username does not already exist.

## Database Migrations

Install dependencies and apply migrations from `backend/`:

```powershell
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
```

The migration creates these business tables:

- `users`
- `chat_sessions`
- `chat_messages`
- `chat_logs`
- `scan_events`
- `provider_credentials`
- `system_settings`
- `uploaded_files`

Alembic also creates `alembic_version`.

## Run

From `backend/`:

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

API metadata, docs, and health check:

- `http://127.0.0.1:8002/`
- `http://127.0.0.1:8002/docs`
- `http://127.0.0.1:8002/api/health`

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/health
```

## Key Routes

- `POST /api/auth/login`
- `GET /api/sessions`
- `POST /api/chat/preview` accepts `attachment_file_id` to include a reviewed upload in the scanned prompt
- `POST /api/chat/confirm` accepts the same `attachment_file_id` to rebuild the approved attachment context before model dispatch
- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/token-usage`
- `POST /api/file-review/files/upload`
- `GET /api/file-review/settings`
- `PUT /api/file-review/settings`
- `GET /api/logs`
- `GET /api/providers`

## Attachment Storage

File-review settings are stored in `system_settings` and can be managed from the React admin page at `/admin/configuration`.

- `FILE_REVIEW_ACTIVE_STORAGE_PROFILE` chooses `windows` or `linux`.
- `FILE_REVIEW_WINDOWS_STORAGE_PATH` stores the Windows landing path.
- `FILE_REVIEW_LINUX_STORAGE_PATH` stores the Linux/cloud landing path.
- `FILE_REVIEW_PER_USER_STORAGE_DIRS=true` writes files beneath a sanitized username subdirectory.

Only the active runtime profile path is created on the current host. The inactive platform path is stored as text so a Windows admin can prepare Linux deployment paths without rewriting them.

## Chat Attachments

The upload flow is intentionally split from model dispatch:

1. `POST /api/file-review/files/upload` persists the file and starts asynchronous extraction/review.
2. The frontend polls `GET /api/file-review/files/{file_id}` until `status` is `completed`.
3. `POST /api/chat/preview` receives the user message plus `attachment_file_id`.
4. `ChatService` checks ownership/admin access, blocks incomplete or high-risk files, appends extracted text, and scans the combined prompt.
5. `POST /api/chat/confirm` repeats the server-side attachment lookup before sending the approved prompt to the model.

## Local Model Cache

Default model cache location:

```text
backend/.model-cache/
```

The app redirects these caches into the project-local model directory by default:

- `HF_HOME`
- `HUGGINGFACE_HUB_CACHE`
- `TRANSFORMERS_CACHE`
- `TORCH_HOME`

## Tests

From `backend/`:

```powershell
uv run pytest
```

The repository includes `tests/test_file_review_permissions.py`, covering file-review authorization, username-based storage, and chat attachment context behavior.

## Security Notes

- `backend/.env` contains secrets and database credentials. Do not commit it.
- High-risk logs can store and display raw sensitive prompt content in plaintext.
- Production deployments need a retention, encryption, backup, and access-control policy for PostgreSQL data.

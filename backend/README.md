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
- `POST /api/chat/preview`
- `POST /api/chat/confirm`
- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/token-usage`
- `POST /api/file-review/files/upload`
- `GET /api/logs`
- `GET /api/providers`

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

The pytest configuration is present in `pyproject.toml`, but the current repository does not contain committed automated test files.

## Security Notes

- `backend/.env` contains secrets and database credentials. Do not commit it.
- High-risk logs can store and display raw sensitive prompt content in plaintext.
- Production deployments need a retention, encryption, backup, and access-control policy for PostgreSQL data.

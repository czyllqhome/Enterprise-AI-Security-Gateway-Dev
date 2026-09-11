# Enterprise AI Security Gateway Backend

FastAPI backend for the Enterprise AI Security Gateway. The product UI is served by the independent React app in `../frontend`; this service is the API server.

## Overview

The backend provides:

- JWT authentication, admin authorization, and user management
- multi-turn chat sessions persisted in PostgreSQL
- prompt scanning, sensitive-data masking, prompt-injection detection, and topic restrictions
- OpenAI-compatible provider configuration for OpenAI, Qwen, OpenRouter, and Ollama
- complete prompt audit logs with allow/review/block filtering, scanner governance, management dashboards, and token usage estimates
- Office, PDF, and image upload with immutable identity, multimodal business review, optimized extraction/OCR, and asynchronous original-file review
- reviewed attachments can be referenced by `attachment_file_id`; extracted/OCR/review text stays inside the guardrail path while the downstream model receives the user prompt and approved original bytes
- authenticated chat, session, provider, attachment, and administration APIs

## Requirements

- Python `3.11`
- uv
- PostgreSQL 18
- Business Sensitive can use Ollama, Aliyun Bailian, AWS Bedrock, or OpenRouter `qwen/qwen3.8-flash`; configure the OpenRouter key from the admin API Key page

## PostgreSQL Setup

PostgreSQL is the only supported runtime database. Application `DATABASE_URL` values must use the `postgresql+psycopg://` driver; SQLite, SQL Server, MySQL, and other database engines are not supported for development or production runtime. A small number of isolated unit tests use in-memory SQLite and do not exercise the application database configuration.

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
FILE_REVIEW_VISION_MODEL=qwen3.5:4b
QWEN3GUARD_ENABLED=true
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-4B
QWEN3GUARD_MODEL_PATH=
LOCAL_MODEL_DEVICE=auto
QWEN3GUARD_DEVICE=inherit
PRIVACY_FILTER_DEVICE=inherit
FILE_OCR_DEVICE=inherit
```

The default admin is created only when `DEFAULT_ADMIN_PASSWORD` is non-empty and the configured username does not already exist.

## Database Migrations

Install dependencies and apply migrations from `backend/`:

```powershell
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
uv run python scripts/prepare_scanner_assets.py
```

The asset preparation step downloads and validates the local token-counting encoder during deployment/build preparation. Privacy Filter uses its separately configured checkpoint and auto-download policy.

The default Qwen3Guard model uses three BF16 weight shards totaling about 8.82 GB. Pre-download or resume them before starting the API:

```powershell
uv run python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3Guard-Gen-4B', local_dir='.model-cache/qwen3guard/Qwen3Guard-Gen-4B')"
```

Verify that all three `model-0000x-of-00003.safetensors` files exist. `LOCAL_MODEL_DEVICE` accepts `auto`, `cpu`, or `cuda`; Qwen3Guard, Privacy Filter, and file OCR inherit it unless their component setting overrides it. In `auto` mode Qwen3Guard selects CUDA when available, while Privacy Filter and PaddleOCR remain on CPU for compatibility. Explicit `cuda` fails closed when the required CUDA runtime is unavailable. This project currently installs the PyTorch CUDA 13.0 build, which requires an NVIDIA `580+` driver on Windows.

For a CPU-only host such as an EC2 C7i instance, use the smaller Qwen3Guard model and force every local scanner onto CPU:

```env
LOCAL_MODEL_DEVICE=cpu
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-0.6B
QWEN3GUARD_MODEL_PATH=./.model-cache/qwen3guard/Qwen3Guard-Gen-0.6B
QWEN3GUARD_DEVICE=inherit
PRIVACY_FILTER_DEVICE=inherit
FILE_OCR_DEVICE=inherit
QWEN3GUARD_WORKERS=1
```

Verify warm scanner latency and the Qwen3Guard runtime device before deployment:

```powershell
uv run python scripts/benchmark_scanners.py --samples 5
```

The benchmark reports the actual Qwen3Guard device and warm p50/p95 latency. Production readiness requires the scanner proof secret to contain at least 32 random bytes.

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

For a multi-instance/AWS deployment, keep file review out of the web process and run it as a separate ECS service or process:

```env
APP_ENV=production
FILE_REVIEW_WORKER_MODE=external
FILE_REVIEW_ACTIVE_STORAGE_PROFILE=linux
FILE_REVIEW_LINUX_STORAGE_PATH=/mnt/ai-gateway-files
```

```powershell
uv run python -m app.workers.file_review_worker
```

The worker claims PostgreSQL jobs with a lease and `SKIP LOCKED`, retries transient failures, and recovers expired jobs after a process restart. Every API and worker replica must see the same files; on AWS, mount the same encrypted EFS access point at `FILE_REVIEW_LINUX_STORAGE_PATH` (or replace the storage adapter with S3 before using ephemeral ECS storage). `FILE_REVIEW_WORKER_MODE=embedded` is intended for one-process local development only.

`POST /api/chat/confirm/stream` emits NDJSON model deltas. When it is exposed through ALB or a reverse proxy, disable response buffering and choose an idle timeout longer than the provider timeout.

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
- `POST /api/chat/preview` validates `attachment_file_id`, scans only the user prompt, and returns both a signed `scan_proof` and server-side `snapshot_id`
- `POST /api/chat/confirm` validates the same snapshot, proof, policy, permission, and original hash before model dispatch
- `POST /api/chat/confirm/stream` validates the same one-use scan proof and streams model deltas as NDJSON
- `GET /api/console/performance` reports scan p50/p95/p99 and per-scanner latency/errors
- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/token-usage`
- `POST /api/file-review/files/upload`
- `GET /api/file-review/files/{id}/status`
- `POST /api/file-review/files/{id}/retry`
- `DELETE /api/file-review/files/{id}`
- `GET /api/file-review/settings`
- `PUT /api/file-review/settings`
- `GET /api/logs` with optional `decision=allowed|review|blocked`
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

1. `POST /api/file-review/files/upload` stores the original bytes, verifies MIME, records SHA-256/owner identity, and enqueues durable review work in PostgreSQL.
2. With OpenRouter `qwen/qwen3.8-flash`, image and PDF bytes are sent to OpenRouter for one multimodal Business Sensitive decision before local privacy checks. DOCX/XLSX/PPTX use fast native text extraction; legacy `.doc` is rejected.
3. High-risk business content is blocked. Medium-risk content requires explicit send confirmation and skips the remaining file scanners. Clean business results continue through local OCR/text privacy and safety checks. Missing coverage, timeout, unavailable scanners, invalid model responses, or changed bytes fail closed.
4. The frontend polls `GET /api/file-review/files/{file_id}/status`. Extracted text is hidden by default and may appear only in the collapsible audit detail.
5. `POST /api/chat/preview` scans the user prompt without appending file-derived text, validates the target model/MIME capability, and creates a signed proof plus a server-side send snapshot.
6. `POST /api/chat/confirm` rechecks the snapshot, one-use proof, authorization, policy, and original SHA-256. The provider adapter receives the user prompt and original file as separate inputs.
7. There is no fallback that substitutes OCR or extracted text when the selected provider/model cannot accept the original format.

Set `ATTACHMENT_CAPABILITIES` only for endpoint/model/MIME combinations verified against the real downstream provider. `FILE_REVIEW_VISION_*`, `OFFICE_CONVERTER_*`, and the separate `FILE_REVIEW_PROVIDER`/`FILE_REVIEW_MODEL` settings are retained only for configuration compatibility and are not used by the optimized review path. See [`ORIGINAL_ATTACHMENTS.md`](ORIGINAL_ATTACHMENTS.md) for the complete operational contract.

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

The repository includes complete prompt-log decisions, original-byte transport, review completeness, visual/Office coverage, snapshot tampering, authorization, retry/lease, checkpoint, migration, and chat scan-proof regression tests. Some isolated unit tests use in-memory SQLite for speed; deployed application services use PostgreSQL only.

## Security Notes

- `backend/.env` contains secrets and database credentials. Do not commit it.
- `chat_logs` records every prompt decision and stores scanner-sanitized content; clean prompts are unchanged. Other business tables can still retain original confirmed input, so production deployments need an explicit data-retention policy.
- Production deployments need a retention, encryption, backup, and access-control policy for PostgreSQL data.

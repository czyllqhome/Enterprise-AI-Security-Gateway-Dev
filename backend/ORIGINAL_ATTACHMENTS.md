# Original attachment review and forwarding

The gateway scans internal extraction/visual representations for security and privacy, then sends approved original bytes alongside the user's text. Review output is never appended to the business prompt.

## Services

File review now requires an independent worker. Upload creates a durable database job in the same transaction as the file identity. FastAPI BackgroundTasks no longer executes file reviews.

On a database managed by the existing Alembic revision chain, apply migrations before starting the services:

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002
```

In a separate terminal, from backend:

```powershell
uv run python -m app.workers.document_worker
```

For an existing database created only by `create_all`, verify its schema and migration history before baselining Alembic; do not blindly stamp a revision or run the initial create-table migration over existing tables.

Each worker processes one file at a time. PostgreSQL row locking permits multiple independent workers; model hardware capacity should determine worker count. Workers renew a 90-second lease every 15 seconds. Expired jobs can be recovered, and stale workers cannot publish approval. Failures retry with backoff up to three attempts. Successful visual, business, and privacy review units are persisted as policy/hash-bound checkpoints, so bounded retries do not repeat completed model calls. Production PostgreSQL concurrency/load testing remains required before rollout.

## Configuration

- `FILE_REVIEW_VISION_MODEL`: explicitly configured local vision-capable guardrail model. Empty means visual review is unavailable.
- `FILE_REVIEW_VISION_BASE_URL`: loopback Ollama endpoint; no external host, proxy or redirect is permitted for this pre-review path.
- `OFFICE_CONVERTER_PATH`: explicit LibreOffice/soffice executable used to render Office review copies. DOC requires it; DOCX/XLSX/PPTX stay unknown if required rendered coverage is unavailable.
- `ATTACHMENT_CAPABILITIES`: JSON mapping provider -> exact model ID -> MIME list, enabled only after testing that endpoint with original files. Defaults to `{}`.

The OpenAI Responses adapter handles original-file inputs. Other adapters currently reject original attachments rather than drop or convert them. Setting a capability is an operator declaration, not automatic proof that a model understands every file feature. Real model sample validation is still required.

## UI and API

- Upload: existing `/api/file-review/files/upload`.
- Progress without document content: `GET /api/file-review/files/{id}/status`.
- Authorized retry: `POST /api/file-review/files/{id}/retry`.
- Authorized revocation and local byte cleanup: `DELETE /api/file-review/files/{id}`. Access is revoked before cleanup is attempted.
- Chat preview returns `snapshot_id`; confirm must submit it with the same prompt and attachment reference. Duplicate confirmation does not issue another model call.
- New chat messages show the user's text and original-file card; extraction appears only in collapsible review details.

Unverified legacy files, incomplete coverage, unavailable required scanners, any confirmed business-sensitive content, private information requiring redaction, and changed file hashes cannot be forwarded. The gateway does not modify an original to bypass this decision.

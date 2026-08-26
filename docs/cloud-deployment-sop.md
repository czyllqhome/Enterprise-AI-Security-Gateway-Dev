# Cloud Deployment SOP

This SOP deploys the Enterprise AI Security Gateway to three cloud servers:

- Frontend and Nginx: `10.0.0.7`
- Backend FastAPI: `10.0.0.9`
- PostgreSQL: `10.0.0.11`

The recommended production topology is:

```text
Browser
  -> http://10.0.0.7
    -> Nginx serves frontend/dist
    -> Nginx proxies /api, /docs, /openapi.json to http://10.0.0.9:8002
      -> FastAPI connects to PostgreSQL at 10.0.0.11:5432
```

## 0. AWS Network and Security Groups

Create three dedicated AWS security groups. Use security group references as the source/destination whenever the servers are in the same VPC; this is safer and easier to maintain than hard-coding private IPs. The private IPs below are included for clarity:

- Frontend and Nginx EC2: `10.0.0.7`
- Backend FastAPI EC2: `10.0.0.9`
- PostgreSQL EC2 or RDS: `10.0.0.11`

Security groups are stateful. You do not need to add inbound ephemeral-port rules for response traffic when the matching outbound request is allowed.

### 0.1 Recommended Security Group Names

Use names like:

```text
sg-ai-gateway-frontend
sg-ai-gateway-backend
sg-ai-gateway-db
```

If PostgreSQL is deployed as RDS, attach `sg-ai-gateway-db` to the RDS instance. If PostgreSQL is deployed on EC2, attach it to the PostgreSQL EC2 instance.

### 0.2 Frontend/Nginx Security Group: `sg-ai-gateway-frontend`

Attach this security group to the frontend server `10.0.0.7`.

Inbound rules:

| Type | Protocol | Port | Source | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| HTTP | TCP | `80` | Client CIDR, for example `0.0.0.0/0` for public access or your corporate CIDR | Yes, unless HTTPS-only | Browser access to Nginx |
| HTTPS | TCP | `443` | Client CIDR, for example `0.0.0.0/0` for public access or your corporate CIDR | Recommended | Browser access to Nginx over TLS |
| SSH | TCP | `22` | Bastion/security admin CIDR only | Optional | Linux server administration |
| RDP | TCP | `3389` | Bastion/security admin CIDR only | Optional, Windows only | Windows server administration |

Outbound rules:

| Type | Protocol | Port | Destination | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| Custom TCP | TCP | `8002` | `sg-ai-gateway-backend` or `10.0.0.9/32` | Yes | Nginx proxy to FastAPI |
| HTTPS | TCP | `443` | `0.0.0.0/0`, NAT gateway, or specific package/certificate endpoints | Optional | OS updates, `npm install`, Certbot/ACME, external monitoring |
| HTTP | TCP | `80` | `0.0.0.0/0`, NAT gateway, or specific package/certificate endpoints | Optional | Package mirrors or HTTP-01 certificate validation |

For a locked-down production environment, the only application-required outbound rule from the frontend server is `TCP 8002` to the backend security group.

### 0.3 Backend/FastAPI Security Group: `sg-ai-gateway-backend`

Attach this security group to the backend server `10.0.0.9`.

Inbound rules:

| Type | Protocol | Port | Source | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| Custom TCP | TCP | `8002` | `sg-ai-gateway-frontend` or `10.0.0.7/32` | Yes | Nginx reverse proxy to FastAPI |
| SSH | TCP | `22` | Bastion/security admin CIDR only | Optional | Linux server administration |
| RDP | TCP | `3389` | Bastion/security admin CIDR only | Optional, Windows only | Windows server administration |

Do not allow `0.0.0.0/0` inbound to port `8002`. Public users should reach the backend only through Nginx on `10.0.0.7`.

Outbound rules:

| Type | Protocol | Port | Destination | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | TCP | `5432` | `sg-ai-gateway-db` or `10.0.0.11/32` | Yes | SQLAlchemy/PostgreSQL connection |
| HTTPS | TCP | `443` | AWS service endpoints, VPC endpoints, NAT gateway, or `0.0.0.0/0` | Required for Bedrock/OpenAI/Qwen/OpenRouter | AWS Bedrock Runtime, STS/IMDS support paths, external model providers, dependency downloads |
| HTTP | TCP | `80` | NAT gateway or package endpoints | Optional | Package mirrors and OS updates |
| Custom TCP | TCP | `11434` | Ollama server SG/IP | Optional | Only needed if Ollama runs on a separate server |

If Ollama runs on the backend server itself, keep `BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434` and `FILE_REVIEW_OLLAMA_URL=http://127.0.0.1:11434`; no security group rule is needed for local loopback traffic.

If AWS Bedrock is used and the backend subnet has no NAT gateway, create VPC interface endpoints for the AWS services you use and target those endpoints in the route/security design. At minimum, the backend must be able to reach Bedrock Runtime in `BEDROCK_REGION`.

### 0.4 PostgreSQL Security Group: `sg-ai-gateway-db`

Attach this security group to PostgreSQL server `10.0.0.11` or to the RDS instance.

Inbound rules:

| Type | Protocol | Port | Source | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | TCP | `5432` | `sg-ai-gateway-backend` or `10.0.0.9/32` | Yes | Backend database connection |
| SSH | TCP | `22` | Bastion/security admin CIDR only | Optional, EC2 only | PostgreSQL EC2 administration |

Do not allow `0.0.0.0/0` inbound to port `5432`. The database should never be directly reachable from client browsers or the frontend server.

Outbound rules:

| Type | Protocol | Port | Destination | Required | Purpose |
| --- | --- | --- | --- | --- | --- |
| HTTPS | TCP | `443` | NAT gateway, package repositories, or AWS service endpoints | Optional, EC2 only | OS updates, backups, monitoring agents |
| PostgreSQL response traffic | TCP | Ephemeral | Backend client connection | No explicit rule needed | Security groups are stateful |

For RDS, the default outbound rule is usually not relevant to the application path. The critical rule is inbound `5432` from `sg-ai-gateway-backend`.

### 0.5 Minimum Application Path Summary

The minimum required application traffic is:

```text
Client CIDR -> 10.0.0.7:80/443
10.0.0.7 -> 10.0.0.9:8002
10.0.0.9 -> 10.0.0.11:5432
10.0.0.9 -> AWS Bedrock / external model provider endpoints on 443, if those providers are enabled
```

Recommended public exposure:

- Public: only `10.0.0.7:80/443`
- Private: `10.0.0.9:8002`, reachable only from `sg-ai-gateway-frontend`
- Private: `10.0.0.11:5432`, reachable only from `sg-ai-gateway-backend`

## 1. PostgreSQL Server: 10.0.0.11

### 1.1 Install PostgreSQL

Install PostgreSQL on `10.0.0.11`. PostgreSQL 16+ is fine; the local development notes mention PostgreSQL 18, but the app uses standard SQLAlchemy/PostgreSQL features.

### 1.2 Create Database and User

Run as the PostgreSQL admin user:

```sql
CREATE USER ai_guard_user WITH PASSWORD 'replace-with-a-strong-db-password';
CREATE DATABASE ai_guard OWNER ai_guard_user;
GRANT ALL PRIVILEGES ON DATABASE ai_guard TO ai_guard_user;
```

### 1.3 Allow Remote Connections From Backend Server

Edit PostgreSQL `postgresql.conf`.

Common Linux paths:

```text
/etc/postgresql/<version>/main/postgresql.conf
/var/lib/pgsql/<version>/data/postgresql.conf
```

Set:

```conf
listen_addresses = '10.0.0.11'
port = 5432
```

Edit PostgreSQL `pg_hba.conf`.

Common Linux paths:

```text
/etc/postgresql/<version>/main/pg_hba.conf
/var/lib/pgsql/<version>/data/pg_hba.conf
```

Add:

```conf
host    ai_guard    ai_guard_user    10.0.0.9/32    scram-sha-256
```

Restart PostgreSQL:

```bash
sudo systemctl restart postgresql
```

Validate from `10.0.0.9`:

```bash
psql "postgresql://ai_guard_user:replace-with-a-strong-db-password@10.0.0.11:5432/ai_guard" -c "select 1;"
```

## 2. Backend Server: 10.0.0.9

### 2.1 Prepare Runtime

Install:

- Python `>=3.11,<3.12`
- `uv`
- Git
- System libraries needed by OCR/PDF/Office parsing if file review is enabled
- Ollama, if business-sensitive scanning or file review uses local Ollama

Clone or copy the project to a stable path, for example:

```text
/opt/enterprise-ai-security-gateway
```

Install backend dependencies:

```bash
cd /opt/enterprise-ai-security-gateway/backend
uv sync --group dev --link-mode=copy
```

### 2.2 Configure Backend Environment

Create the backend environment file from the example:

```bash
cd /opt/enterprise-ai-security-gateway/backend
cp .env.example .env
```

Edit this file:

```text
backend/.env
```

Required production values for this three-server layout:

```env
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8002

CORS_ORIGINS=http://10.0.0.7

DATABASE_URL=postgresql+psycopg://ai_guard_user:replace-with-a-strong-db-password@10.0.0.11:5432/ai_guard

JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_EXPIRES_MINUTES=480

DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-initial-admin-password
DEFAULT_ADMIN_DISPLAY_NAME=Administrator

API_KEY_ENCRYPTION_SECRET=replace-with-a-long-random-secret

DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4.1-mini
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1

BEDROCK_REGION=us-east-1
BEDROCK_DEFAULT_MODEL=anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_PROFILE_NAME=
BEDROCK_TIMEOUT_SECONDS=60

LOCAL_MODEL_CACHE_DIR=./.model-cache

PRIVACY_FILTER_ENABLED=true
PRIVACY_FILTER_MODEL_PATH=./.model-cache/openai-privacy-filter
PRIVACY_FILTER_AUTO_DOWNLOAD=false
PRIVACY_FILTER_DEVICE=auto
PRIVACY_FILTER_DECODE_MODE=viterbi
PRIVACY_FILTER_OUTPUT_MODE=typed
PRIVACY_FILTER_CONTEXT_WINDOW_LENGTH=0

BUSINESS_SENSITIVE_ENABLED=true
BUSINESS_SENSITIVE_PROVIDER=ollama
BUSINESS_SENSITIVE_MODEL=qwen3.5:4b
BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434
BUSINESS_SENSITIVE_QWEN_MODEL=deepseek-v4-flash
BUSINESS_SENSITIVE_QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
BUSINESS_SENSITIVE_QWEN_API_KEY=
BUSINESS_SENSITIVE_BEDROCK_MODEL=anthropic.claude-3-5-haiku-20241022-v1:0
BUSINESS_SENSITIVE_TIMEOUT_SECONDS=20

QWEN3GUARD_ENABLED=true
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-0.6B
QWEN3GUARD_MODEL_PATH=
QWEN3GUARD_MAX_NEW_TOKENS=96

FILE_REVIEW_ENABLED=true
FILE_REVIEW_PROVIDER=ollama
FILE_REVIEW_MODEL=qwen3.5:4b
FILE_REVIEW_BEDROCK_MODEL=anthropic.claude-3-5-haiku-20241022-v1:0
FILE_REVIEW_OLLAMA_URL=http://127.0.0.1:11434
FILE_REVIEW_TIMEOUT_SECONDS=45
FILE_REVIEW_MAX_UPLOAD_MB=20
FILE_REVIEW_DEFAULT_STORAGE_PATH=./uploaded-documents
```

Important notes:

- `backend/app/core/config.py` reads `backend/.env`; it does not read a root `.env`.
- `CORS_ORIGINS` is a comma-separated string. For multiple origins, use `http://10.0.0.7,https://your-domain.example`.
- Because Nginx is on a different server, do not bind the backend to `127.0.0.1`. Use `APP_HOST=0.0.0.0` and start Uvicorn with `--host 0.0.0.0`, or bind specifically to `10.0.0.9`.
- If Ollama is not on `10.0.0.9`, change both `BUSINESS_SENSITIVE_OLLAMA_URL` and `FILE_REVIEW_OLLAMA_URL` to the actual internal URL.
- If AWS Bedrock is enabled, attach an IAM role or configure AWS SDK credentials on `10.0.0.9`; the app does not store a Bedrock API key.

### 2.2.1 AWS Bedrock Runtime

If you use AWS Bedrock for chat or business-sensitive scanning, configure the backend server with an IAM role or AWS SDK credential chain that can invoke the target Bedrock models.

Minimum IAM action for non-streaming calls:

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel"
  ],
  "Resource": "*"
}
```

Also confirm in the AWS Bedrock console that the selected model is enabled in `BEDROCK_REGION`. The model string can be a base model ID, an inference profile ID, or an ARN supported by Bedrock Converse.

### 2.3 Database Migration

The Alembic environment reads `DATABASE_URL` from `backend/.env` through `backend/alembic/env.py`, so `backend/alembic.ini` does not need to be edited for this deployment.

Run:

```bash
cd /opt/enterprise-ai-security-gateway/backend
uv run alembic upgrade head
```

The app also calls `Base.metadata.create_all` on startup, but production deployments should still run Alembic explicitly.

### 2.4 Start Backend Manually for Smoke Test

```bash
cd /opt/enterprise-ai-security-gateway/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002 --workers 2
```

From `10.0.0.7`, validate:

```bash
curl http://10.0.0.9:8002/api/health
```

Expected:

```json
{"status":"ok"}
```

### 2.5 Configure Backend as a System Service

Create:

```text
/etc/systemd/system/ai-gateway-backend.service
```

Example:

```ini
[Unit]
Description=Enterprise AI Security Gateway Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/enterprise-ai-security-gateway/backend
ExecStart=/usr/local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8002 --workers 2
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-gateway-backend
sudo systemctl start ai-gateway-backend
sudo systemctl status ai-gateway-backend
```

Logs:

```bash
journalctl -u ai-gateway-backend -f
```

## 3. Frontend and Nginx Server: 10.0.0.7

### 3.1 Build Frontend

Build can happen on a build machine or on `10.0.0.7`.

Install:

- Node.js
- npm
- Git
- Nginx

Clone or copy the project:

```bash
cd /opt
git clone <repo-url> enterprise-ai-security-gateway
```

Install and build:

```bash
cd /opt/enterprise-ai-security-gateway/frontend
npm install
npm run build
```

### 3.2 Frontend API Base URL

The frontend client is:

```text
frontend/src/api/client.ts
```

Current recommended production behavior:

```ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
```

This means browser requests go to the same origin:

```text
http://10.0.0.7/api/...
```

Then Nginx proxies them to:

```text
http://10.0.0.9:8002/api/...
```

For this topology, do not set `VITE_API_BASE_URL` before `npm run build`, or set it to an empty value.

If you intentionally want the browser to call the backend directly, set:

```env
VITE_API_BASE_URL=http://10.0.0.9:8002
```

But that requires opening backend port `8002` to client browsers and maintaining CORS more carefully, so it is not recommended.

### 3.3 Deploy Static Files

Copy build output:

```bash
sudo mkdir -p /var/www/ai-gateway
sudo rsync -av --delete /opt/enterprise-ai-security-gateway/frontend/dist/ /var/www/ai-gateway/
```

The directory must contain:

```text
/var/www/ai-gateway/index.html
/var/www/ai-gateway/assets/...
```

### 3.4 Configure Nginx

Create:

```text
/etc/nginx/sites-available/ai-gateway
```

Config:

```nginx
server {
    listen 80;
    server_name 10.0.0.7;

    root /var/www/ai-gateway;
    index index.html;

    client_max_body_size 100m;

    location /api/ {
        proxy_pass http://10.0.0.9:8002/api/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /docs {
        proxy_pass http://10.0.0.9:8002/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://10.0.0.9:8002/openapi.json;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/ai-gateway /etc/nginx/sites-enabled/ai-gateway
sudo nginx -t
sudo systemctl reload nginx
```

If your Nginx package uses a single config file instead of `sites-available`, place the `server { ... }` block inside:

```text
/etc/nginx/nginx.conf
```

inside the existing `http { ... }` block.

### 3.5 Windows Nginx Variant

If the frontend server is Windows and Nginx is installed under `G:\nginx\nginx-1.31.3`, edit:

```text
G:\nginx\nginx-1.31.3\conf\nginx.conf
```

Put this inside `http { ... }`:

```nginx
server {
    listen 80;
    server_name 10.0.0.7;

    root D:/dist;
    index index.html;

    client_max_body_size 100m;

    location /api/ {
        proxy_pass http://10.0.0.9:8002/api/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /docs {
        proxy_pass http://10.0.0.9:8002/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://10.0.0.9:8002/openapi.json;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Windows Nginx paths should use forward slashes, for example `D:/dist`, not `D:\dist`.

Validate and start:

```powershell
cd G:\nginx\nginx-1.31.3
.\nginx.exe -t
.\nginx.exe
```

Reload after config changes:

```powershell
.\nginx.exe -s reload
```

## 4. File-by-File Configuration Checklist

### 4.1 `backend/.env`

Change these values:

```env
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8002
CORS_ORIGINS=http://10.0.0.7
DATABASE_URL=postgresql+psycopg://ai_guard_user:replace-with-a-strong-db-password@10.0.0.11:5432/ai_guard
JWT_SECRET_KEY=replace-with-a-long-random-secret
API_KEY_ENCRYPTION_SECRET=replace-with-a-long-random-secret
DEFAULT_ADMIN_PASSWORD=replace-with-initial-admin-password
```

If using HTTPS/domain later:

```env
CORS_ORIGINS=https://your-domain.example
```

or during migration:

```env
CORS_ORIGINS=http://10.0.0.7,https://your-domain.example
```

### 4.2 `frontend/src/api/client.ts`

Recommended:

```ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
```

This supports Nginx same-origin proxying.

### 4.3 `frontend/.env`

For this topology, either do not create `frontend/.env`, or use:

```env
VITE_API_BASE_URL=
```

Do not use the local development value in production:

```env
VITE_API_BASE_URL=http://127.0.0.1:8002
```

### 4.4 Nginx Config on 10.0.0.7

Change:

```nginx
server_name 10.0.0.7;
root /var/www/ai-gateway;
proxy_pass http://10.0.0.9:8002/api/;
```

Windows variant:

```nginx
server_name 10.0.0.7;
root D:/dist;
proxy_pass http://10.0.0.9:8002/api/;
```

### 4.5 PostgreSQL Config on 10.0.0.11

In `postgresql.conf`:

```conf
listen_addresses = '10.0.0.11'
port = 5432
```

In `pg_hba.conf`:

```conf
host    ai_guard    ai_guard_user    10.0.0.9/32    scram-sha-256
```

### 4.6 `backend/alembic.ini`

No production change is required. Although the file has a local `sqlalchemy.url`, `backend/alembic/env.py` overrides it with `DATABASE_URL` from `backend/.env`.

## 5. Deployment Verification

From PostgreSQL server `10.0.0.11`:

```bash
sudo systemctl status postgresql
```

From backend server `10.0.0.9`:

```bash
curl http://127.0.0.1:8002/api/health
curl http://10.0.0.9:8002/api/health
```

From frontend server `10.0.0.7`:

```bash
curl http://10.0.0.9:8002/api/health
curl http://127.0.0.1/api/health
curl http://127.0.0.1/login
```

From a browser:

```text
http://10.0.0.7/login
http://10.0.0.7/admin
http://10.0.0.7/app/chat
```

Expected behavior:

- `/login` loads the React app
- `/api/health` returns `{"status":"ok"}`
- Browser developer tools show API requests going to `http://10.0.0.7/api/...`, not `http://127.0.0.1:8002/api/...`
- Login succeeds with the default admin configured in `backend/.env`

## 6. Common Failure Checks

### Frontend 404 on `/login` or `/admin`

Nginx is missing React fallback routing. Confirm:

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### Frontend loads but login says API connection failed

Check browser developer tools. If requests go to `127.0.0.1:8002`, rebuild the frontend after fixing `frontend/src/api/client.ts` or `frontend/.env`.

Correct production behavior:

```text
http://10.0.0.7/api/auth/login
```

### Nginx returns 502 for `/api/health`

Check from `10.0.0.7`:

```bash
curl http://10.0.0.9:8002/api/health
```

If this fails:

- Backend service is not running
- Backend is bound to `127.0.0.1` instead of `0.0.0.0` or `10.0.0.9`
- Security group/firewall blocks `10.0.0.7 -> 10.0.0.9:8002`

### Backend cannot connect to database

Check from `10.0.0.9`:

```bash
psql "postgresql://ai_guard_user:replace-with-a-strong-db-password@10.0.0.11:5432/ai_guard" -c "select 1;"
```

If this fails:

- `backend/.env` has the wrong `DATABASE_URL`
- PostgreSQL is not listening on `10.0.0.11`
- `pg_hba.conf` does not allow `10.0.0.9/32`
- Security group/firewall blocks `10.0.0.9 -> 10.0.0.11:5432`

### CORS Error in Browser

Set `backend/.env`:

```env
CORS_ORIGINS=http://10.0.0.7
```

Then restart backend:

```bash
sudo systemctl restart ai-gateway-backend
```

If using HTTPS/domain, include the exact browser origin, including scheme and port when applicable.

## 7. Update and Redeploy

Backend:

```bash
cd /opt/enterprise-ai-security-gateway
git pull
cd backend
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
sudo systemctl restart ai-gateway-backend
```

Frontend:

```bash
cd /opt/enterprise-ai-security-gateway
git pull
cd frontend
npm install
npm run build
sudo rsync -av --delete dist/ /var/www/ai-gateway/
sudo nginx -t
sudo systemctl reload nginx
```

Windows Nginx static deploy variant:

```powershell
cd S:\Enterprise-AI-Security-Gateway-Dev\frontend
npm install
npm run build
Copy-Item -Path .\dist\* -Destination D:\dist -Recurse -Force
cd G:\nginx\nginx-1.31.3
.\nginx.exe -t
.\nginx.exe -s reload
```

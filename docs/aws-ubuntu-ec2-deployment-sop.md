# AWS Ubuntu EC2 单机部署 SOP

本文档用于把 Enterprise AI Security Gateway 的以下分支部署到一台 AWS Ubuntu EC2：

- 仓库：`https://github.com/czyllqhome/Enterprise-AI-Security-Gateway-Dev.git`
- 分支：`codex/original-attachment-security`
- 操作系统：Ubuntu Server 24.04 LTS，x86_64
- 部署形态：Nginx、React 静态文件、FastAPI、文件审核 worker 和 PostgreSQL 位于同一台 EC2

该拓扑适合演示、验证和单节点生产试运行。需要高可用、滚动发布或多实例扩容时，应把 PostgreSQL 迁移到 RDS，并把附件目录迁移到加密 EFS 或对象存储。

## 0. 目标架构

```text
Browser
  -> HTTPS 443
    -> Nginx
      -> frontend/dist
      -> /api/* -> FastAPI 127.0.0.1:8002

FastAPI / File Review Worker
  -> PostgreSQL 127.0.0.1:5432
  -> Bedrock or external model provider over HTTPS
  -> Ollama 127.0.0.1:11434 when using the optional local business scanner
```

只有 Nginx 的 `80/443` 对外开放。FastAPI `8002`、PostgreSQL `5432` 和 Ollama `11434` 都只监听本机或由主机防火墙阻断。

## 1. 上线前信息清单

开始前准备以下值，并存放在密码管理器中：

| 名称 | 示例 | 说明 |
| --- | --- | --- |
| AWS Region | `ap-southeast-1` | EC2、Bedrock 和备份所在区域 |
| 域名 | `ai-gateway.example.com` | 推荐配置；没有域名时先用 EC2 公网 IP |
| 管理员公网 CIDR | `203.0.113.10/32` | 仅在使用 SSH 时需要 |
| PostgreSQL 密码 | 64 位十六进制随机值 | 必须是 URL 安全字符 |
| JWT 密钥 | 至少 32 个随机字节 | 不要使用示例值 |
| Scan Proof 密钥 | 至少 32 个随机字节 | 生产就绪检查会验证 |
| API Key 加密密钥 | 至少 32 个随机字节 | 上线后必须稳定保存，不能随意轮换 |
| 初始管理员密码 | 强随机密码 | 首次登录并创建正式管理员后可从 `.env` 清空 |

可以分别执行以下命令生成随机值，每个用途使用不同结果：

```bash
openssl rand -hex 32
```

不要把真实密钥写入 Git、AMI、EC2 User Data 或工单正文。

## 2. 创建 EC2

### 2.1 推荐规格

本项目包含 Privacy Filter、Qwen3Guard、PaddleOCR、Office/PDF 解析和可选 Ollama，资源消耗明显高于普通 FastAPI 服务。以下是项目侧的起步估算，正式规格应以扫描器基准和业务并发压测为准：

| 使用方式 | 建议起点 |
| --- | --- |
| 功能验证，部分本地扫描器关闭 | 4 vCPU、16 GiB RAM |
| CPU 模式，Qwen3Guard 0.6B，外部 Business Sensitive | 8 vCPU、32 GiB RAM |
| Qwen3Guard 4B、独立 worker 或更多本地模型 | 16 vCPU、64 GiB RAM 起 |

建议使用：

- Ubuntu Server 24.04 LTS x86_64 AMI
- `gp3` EBS，至少 150 GiB
- 根卷启用 EBS 加密
- 不使用 Spot 实例承载唯一的生产节点
- 分配固定域名；需要固定公网地址时绑定 Elastic IP

模型缓存可能超过 15 GiB，附件、PostgreSQL、构建缓存和日志也会持续增长。不要使用默认的超小根卷。

### 2.2 Security Group

入站规则：

| 协议 | 端口 | 来源 | 用途 |
| --- | --- | --- | --- |
| TCP | `443` | 企业出口 CIDR 或 `0.0.0.0/0` | HTTPS 产品入口 |
| TCP | `80` | 同上 | 跳转 HTTPS、ACME 验证 |
| TCP | `22` | 管理员固定 CIDR | 仅在不用 Session Manager 时开放 |

不要添加以下公网入站规则：

- `8002`：FastAPI
- `5432`：PostgreSQL
- `11434`：Ollama
- `5173`：Vite 开发服务器

AWS Security Group 是有状态的，已允许连接的响应流量不需要额外开放临时入站端口。建议用 AWS Systems Manager Session Manager 管理实例，从而不开放 `22`。

出站至少需要 HTTPS `443`，用于 GitHub、Python/npm 依赖、Hugging Face、Bedrock 或外部模型提供商。若使用严格出站策略，还要按实际网络设计放通 Ubuntu 软件源、DNS、时间同步和所用 AWS VPC Endpoint。

### 2.3 IAM Role

给 EC2 绑定 Instance Profile，不要在 `.env` 中保存长期 AWS Access Key。

建议权限：

- 使用 Session Manager：附加 `AmazonSSMManagedInstanceCore`。
- 使用 Bedrock：自定义最小权限策略，仅允许目标模型或 inference profile 的：
  - `bedrock:InvokeModel`
  - `bedrock:InvokeModelWithResponseStream`
  - `bedrock:GetInferenceProfile`（使用 inference profile 时需要）
- 使用 CloudWatch Agent、Secrets Manager、EFS 或 S3 时，只增加实际需要的资源权限。

Bedrock 示例策略需将 `Resource` 收敛为实际模型或 inference profile ARN：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetInferenceProfile"
      ],
      "Resource": [
        "<BEDROCK_MODEL_OR_INFERENCE_PROFILE_ARN>"
      ]
    }
  ]
}
```

## 3. 连接实例并初始化系统

通过 EC2 Console 的 Session Manager 连接，或使用受限 SSH：

```bash
ssh -i /path/to/key.pem ubuntu@<EC2_PUBLIC_IP>
```

检查系统：

```bash
cat /etc/os-release
uname -m
df -h
free -h
```

更新系统并安装基础依赖：

```bash
sudo apt update
sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt install -y \
  ca-certificates curl git gnupg jq openssl rsync build-essential \
  nginx postgresql postgresql-contrib postgresql-client \
  libgl1 libglib2.0-0 libgomp1 libmagic1
```

如果要审核或渲染 Office 文件，安装 LibreOffice：

```bash
sudo DEBIAN_FRONTEND=noninteractive apt install -y libreoffice
command -v soffice
```

创建专用服务账号和数据目录：

```bash
sudo useradd --system --create-home --home-dir /var/lib/ai-gateway \
  --shell /usr/sbin/nologin ai-gateway
sudo install -d -o ai-gateway -g ai-gateway /opt/enterprise-ai-security-gateway
sudo install -d -m 0750 -o ai-gateway -g ai-gateway /var/lib/ai-gateway/model-cache
sudo install -d -m 0750 -o ai-gateway -g ai-gateway /var/lib/ai-gateway/uploads
```

## 4. 从指定 GitHub 分支 Clone

首次部署必须执行带 `--branch` 和 `--single-branch` 的 clone：

```bash
sudo -u ai-gateway -H git clone \
  --branch codex/original-attachment-security \
  --single-branch \
  https://github.com/czyllqhome/Enterprise-AI-Security-Gateway-Dev.git \
  /opt/enterprise-ai-security-gateway
```

验证分支和提交：

```bash
sudo -u ai-gateway -H git -C /opt/enterprise-ai-security-gateway status -sb
sudo -u ai-gateway -H git -C /opt/enterprise-ai-security-gateway branch --show-current
sudo -u ai-gateway -H git -C /opt/enterprise-ai-security-gateway log -1 --oneline
```

分支输出必须是：

```text
codex/original-attachment-security
```

## 5. 安装 uv、Python 3.11 和 Node.js 20

项目要求 Python `>=3.11,<3.12`。Ubuntu 24.04 的系统 Python 不是目标版本，因此使用 uv 管理独立 Python 3.11，不替换系统 Python。

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
sh /tmp/uv-install.sh
sudo install -m 0755 "$HOME/.local/bin/uv" /usr/local/bin/uv
rm /tmp/uv-install.sh
uv --version
```

为服务账号安装 Python 3.11，并创建后端环境：

```bash
sudo -u ai-gateway -H /usr/local/bin/uv python install 3.11
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H /usr/local/bin/uv venv --python 3.11
sudo -u ai-gateway -H /usr/local/bin/uv sync --frozen --no-dev --link-mode=copy
sudo -u ai-gateway -H .venv/bin/python --version
```

Python 输出必须是 `3.11.x`。

通过 NodeSource 安装 Node.js 20：

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x -o /tmp/nodesource_setup.sh
sudo -E bash /tmp/nodesource_setup.sh
rm /tmp/nodesource_setup.sh
sudo apt install -y nodejs
node --version
npm --version
```

Node.js 输出必须是 `v20.x` 或项目验证过的更高兼容版本。

## 6. 配置本机 PostgreSQL

确认服务运行：

```bash
sudo systemctl enable --now postgresql
sudo systemctl status postgresql --no-pager
```

创建项目用户。命令会交互式要求输入密码，避免把密码写入 shell 历史：

```bash
sudo -u postgres createuser --pwprompt ai_guard_user
sudo -u postgres createdb --owner=ai_guard_user --encoding=UTF8 ai_guard
```

验证数据库连接：

```bash
psql -h 127.0.0.1 -U ai_guard_user -d ai_guard -c "select current_database(), current_user;"
```

保持 PostgreSQL 仅监听本机。确认：

```bash
sudo ss -lntp | grep 5432
```

单机部署不要在 Security Group 中开放 `5432`。

## 7. 配置后端环境

复制配置模板：

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H cp .env.example .env
sudo chown ai-gateway:ai-gateway .env
sudo chmod 600 .env
sudoedit .env
```

至少核对并修改以下配置。尖括号内容必须替换，不要原样保留：

```env
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8002
CORS_ORIGINS=https://<YOUR_DOMAIN>

DATABASE_URL=postgresql+psycopg://ai_guard_user:<URL_SAFE_DB_PASSWORD>@127.0.0.1:5432/ai_guard
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT_SECONDS=30
DB_POOL_RECYCLE_SECONDS=1800

JWT_SECRET_KEY=<64_HEX_CHARS>
SCAN_PROOF_SECRET=<DIFFERENT_64_HEX_CHARS>
API_KEY_ENCRYPTION_SECRET=<DIFFERENT_STABLE_64_HEX_CHARS>
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=<INITIAL_ADMIN_PASSWORD>
DEFAULT_ADMIN_DISPLAY_NAME=Administrator

SCANNER_STRICT_MODE=true
SCANNER_TOTAL_DEADLINE_MS=15000
SCANNER_EXECUTOR_WORKERS=8

LOCAL_MODEL_CACHE_DIR=/var/lib/ai-gateway/model-cache
LOCAL_MODEL_DEVICE=cpu

PRIVACY_FILTER_ENABLED=true
PRIVACY_FILTER_MODEL_PATH=/var/lib/ai-gateway/model-cache/openai-privacy-filter
PRIVACY_FILTER_AUTO_DOWNLOAD=true
PRIVACY_FILTER_DEVICE=inherit

QWEN3GUARD_ENABLED=true
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-0.6B
QWEN3GUARD_MODEL_PATH=/var/lib/ai-gateway/model-cache/qwen3guard/Qwen3Guard-Gen-0.6B
QWEN3GUARD_DEVICE=inherit
QWEN3GUARD_WORKERS=1

FILE_REVIEW_ENABLED=true
FILE_REVIEW_WORKER_MODE=external
FILE_REVIEW_ACTIVE_STORAGE_PROFILE=linux
FILE_REVIEW_LINUX_STORAGE_PATH=/var/lib/ai-gateway/uploads
FILE_REVIEW_PER_USER_STORAGE_DIRS=true
FILE_OCR_DEVICE=inherit
OFFICE_CONVERTER_PATH=/usr/bin/soffice

ATTACHMENT_CAPABILITIES={}
```

如果暂时没有域名，部署验证阶段可使用：

```env
CORS_ORIGINS=http://<EC2_PUBLIC_IP>
```

### 7.1 Business Sensitive 使用 Bedrock（AWS 推荐）

EC2 已绑定 Bedrock IAM Role 时配置：

```env
BUSINESS_SENSITIVE_ENABLED=true
BUSINESS_SENSITIVE_PROVIDER=bedrock
BUSINESS_SENSITIVE_BEDROCK_MODEL=<MODEL_ID_OR_INFERENCE_PROFILE_ID>
BEDROCK_REGION=<AWS_REGION>
BEDROCK_DEFAULT_MODEL=<MODEL_ID_OR_INFERENCE_PROFILE_ID>
BEDROCK_PROFILE_NAME=
```

不要填写长期 AWS Access Key；Boto3 会读取 EC2 Instance Profile 的临时凭据。

### 7.2 Business Sensitive 使用本机 Ollama（可选）

如果不能使用 Bedrock，可按 Ollama 官方方法安装服务。生产环境建议先检查下载的安装脚本再执行：

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh
less /tmp/ollama-install.sh
sudo sh /tmp/ollama-install.sh
rm /tmp/ollama-install.sh

sudo systemctl enable --now ollama
ollama pull qwen3.5:4b
curl http://127.0.0.1:11434/api/tags
```

后端配置：

```env
BUSINESS_SENSITIVE_ENABLED=true
BUSINESS_SENSITIVE_PROVIDER=ollama
BUSINESS_SENSITIVE_MODEL=qwen3.5:4b
BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434
```

不要让 Ollama 监听公网地址，也不要开放 `11434`。

### 7.3 原文件发送能力

`ATTACHMENT_CAPABILITIES={}` 是安全默认值：未验证的模型不能接收原文件。只有在完成对应模型/MIME 的原件测试后，才通过精确模型 ID 配置允许列表，例如：

```env
ATTACHMENT_CAPABILITIES={"openai":{"<EXACT_MODEL_ID>":["application/pdf","image/png"]}}
```

不要为了让上传功能“看起来可用”而宽泛放行所有模型或 MIME。

## 8. 准备模型、迁移数据库

先准备 tokenizer：

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H .venv/bin/python scripts/prepare_scanner_assets.py
```

首次准备本地扫描器。此命令会按照 `.env` 下载并预热 Privacy Filter 和 Qwen3Guard，可能需要较长时间：

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H .venv/bin/python -c \
  "from app.services.guardrails.llm_guard_service import get_guardrail_service; get_guardrail_service(); print('local scanners ready')"
```

确认模型准备完成后，将 `.env` 改为：

```env
PRIVACY_FILTER_AUTO_DOWNLOAD=false
```

执行迁移：

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H .venv/bin/alembic current
sudo -u ai-gateway -H .venv/bin/alembic upgrade head
sudo -u ai-gateway -H .venv/bin/alembic current
```

当前分支应包含全量 Prompt 审计迁移 `20260911_0005`。

## 9. 配置 systemd

### 9.1 FastAPI 服务

创建 `/etc/systemd/system/ai-gateway-api.service`：

```ini
[Unit]
Description=Enterprise AI Security Gateway API
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=simple
User=ai-gateway
Group=ai-gateway
WorkingDirectory=/opt/enterprise-ai-security-gateway/backend
Environment=HOME=/var/lib/ai-gateway
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/enterprise-ai-security-gateway/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --workers 1
Restart=on-failure
RestartSec=5
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/ai-gateway

[Install]
WantedBy=multi-user.target
```

单机部署先使用一个 Uvicorn worker。每增加一个进程都可能重复加载本地模型，必须先验证内存余量。

### 9.2 文件审核 worker

创建 `/etc/systemd/system/ai-gateway-worker.service`：

```ini
[Unit]
Description=Enterprise AI Security Gateway File Review Worker
After=network-online.target postgresql.service ai-gateway-api.service
Wants=network-online.target
Requires=postgresql.service

[Service]
Type=simple
User=ai-gateway
Group=ai-gateway
WorkingDirectory=/opt/enterprise-ai-security-gateway/backend
Environment=HOME=/var/lib/ai-gateway
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/enterprise-ai-security-gateway/backend/.venv/bin/python -m app.workers.file_review_worker
Restart=on-failure
RestartSec=5
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/var/lib/ai-gateway

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-gateway-api ai-gateway-worker
sudo systemctl status ai-gateway-api ai-gateway-worker --no-pager
```

查看日志：

```bash
sudo journalctl -u ai-gateway-api -n 200 --no-pager
sudo journalctl -u ai-gateway-worker -n 200 --no-pager
```

检查本机 API：

```bash
curl --fail http://127.0.0.1:8002/api/health
curl --fail http://127.0.0.1:8002/api/health/ready | jq
```

`/api/health/ready` 必须返回 HTTP `200` 和 `"status": "ready"`。若返回 `503`，不要继续对外发布。

## 10. 构建前端

使用 lock file 安装并构建：

```bash
cd /opt/enterprise-ai-security-gateway/frontend
sudo -u ai-gateway -H npm ci
sudo -u ai-gateway -H npm run build
test -f dist/index.html
```

生产环境采用 Nginx 同源代理，不要设置本地开发值 `VITE_API_BASE_URL=http://127.0.0.1:8002`。默认留空即可。

部署静态文件：

```bash
sudo install -d -m 0755 /var/www/ai-gateway
sudo rsync -a --delete /opt/enterprise-ai-security-gateway/frontend/dist/ /var/www/ai-gateway/
sudo chown -R root:root /var/www/ai-gateway
```

## 11. 配置 Nginx

创建 `/etc/nginx/sites-available/ai-gateway`：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name <YOUR_DOMAIN_OR_PUBLIC_IP>;

    root /var/www/ai-gateway;
    index index.html;

    client_max_body_size 25m;

    location /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 30s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # /api/chat/confirm/stream 使用 NDJSON 流式输出。
        proxy_buffering off;
        proxy_cache off;
        add_header X-Accel-Buffering no;
    }

    location = /docs {
        proxy_pass http://127.0.0.1:8002/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /openapi.json {
        proxy_pass http://127.0.0.1:8002/openapi.json;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

启用站点：

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn /etc/nginx/sites-available/ai-gateway /etc/nginx/sites-enabled/ai-gateway
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

验证 HTTP：

```bash
curl --fail http://127.0.0.1/api/health
curl --fail http://127.0.0.1/login > /dev/null
```

## 12. 配置 HTTPS

先把域名 A/AAAA 记录指向 EC2，再安装 Certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <YOUR_DOMAIN>
sudo certbot renew --dry-run
```

确认 `.env` 中的 CORS 与浏览器实际 Origin 完全一致：

```env
CORS_ORIGINS=https://<YOUR_DOMAIN>
```

修改后重启 API：

```bash
sudo systemctl restart ai-gateway-api
```

如果这是只在企业内网开放的系统，可使用企业证书或内部 ALB 终止 TLS，但不要长期以明文 HTTP 传输登录凭证和 Prompt。

## 13. 上线验收

### 13.1 服务与端口

```bash
sudo systemctl is-active postgresql nginx ai-gateway-api ai-gateway-worker
sudo ss -lntp
```

预期：

- `80/443`：Nginx 对外监听
- `8002`：只监听 `127.0.0.1`
- `5432`：只监听 loopback 或 PostgreSQL 本机 socket
- `11434`：如启用 Ollama，只监听 `127.0.0.1`

### 13.2 HTTP 验收

```bash
curl --fail https://<YOUR_DOMAIN>/api/health
curl --fail https://<YOUR_DOMAIN>/api/health/ready | jq
curl -I https://<YOUR_DOMAIN>/login
```

### 13.3 产品验收

依次验证：

1. 使用初始管理员登录 `/login`。
2. 在 `/admin/api-keys` 配置实际聊天模型提供商。
3. 在 `/admin/scanners` 确认启用扫描器均为可用状态，严格模式已开启。
4. 发送普通 Prompt，确认成功放行。
5. 发送包含邮箱或电话的 Prompt，确认进入脱敏审查。
6. 发送提示注入测试文本，确认被拦截。
7. 在 `/admin/logs` 分别按 `allowed`、`review`、`blocked` 筛选，确认每次 Prompt 都有一条日志。
8. 上传允许类型的测试文件，确认 worker 完成审核。
9. 验证 `/api/chat/confirm/stream` 的响应可以持续输出，Nginx 没有聚合缓冲。

首次登录完成后，建议创建实名管理员、停用共享初始账号，并将 `.env` 中 `DEFAULT_ADMIN_PASSWORD` 清空后重启 API。

## 14. 日常运维

### 14.1 查看日志

```bash
sudo journalctl -u ai-gateway-api -f
sudo journalctl -u ai-gateway-worker -f
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### 14.2 PostgreSQL 备份

升级前执行逻辑备份：

```bash
BACKUP_FILE="$HOME/ai_guard_$(date +%Y%m%d_%H%M%S).dump"
sudo -u postgres pg_dump --format=custom ai_guard > "$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"
echo "$BACKUP_FILE"
```

生产环境还应通过 AWS Backup 或 Data Lifecycle Manager 定期创建加密 EBS 快照。EBS 快照不能替代 PostgreSQL 一致性备份。

### 14.3 磁盘与内存

```bash
df -h
du -sh /var/lib/ai-gateway/model-cache /var/lib/ai-gateway/uploads
free -h
ps -eo pid,comm,%mem,rss --sort=-rss | head
```

至少对根卷使用率、可用内存、API `5xx`、worker 失败和 PostgreSQL 可用性设置告警。

## 15. 更新指定分支

记录当前版本并备份数据库：

```bash
cd /opt/enterprise-ai-security-gateway
sudo -u ai-gateway -H git rev-parse HEAD
sudo -u ai-gateway -H git status --short
```

工作区必须为空。然后更新固定分支：

```bash
cd /opt/enterprise-ai-security-gateway
sudo -u ai-gateway -H git fetch origin codex/original-attachment-security
sudo -u ai-gateway -H git checkout codex/original-attachment-security
sudo -u ai-gateway -H git pull --ff-only origin codex/original-attachment-security
```

更新依赖、迁移和前端：

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H /usr/local/bin/uv sync --frozen --no-dev --link-mode=copy
sudo -u ai-gateway -H .venv/bin/alembic upgrade head

cd /opt/enterprise-ai-security-gateway/frontend
sudo -u ai-gateway -H npm ci
sudo -u ai-gateway -H npm run build
sudo rsync -a --delete dist/ /var/www/ai-gateway/
sudo chown -R root:root /var/www/ai-gateway

sudo systemctl restart ai-gateway-worker ai-gateway-api
sudo nginx -t
sudo systemctl reload nginx
```

重新执行健康检查和产品验收。

## 16. 回滚

不要在没有数据库备份的情况下直接执行 Alembic downgrade。

推荐顺序：

1. 停止外部流量或显示维护页。
2. 停止 API 与 worker。
3. 恢复升级前 PostgreSQL 逻辑备份或一致性 EBS 快照。
4. 将代码切回升级前记录的 commit。
5. 重新同步依赖和构建前端。
6. 启动服务并完成健康检查。

代码回滚示例，`<PREVIOUS_COMMIT>` 必须是上线前记录并验证过的提交：

```bash
sudo systemctl stop ai-gateway-api ai-gateway-worker
cd /opt/enterprise-ai-security-gateway
sudo -u ai-gateway -H git checkout <PREVIOUS_COMMIT>

cd backend
sudo -u ai-gateway -H /usr/local/bin/uv sync --frozen --no-dev --link-mode=copy

cd ../frontend
sudo -u ai-gateway -H npm ci
sudo -u ai-gateway -H npm run build
sudo rsync -a --delete dist/ /var/www/ai-gateway/

sudo systemctl start ai-gateway-api ai-gateway-worker
sudo systemctl reload nginx
```

只有确认旧代码兼容当前数据库结构时才能只回滚代码；否则必须同时恢复数据库。

## 17. 常见故障

### `/api/health` 正常但 `/api/health/ready` 返回 503

检查：

```bash
sudo journalctl -u ai-gateway-api -n 300 --no-pager
```

常见原因：

- `SCAN_PROOF_SECRET` 仍是示例值或不足 32 字节。
- Privacy Filter checkpoint 不完整且 `PRIVACY_FILTER_AUTO_DOWNLOAD=false`。
- Qwen3Guard 模型未下载完整或内存不足。
- Business Sensitive 选择了 Ollama，但 Ollama 未运行或模型未下载。
- Business Sensitive 选择了 Bedrock，但 EC2 IAM Role、Region 或模型 ID 不正确。
- 严格模式下任一已启用扫描器不可用。

### Nginx 返回 502

```bash
curl -v http://127.0.0.1:8002/api/health
sudo systemctl status ai-gateway-api --no-pager
sudo journalctl -u ai-gateway-api -n 200 --no-pager
```

### 登录页打开但 API 请求失败

浏览器请求必须访问同源 `/api/...`，不能访问浏览器自身的 `127.0.0.1:8002`。确认未在前端构建时写入错误的 `VITE_API_BASE_URL`，然后重新构建和同步 `dist/`。

### Alembic 连接失败

```bash
cd /opt/enterprise-ai-security-gateway/backend
sudo -u ai-gateway -H .venv/bin/python -c \
  "from app.core.config import get_settings; from sqlalchemy.engine import make_url; print(make_url(get_settings().database_url).drivername)"
```

输出必须是 `postgresql+psycopg`。不要打印完整 URL，以免泄露数据库密码。

### 文件长时间停留在 queued/processing

```bash
sudo systemctl status ai-gateway-worker --no-pager
sudo journalctl -u ai-gateway-worker -n 300 --no-pager
ls -ld /var/lib/ai-gateway/uploads
```

确认 API 与 worker 使用同一个 `.env`、PostgreSQL 和附件目录。

## 18. 多节点生产化改造

从单 EC2 扩展前，至少完成：

- PostgreSQL 迁移到私有子网 RDS，`5432` 只允许来自后端 Security Group。
- 附件迁移到加密 EFS，并让所有 API/worker 挂载同一 access point；不要使用实例临时盘。
- Nginx 替换为 ALB 或在 ALB 前后明确 TLS 边界。
- API 与 worker 分离实例或 Auto Scaling Group。
- 模型缓存使用预构建 AMI、EBS 快照或受控下载流程。
- 密钥迁移到 Secrets Manager，并设计 `API_KEY_ENCRYPTION_SECRET` 的备份与轮换方案。
- 配置 CloudWatch 指标、集中日志、告警、AWS Backup 和恢复演练。

## 19. AWS 官方参考

- [EC2 Security Group 创建与规则](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html)
- [EC2 Security Group 连接跟踪与有状态行为](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html)
- [EC2 IAM Role 与 Instance Profile](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [Systems Manager Session Manager 前置条件](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html)
- [Amazon EBS 加密](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption.html)
- [Amazon EBS 快照](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [Amazon Bedrock 模型推理前置权限](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-prereq.html)
- [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)
- [uv 管理 Python 版本](https://docs.astral.sh/uv/concepts/python-versions/)
- [NodeSource Node.js Debian/Ubuntu 发行包](https://github.com/nodesource/distributions)
- [Ollama Linux 安装](https://docs.ollama.com/linux)

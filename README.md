# Enterprise AI Security Gateway

企业 AI 安全网关演示/原型项目，用于在企业使用大模型前提供统一的身份认证、模型接入、安全扫描、敏感信息脱敏、审计日志和管理监控能力。

当前项目拆分为两个本地服务：

- 后端 API：FastAPI，默认运行在 `http://127.0.0.1:8002`
- 前端应用：React + Vite，默认运行在 `http://127.0.0.1:5173`

后端根路径 `/` 只返回服务元数据，不承载产品 UI；实际产品界面由 `frontend/` 下的 React 应用提供。

## 当前项目状态

- 已实现 JWT 登录、管理员鉴权、用户管理和默认管理员初始化。
- 已实现用户聊天、会话管理、聊天预扫描、一次性扫描凭证和流式确认发送流程。
- 已实现敏感信息识别、脱敏占位、提示注入检测、限制主题检测、源代码阻断和商务敏感内容扫描。
- 已实现 OpenAI、阿里云百炼/Qwen、OpenRouter、AWS Bedrock 和 Ollama 模型提供商配置。
- 已实现管理员控制台、扫描器开关/严格模式、扫描性能统计、审计日志、Token Usage 估算和 14 天趋势统计。
- 已实现附件上传、原件哈希与 MIME 校验、Office/PDF/图片文本提取、OCR/视觉护栏，以及基于 PostgreSQL 持久任务和单元断点的异步原件审核。
- 文件提取、OCR 和视觉识别结果只用于本工具的安全与隐私审核；业务模型接收用户 Prompt 与审核通过的原文件，不会接收自动拼接的提取正文或审核摘要。
- 后端使用 PostgreSQL 和 Alembic 迁移；启动时仍保留 `Base.metadata.create_all` 与兼容性补字段逻辑。
- 当前后端包含文件权限和聊天扫描性能测试；前端暂未发现单元测试或 E2E 测试配置。
- 仓库中仍保留 `backend/app/static/` 旧静态页面资源，但主线前端已经迁移到 `frontend/`。

## 最近更新（2026-08）

- 聊天扫描器改为并行执行，并为各扫描器设置独立超时、工作线程和总扫描截止时间；响应会返回总耗时及降级扫描器，管理员可通过 `GET /api/console/performance` 查看 p50、p95、p99、错误和超时指标。
- `POST /api/chat/preview` 会签发短时、一次性的 `scan_proof`。普通确认与流式确认都会校验用户、会话、输入摘要、附件和扫描器配置，防止绕过扫描、篡改内容或重复使用扫描结果。
- 新增 `POST /api/chat/confirm/stream`，以前端可逐段展示的 NDJSON 事件流返回模型输出；只有流式响应完整结束后才持久化消息，失败或客户端中断会记录发送失败状态。
- 新增扫描器严格模式：严格模式下，已启用扫描器不可用、报错或超时会按失败关闭策略阻止请求；管理端 `/admin/scanners` 可切换该模式。
- 新增 `GET /api/health/ready` 就绪检查，用于验证启用的扫描器和生产环境扫描凭证密钥；不满足条件时返回 `503`，原有 `GET /api/health` 继续作为存活检查。
- 文件审核由进程内临时后台任务升级为 PostgreSQL 持久队列，支持任务租约、`SKIP LOCKED` 并发领取、失败重试和进程重启后的过期任务恢复。单进程开发默认使用内嵌 worker，多实例部署应使用独立 worker。
- 上传接口限制请求大小并校验实际文件类型；文件审核不会静默截断长文档，模型或解析失败会得到 `unknown` 并禁止原件外发。
- 新增原件 SHA-256、审核策略版本、发送快照和消息附件关系；确认发送时重新校验权限、策略、原件字节与预览快照，重复确认不会重复调用模型。
- PDF 页面、图片帧和 Office 包内媒体可进入本地视觉护栏；Office 整页审核支持通过显式配置的 LibreOffice/soffice 隔离渲染，转换器不可用时保持失败关闭。
- OpenAI 兼容适配器通过 Responses 文件输入发送原件；只有 `ATTACHMENT_CAPABILITIES` 明确允许的模型/MIME 组合才可启用，其他适配器拒绝附件且不降级为提取文字。
- 增加数据库连接池、聊天上下文 token/消息上限、会话查询上限和管理查询时间窗口，减少长会话和大数据量下的资源占用。
- LLM 客户端增加复用缓存，OpenAI 兼容接口、AWS Bedrock 和 Ollama 均支持流式输出。
- 新增扫描器资产预准备和基准脚本，部署前可提前准备 Privacy Filter tokenizer，并验证 Qwen3Guard 实际运行设备及预热后的延迟。
- 新增 Alembic 迁移 `20260824_0002`、`20260824_0003` 和 `20260825_0004`；升级代码后必须执行 `uv run alembic upgrade head`。
- 云部署 SOP 补充了前端、后端和数据库三层 AWS Security Group 规则，以及 Bedrock/外部模型、Ollama 和 PostgreSQL 的最小网络路径。

## 技术栈

### 后端

- Python `>=3.11,<3.12`
- FastAPI、Uvicorn、SQLAlchemy、Alembic
- pydantic-settings，读取 `backend/.env`
- JWT 认证，`passlib[bcrypt]` 密码哈希
- OpenAI Python SDK、AWS SDK，接入 OpenAI、Qwen、OpenRouter、AWS Bedrock 和 Ollama
- `llm-guard`、OpenAI Privacy Filter、Qwen3Guard、自定义中英文规则和本地/远端商务敏感扫描
- `python-docx`、`openpyxl`、`python-pptx`、`pymupdf`、`pillow`、`paddleocr`、`paddlepaddle`
- pytest、pytest-asyncio、httpx

### 前端

- Vite 6
- React 19
- TypeScript 5
- React Router 7
- lucide-react
- 全局样式入口：`frontend/src/styles.css`

### 数据库与本地模型

- 默认数据库：PostgreSQL，示例连接 `127.0.0.1:5432`
- 默认数据库名/用户：`ai_guard` / `ai_guard_user`
- 默认本地模型缓存：`backend/.model-cache/`
- 商务敏感扫描和文件审核默认依赖 Ollama `http://127.0.0.1:11434` 与模型 `qwen3.5:4b`
- 商务敏感扫描也可在管理端切换到阿里云百炼 `deepseek-v4-flash`

## 目录结构

```text
.
├── README.md
├── AGENTS.md
├── docs/
│   └── cloud-deployment-sop.md
├── design md/
│   ├── Enterprise-AI-Security-Gateway-Dev-Plan.md
│   ├── attachment-understanding-development-plan.md
│   ├── dashboard_design.md
│   └── chat-sample功能说明.md
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── .env.example
│   └── src/
│       ├── main.tsx
│       ├── api/
│       ├── pages/
│       ├── state/AuthContext.tsx
│       ├── utils/format.ts
│       └── styles.css
└── backend/
    ├── README.md
    ├── ORIGINAL_ATTACHMENTS.md
    ├── pyproject.toml
    ├── uv.lock
    ├── .env.example
    ├── alembic.ini
    ├── alembic/
    ├── tests/
    └── app/
        ├── main.py
        ├── api/
        ├── core/
        ├── models/
        ├── schemas/
        ├── services/
        └── static/
```

## 环境要求

- Python `3.11`
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ 和 npm
- PostgreSQL 18 或兼容版本
- Ollama 和 `qwen3.5:4b`，用于默认商务敏感扫描和文件审核

## PostgreSQL 初始化

使用 PostgreSQL 管理员账号连接：

```powershell
psql -U postgres -h 127.0.0.1 -p 5432
```

创建项目数据库和用户：

```sql
CREATE USER ai_guard_user WITH PASSWORD 'change-me-strong-password';
CREATE DATABASE ai_guard OWNER ai_guard_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE ai_guard TO ai_guard_user;
\c ai_guard
GRANT USAGE, CREATE ON SCHEMA public TO ai_guard_user;
```

验证项目用户可连接：

```powershell
psql -U ai_guard_user -h 127.0.0.1 -p 5432 -d ai_guard
```

## 后端配置与启动

在项目根目录复制环境变量示例：

```powershell
Copy-Item backend/.env.example backend/.env
```

修改 `backend/.env` 中的关键配置：

```env
DATABASE_URL=postgresql+psycopg://ai_guard_user:change-me-strong-password@127.0.0.1:5432/ai_guard
JWT_SECRET_KEY=replace-with-a-long-random-secret
API_KEY_ENCRYPTION_SECRET=replace-with-another-long-random-secret
SCAN_PROOF_SECRET=replace-with-at-least-32-random-bytes
SCANNER_STRICT_MODE=true
FILE_REVIEW_WORKER_MODE=embedded
ATTACHMENT_CAPABILITIES={}
FILE_REVIEW_VISION_MODEL=
FILE_REVIEW_VISION_BASE_URL=http://127.0.0.1:11434
OFFICE_CONVERTER_PATH=
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
CORS_ORIGINS=http://127.0.0.1:5173
```

只有 `DEFAULT_ADMIN_PASSWORD` 非空，且配置的管理员用户不存在时，后端启动才会创建默认管理员。

安装依赖、执行迁移并准备扫描器资产：

```powershell
Set-Location backend
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
uv run python scripts/prepare_scanner_assets.py
```

可在部署前运行扫描器基准，检查 Qwen3Guard 实际设备和预热后的 p50/p95 延迟：

```powershell
uv run python scripts/benchmark_scanners.py --samples 5
```

## 部署时数据库迁移

部署到服务器或云主机后，先确认服务器上的 `backend/.env` 已配置生产数据库的 `DATABASE_URL`，然后在后端目录执行 Alembic 迁移：

```bash
cd /path/to/Enterprise-AI-Security-Gateway-Dev/backend
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
uv run python scripts/prepare_scanner_assets.py
```

如果依赖和扫描器资产已经在部署流程中准备完成，可以只执行：

```bash
cd /path/to/Enterprise-AI-Security-Gateway-Dev/backend
uv run alembic upgrade head
```

`backend/alembic/env.py` 会读取 `backend/.env` 中的 `DATABASE_URL`，因此部署时应以环境文件或环境变量指向目标 PostgreSQL 实例，不要依赖 `backend/alembic.ini` 中的本地示例地址。

启动后端 API：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

常用地址：

- 服务元数据：`http://127.0.0.1:8002/`
- API 文档：`http://127.0.0.1:8002/docs`
- 存活检查：`http://127.0.0.1:8002/api/health`
- 就绪检查：`http://127.0.0.1:8002/api/health/ready`

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/health
```

## 前端配置与启动

另开一个 PowerShell 窗口：

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

前端默认使用 `VITE_API_BASE_URL=http://127.0.0.1:8002`。

常用地址：

- 登录页：`http://127.0.0.1:5173/login`
- 用户聊天页：`http://127.0.0.1:5173/app/chat`
- 管理员首页：`http://127.0.0.1:5173/admin`
- 用户管理：`http://127.0.0.1:5173/admin/users`
- API Key 管理：`http://127.0.0.1:5173/admin/api-keys`
- 扫描器管理：`http://127.0.0.1:5173/admin/scanners`
- 系统配置：`http://127.0.0.1:5173/admin/configuration`
- Token Usage：`http://127.0.0.1:5173/admin/token-usage`
- 日志查看：`http://127.0.0.1:5173/admin/logs`

构建前端：

```powershell
npm run build
```

## 核心 API

- `POST /api/auth/login`
- `GET /api/sessions`
- `POST /api/chat/preview`
- `POST /api/chat/confirm`
- `POST /api/chat/confirm/stream`
- `GET /api/health/ready`
- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/performance`
- `GET /api/console/dashboard`
- `GET /api/console/token-usage`
- `GET /api/logs`
- `GET /api/providers`
- `POST /api/file-review/files/upload`

## 安全扫描流程

聊天发送分为两步：

1. 前端调用 `POST /api/chat/preview`，后端并行扫描用户输入并为未阻断结果签发短时、一次性的 `scan_proof`。
2. 前端根据扫描结果决定阻断、展示确认，或携带原扫描内容、实体和 `scan_proof` 调用 `POST /api/chat/confirm/stream`；保留的 `POST /api/chat/confirm` 可用于非流式调用。

确认阶段不会重复执行扫描器，而是校验凭证、输入摘要、附件、扫描器配置和一次性消费状态。当扫描结果需要确认时，前端会展示原始内容、脱敏内容和实体类型，用户只能发送脱敏版本。命中源代码、提示注入、限制主题或高风险商务敏感内容时，后端会阻断模型调用。

## 文件上传与审核

聊天输入栏支持上传：

- `.doc`
- `.docx`
- `.xlsx`
- `.pptx`
- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.webp`

文件上传后会保存原件哈希和验证后的 MIME，并在 PostgreSQL 中创建持久审核任务。worker 从原文件生成仅供护栏使用的文本、OCR、页面图像、Office 包内容和可选的渲染页面，依次执行视觉、商务敏感、隐私与安全扫描。任务支持租约、心跳、失败重试、异常恢复和按单元复用成功断点。任何未覆盖内容、扫描器不可用、模型无效响应或文件变化都会使结果保持 `unknown`，不能发送原件。默认单文件上限为 20 MB，默认存储目录为 `backend/uploaded-documents`。

聊天输入栏默认显示文件名、类型、状态与审核决定；提取内容仅在折叠的“审核详情（仅用于安全与隐私检查）”中查看。预扫描只扫描用户 Prompt，并创建绑定用户、会话、模型、配置、Prompt 和附件哈希的发送快照。确认阶段重新校验快照、一次性 `scan_proof`、权限、审核策略和实际原件哈希，然后将用户 Prompt 与原文件作为独立输入发送给明确支持该 MIME 的模型。提取正文、OCR、视觉描述和审核摘要不会加入业务 Prompt，也不会在模型不支持原件时充当降级输入。

详细协议、worker、配置和失败关闭规则见 [`backend/ORIGINAL_ATTACHMENTS.md`](backend/ORIGINAL_ATTACHMENTS.md)，开发及验收记录见 [`design md/attachment-understanding-development-plan.md`](design%20md/attachment-understanding-development-plan.md)。

本地单进程开发默认使用内嵌 worker：

```env
FILE_REVIEW_WORKER_MODE=embedded
```

生产或多实例部署应让 Web 服务使用 `FILE_REVIEW_WORKER_MODE=external`，并单独启动 worker：

```powershell
Set-Location backend
uv run python -m app.workers.file_review_worker
```

所有 API/worker 实例必须能访问同一文件目录；AWS 部署可将加密 EFS 挂载到 `FILE_REVIEW_LINUX_STORAGE_PATH`。不要把附件仅保存在 ECS 临时文件系统中。

通过 ALB、Nginx 或其他反向代理暴露 `POST /api/chat/confirm/stream` 时，需要关闭响应缓冲，并将空闲超时设置为大于模型提供商的调用超时。

## 新增关键配置

- 扫描凭证：`SCAN_PROOF_SECRET`、`SCAN_PROOF_TTL_SECONDS`、`REQUIRE_SCAN_PROOF`
- 扫描策略：`SCANNER_STRICT_MODE`、`SCANNER_TOTAL_DEADLINE_MS`、`SCANNER_EXECUTOR_WORKERS`
- 扫描器资源：`PRIVACY_FILTER_TIMEOUT_MS`、`PRIVACY_FILTER_WORKERS`、`QWEN3GUARD_DEVICE`、`QWEN3GUARD_TIMEOUT_MS`、`QWEN3GUARD_WORKERS`、`BUSINESS_SENSITIVE_TIMEOUT_MS`、`BUSINESS_SENSITIVE_WORKERS`
- 文件存储与队列：`FILE_REVIEW_ACTIVE_STORAGE_PROFILE`、`FILE_REVIEW_WINDOWS_STORAGE_PATH`、`FILE_REVIEW_LINUX_STORAGE_PATH`、`FILE_REVIEW_PER_USER_STORAGE_DIRS`、`FILE_REVIEW_WORKER_MODE`、`FILE_REVIEW_WORKER_POLL_SECONDS`、`FILE_REVIEW_JOB_LEASE_SECONDS`、`FILE_REVIEW_JOB_MAX_ATTEMPTS`
- 原件与视觉能力：`ATTACHMENT_CAPABILITIES`、`FILE_REVIEW_VISION_MODEL`、`FILE_REVIEW_VISION_BASE_URL`、`FILE_REVIEW_VISION_TIMEOUT`、`OFFICE_CONVERTER_PATH`、`OFFICE_CONVERTER_TIMEOUT`
- 数据库连接池：`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_TIMEOUT_SECONDS`、`DB_POOL_RECYCLE_SECONDS`
- 查询与上下文限制：`CHAT_CONTEXT_TOKEN_BUDGET`、`CHAT_CONTEXT_MAX_MESSAGES`、`SESSION_LIST_LIMIT`、`SESSION_DETAIL_MESSAGE_LIMIT`、`ADMIN_QUERY_LOOKBACK_DAYS`、`ADMIN_QUERY_MAX_ROWS`

生产环境必须将 `SCAN_PROOF_SECRET` 设置为至少 32 个随机字节，且不能使用示例值，否则就绪检查不会通过。

## 本地模型与缓存

拉取默认 Ollama 模型：

```powershell
ollama pull qwen3.5:4b
ollama serve
```

Privacy Filter 默认不会自动下载模型。如果 `backend/.model-cache/openai-privacy-filter` 不存在，需要提前准备模型，或在配置中明确启用自动下载。

后端会将 Hugging Face、Transformers、Torch 等缓存重定向到项目本地模型目录，避免污染系统级缓存。

## 测试

后端测试：

```powershell
Set-Location backend
uv run pytest
```

当前已发现的测试文件：

- `backend/tests/test_file_review_permissions.py`
- `backend/tests/test_chat_scan_performance.py`

前端当前仅配置了构建脚本，未发现单元测试或 E2E 测试脚本。

## 安全注意事项

- `backend/.env` 包含密钥和数据库密码，不应提交到版本库。
- `scan_events` 和高风险 `chat_logs` 可能保存原始敏感输入明文；处理真实数据前必须评估保留策略、加密策略和访问权限。
- Provider API Key 依赖 `API_KEY_ENCRYPTION_SECRET` 加密；部署后应保持密钥稳定并安全备份。
- 默认 CORS 仅允许 `http://127.0.0.1:5173`，更换前端地址时需要同步更新 `CORS_ORIGINS`。
- `Base.metadata.create_all` 和 Alembic 迁移同时存在；生产化前应明确数据库迁移策略，避免仅依赖自动建表。
- 文件审核、Privacy Filter、Qwen3Guard、PaddleOCR 和 Ollama 相关能力可能在首次运行时下载或加载较大的模型文件。
- 本地示例附件应放在已忽略的 `attachments_testfiles/` 中，不要提交到版本库。

# Enterprise AI Security Gateway

企业 AI 安全网关演示/原型项目，用于在企业使用大模型前提供统一的身份认证、模型接入、安全扫描、敏感信息脱敏、审计日志和管理监控能力。

当前项目拆分为两个本地服务：

- 后端 API：FastAPI，默认运行在 `http://127.0.0.1:8002`
- 前端应用：React + Vite，默认运行在 `http://127.0.0.1:5173`

后端根路径 `/` 只返回服务元数据，不承载产品 UI；实际产品界面由 `frontend/` 下的 React 应用提供。

## 当前项目状态

- 已实现 JWT 登录、管理员鉴权、用户管理和默认管理员初始化。
- 已实现用户聊天、会话管理、聊天预扫描和确认发送流程。
- 已实现敏感信息识别、脱敏占位、提示注入检测、限制主题检测、源代码阻断和商务敏感内容扫描。
- 已实现 OpenAI 兼容模型提供商配置，当前覆盖 OpenAI、阿里云百炼/Qwen、OpenRouter 和 Ollama。
- 已实现管理员控制台、扫描器开关、审计日志、Token Usage 估算和 14 天趋势统计。
- 已实现附件上传、Office/PDF/图片文本提取、OCR 和异步文件内容审核。
- 后端使用 PostgreSQL 和 Alembic 迁移；启动时仍保留 `Base.metadata.create_all` 与兼容性补字段逻辑。
- 当前存在后端测试 `backend/tests/test_file_review_permissions.py`；前端暂未发现单元测试或 E2E 测试配置。
- 仓库中仍保留 `backend/app/static/` 旧静态页面资源，但主线前端已经迁移到 `frontend/`。

## 技术栈

### 后端

- Python `>=3.11,<3.12`
- FastAPI、Uvicorn、SQLAlchemy、Alembic
- pydantic-settings，读取 `backend/.env`
- JWT 认证，`passlib[bcrypt]` 密码哈希
- OpenAI Python SDK，按 OpenAI 兼容接口接入 OpenAI、Qwen、OpenRouter 和 Ollama
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
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
CORS_ORIGINS=http://127.0.0.1:5173
```

只有 `DEFAULT_ADMIN_PASSWORD` 非空，且配置的管理员用户不存在时，后端启动才会创建默认管理员。

安装依赖并执行迁移：

```powershell
Set-Location backend
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
```

## 部署时数据库迁移

部署到服务器或云主机后，先确认服务器上的 `backend/.env` 已配置生产数据库的 `DATABASE_URL`，然后在后端目录执行 Alembic 迁移：

```bash
cd /path/to/Enterprise-AI-Security-Gateway-Dev/backend
uv sync --group dev --link-mode=copy
uv run alembic upgrade head
```

如果依赖已经在部署流程中安装完成，可以只执行：

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
- 健康检查：`http://127.0.0.1:8002/api/health`

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
- `GET /api/console/summary`
- `GET /api/console/scanners`
- `GET /api/console/dashboard`
- `GET /api/console/token-usage`
- `GET /api/logs`
- `GET /api/providers`
- `POST /api/file-review/files/upload`

## 安全扫描流程

聊天发送分为两步：

1. 前端调用 `POST /api/chat/preview`，后端先扫描用户输入。
2. 前端根据扫描结果决定阻断、展示确认，或调用 `POST /api/chat/confirm` 发送给模型。

当扫描结果需要确认时，前端会展示原始内容、脱敏内容和实体类型，用户只能发送脱敏版本。命中源代码、提示注入、限制主题或高风险商务敏感内容时，后端会阻断模型调用。

## 文件上传与审核

聊天输入栏支持上传：

- `.docx`
- `.xlsx`
- `.pptx`
- `.pdf`
- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.webp`

文件上传后由后端异步执行内容提取、OCR 和商务敏感审核。默认单文件上限为 20 MB，默认存储目录为 `backend/uploaded-documents`。

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

前端当前仅配置了构建脚本，未发现单元测试或 E2E 测试脚本。

## 安全注意事项

- `backend/.env` 包含密钥和数据库密码，不应提交到版本库。
- `scan_events` 和高风险 `chat_logs` 可能保存原始敏感输入明文；处理真实数据前必须评估保留策略、加密策略和访问权限。
- Provider API Key 依赖 `API_KEY_ENCRYPTION_SECRET` 加密；部署后应保持密钥稳定并安全备份。
- 默认 CORS 仅允许 `http://127.0.0.1:5173`，更换前端地址时需要同步更新 `CORS_ORIGINS`。
- `Base.metadata.create_all` 和 Alembic 迁移同时存在；生产化前应明确数据库迁移策略，避免仅依赖自动建表。
- 文件审核、Privacy Filter、Qwen3Guard、PaddleOCR 和 Ollama 相关能力可能在首次运行时下载或加载较大的模型文件。

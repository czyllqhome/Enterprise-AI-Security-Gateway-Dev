# Enterprise AI Security Gateway

企业 AI 安全网关演示/原型项目，由两个本地服务组成：

- 后端 API：FastAPI，默认 `http://127.0.0.1:8002`
- 前端应用：React + Vite，默认 `http://127.0.0.1:5173`

后端提供 JWT 认证、聊天会话、安全扫描、敏感信息脱敏、模型提供商配置、审计日志、管理看板、Token Usage 监控和文件内容审核。前端提供登录、用户聊天、附件上传及管理员平台。后端根路径只返回服务元数据，产品界面由 `frontend/` 提供。

## 当前版本

- 项目版本：`0.1.0`
- 后端版本来源：`backend/pyproject.toml`
- 前端版本来源：`frontend/package.json`

## 环境要求

- Python `3.11`（项目要求 `>=3.11,<3.12`）
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ 与 npm
- Docker Desktop（使用推荐的 PostgreSQL 模式时需要）
- Ollama 与 `qwen3.5:4b`（启用商务敏感扫描和文件审核时需要）

## 推荐运行方式：PostgreSQL

以下命令均在项目根目录使用 PowerShell 执行。

### 1. 启动 PostgreSQL

```powershell
docker compose -f docker-compose.postgres.yml up -d
docker compose -f docker-compose.postgres.yml ps
```

默认容器使用数据库 `ai_guard`、用户 `ai_guard_user`、密码 `change-me-strong-password`，并将容器内的 PostgreSQL `5432` 端口映射到宿主机 `5433`。数据持久化在 `data/postgres`。真实环境中请同时修改 Compose 和后端配置中的密码。

### 2. 配置后端

```powershell
Copy-Item backend/.env.example backend/.env
```

至少检查或修改 `backend/.env` 中的以下配置：

```env
DATABASE_URL=postgresql+psycopg://ai_guard_user:change-me-strong-password@127.0.0.1:5433/ai_guard
JWT_SECRET_KEY=replace-with-a-long-random-secret
API_KEY_ENCRYPTION_SECRET=replace-with-another-long-random-secret
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=replace-with-a-strong-password
CORS_ORIGINS=http://127.0.0.1:5173
```

只有 `DEFAULT_ADMIN_PASSWORD` 非空且管理员尚不存在时，启动过程才会创建默认管理员。请勿在真实环境中使用示例密钥或密码。

### 3. 安装并启动后端

```powershell
Set-Location backend
uv sync --group dev --link-mode=copy
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Windows Desktop、OneDrive 或受管理目录中建议保留 `--link-mode=copy`，以避免硬链接权限问题。

后端启动时会创建缺失的数据表，并对部分旧表字段执行兼容处理。项目同时保留 Alembic 迁移；生产化前应统一迁移策略，不要仅依赖自动建表。

### 4. 安装并启动前端

另开一个 PowerShell 窗口，在项目根目录执行：

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

前端默认使用 `VITE_API_BASE_URL=http://127.0.0.1:8002`。

### 5. 访问和验证

- 登录页：`http://127.0.0.1:5173/login`
- 用户聊天：`http://127.0.0.1:5173/app/chat`
- 管理员平台：`http://127.0.0.1:5173/admin`
- Token Usage：`http://127.0.0.1:5173/admin/token-usage`
- API 文档：`http://127.0.0.1:8002/docs`
- 健康检查：`http://127.0.0.1:8002/api/health`

```powershell
Invoke-RestMethod http://127.0.0.1:8002/api/health
```

## 轻量运行方式：SQLite

如果不需要 PostgreSQL，可不启动 Docker，并将 `backend/.env` 中的数据库地址改为：

```env
DATABASE_URL=sqlite:///./ai_guard_demo.db
```

从 `backend/` 目录启动 API 时，数据库文件会创建为 `backend/ai_guard_demo.db`。其余安装和启动命令与 PostgreSQL 模式相同。

## 本地模型与扫描器

商务敏感扫描和文件审核默认调用本地 Ollama：

```powershell
ollama pull qwen3.5:4b
ollama serve
```

默认连接为 `http://127.0.0.1:11434`。Privacy Filter 默认不会自动下载模型；若 `backend/.model-cache/openai-privacy-filter` 不存在，请提前准备模型或明确启用自动下载。首次初始化 LLM Guard、Qwen3Guard、PaddleOCR 等组件也可能需要较长时间和额外模型文件。

## 附件上传与审核

聊天输入栏支持 `.docx`、`.xlsx`、`.pptx`、`.pdf`、`.png`、`.jpg`、`.jpeg`、`.bmp` 和 `.webp`。

文件上传后由后端异步执行内容提取和商务敏感审核，前端轮询显示处理状态。默认单文件上限为 20 MB，默认存储目录为 `backend/uploaded-documents`。当前附件进入独立文件审核流程，不会自动拼接到模型对话上下文。

## 构建与停止

```powershell
Set-Location frontend
npm run build
```

```powershell
docker compose -f docker-compose.postgres.yml down
```

## 路由与权限

- 未登录用户跳转到 `/login`
- 普通用户登录后进入 `/app/chat`
- 管理员登录后进入 `/admin`
- 管理员功能同时受前端路由守卫和后端权限校验保护
- 聊天、会话和附件上传使用 JWT 中的当前用户身份

## 安全提示

- `backend/.env` 包含密钥和密码，不应提交到版本库。
- `scan_events` 和高风险 `chat_logs` 可能保存原始敏感输入；处理真实数据前必须评估保留策略和访问权限。
- Provider API Key 依赖 `API_KEY_ENCRYPTION_SECRET`，部署后应保持密钥稳定并安全备份。
- 默认 CORS 仅允许 `http://127.0.0.1:5173`；更换前端地址时需同步更新 `CORS_ORIGINS`。

更多后端配置、接口和数据库说明见 [backend/README.md](backend/README.md)。

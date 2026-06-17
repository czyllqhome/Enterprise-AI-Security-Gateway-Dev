# Enterprise AI Security Gateway 项目说明

## 项目概览

本项目是一个企业 AI 安全网关演示/原型项目，当前拆分为后端 API 服务和前端 React 应用两个本地服务：

- 后端 API：默认运行在 `http://127.0.0.1:8002`
- 前端应用：默认运行在 `http://127.0.0.1:5173`

后端负责认证、聊天会话、安全扫描、敏感信息脱敏、模型提供商配置、审计日志、管理看板、文件上传与文件内容审核等能力。前端负责登录、用户聊天页、管理员平台、API Key 管理、扫描器管理、日志查看和管理驾驶舱。

当前后端根路径 `/` 只返回服务元数据，不再承载产品 UI；产品 UI 由 `frontend/` 下的 Vite/React 应用提供。

## 技术栈

### 后端

- Python：要求 `>=3.11,<3.12`
- Web 框架：FastAPI
- ASGI 服务：Uvicorn
- 数据库访问：SQLAlchemy
- 数据迁移：Alembic
- 配置管理：pydantic-settings，读取 `backend/.env`
- 认证：JWT，密码哈希使用 `passlib[bcrypt]`
- LLM 调用：OpenAI Python SDK，项目中 OpenAI、Qwen、OpenRouter、Ollama 走 OpenAI 兼容/本地接口配置
- 安全扫描：
  - `llm-guard`
  - OpenAI Privacy Filter 依赖 `opf @ git+https://github.com/openai/privacy-filter.git`
  - Qwen3Guard 本地模型配置
  - 自定义中英文正则
  - Ollama 上的 `qwen3.5:4b` 用于商务敏感内容扫描
- 文件解析/审核：
  - `python-docx`
  - `openpyxl`
  - `python-pptx`
  - `pymupdf`
  - `pillow`
  - `paddleocr`
  - `paddlepaddle`
- 测试依赖：`pytest`、`pytest-asyncio`、`httpx`

### 前端

- Vite 6
- React 19
- TypeScript 5
- React Router 7
- lucide-react 图标
- 样式：`frontend/src/styles.css`

### 数据库与运行环境

- 默认配置可使用 SQLite，默认数据库路径由后端解析为 `backend/ai_guard_demo.db`
- `backend/.env.example` 中示例 `DATABASE_URL` 使用 PostgreSQL
- 根目录提供 `docker-compose.postgres.yml`，用于启动本地 PostgreSQL 16 容器
- 本地模型缓存默认位于 `backend/.model-cache/`

## 目录结构说明

```text
.
├── AGENTS.md                         # 本文件，供后续 AI Agent / 开发者快速理解项目
├── README.md                         # 根 README，说明前后端拆分、启动地址和路由模型
├── docker-compose.postgres.yml       # PostgreSQL 16 本地开发容器配置
├── data/                             # PostgreSQL 数据卷目录，来自 docker-compose 配置
├── design md/                        # 产品/设计说明文档
├── frontend/                         # React + Vite 前端应用
│   ├── package.json                  # 前端依赖与 npm scripts
│   ├── vite.config.ts                # Vite dev server 配置
│   ├── .env.example                  # 前端 API 地址示例
│   └── src/
│       ├── main.tsx                  # 前端路由入口与权限守卫
│       ├── api/                      # API client 与类型定义
│       ├── pages/                    # 登录、聊天、管理员页面
│       ├── state/AuthContext.tsx     # 前端认证状态
│       ├── utils/format.ts           # 格式化工具
│       └── styles.css                # 全局样式
└── backend/                          # FastAPI 后端
    ├── README.md                     # 后端功能、环境变量、运行方式说明
    ├── pyproject.toml                # Python 项目依赖、pytest 配置
    ├── uv.lock                       # uv 锁文件
    ├── .env.example                  # 后端环境变量示例
    ├── alembic.ini                   # Alembic 配置
    ├── alembic/                      # 数据库迁移脚本
    └── app/
        ├── main.py                   # FastAPI 应用入口、CORS、路由注册、启动建表
        ├── api/                      # API 路由
        ├── core/                     # 配置、数据库、认证、安全、日志、模型缓存
        ├── models/                   # SQLAlchemy ORM 模型
        ├── schemas/                  # Pydantic 请求/响应模型
        ├── services/                 # 业务服务层
        └── static/                   # 旧版/静态页面资源，当前根 README 说明产品 UI 由 frontend 提供
```

## 主要模块/功能说明

### 后端入口与生命周期

- `backend/app/main.py`
  - 创建 FastAPI 应用，标题为 `Enterprise AI Security Gateway API`
  - 配置 CORS，默认允许 `http://127.0.0.1:5173`
  - 注册健康检查、认证、用户管理、会话、聊天、控制台、文件审核、日志、模型提供商等路由
  - 启动时执行日志配置、数据库初始化、`Base.metadata.create_all`
  - 通过 `ensure_schema_compatibility` 给旧表补充部分字段
  - 如果配置了 `DEFAULT_ADMIN_PASSWORD`，启动时创建默认管理员

### 认证与用户

- 路由前缀：`/api/auth`、`/api/admin/users`
- 登录接口返回 JWT，前端保存在 `localStorage` 的 `gateway_access_token`
- `get_current_user` 从 Bearer Token 中解析用户
- `require_admin` 用于后端管理员权限校验
- 默认管理员仅在 `DEFAULT_ADMIN_PASSWORD` 非空且用户不存在时创建

### 聊天与会话

- 路由前缀：`/api/sessions`、`/api/chat`
- 会话支持创建、列表、详情、删除、更新 provider/model
- 聊天发送流程分为：
  - `POST /api/chat/preview`：先扫描用户输入
  - `POST /api/chat/confirm`：确认后调用模型并持久化消息
- 如果扫描结果需要用户确认，前端展示原始内容、脱敏内容和实体类型，用户只能发送脱敏版本
- 如果命中源代码、提示注入、限制主题或高风险商务敏感内容，后端会阻断模型调用

### Guardrails 安全扫描

核心实现位于 `backend/app/services/guardrails/`：

- `llm_guard_service.py`：统一扫描编排
- `privacy_filter_scanner.py`：Privacy Filter 集成
- `qwen3guard_scanner.py`：Qwen3Guard 集成，用于提示注入和限制主题等
- `business_sensitive_scanner.py`：通过 Ollama 本地模型识别商务敏感内容
- `chinese_patterns.py`：中英文自定义正则
- `masking.py`、`entity_normalizer.py`：实体归一化与脱敏占位

扫描器状态、启停和管理看板数据通过 `/api/console/*` 提供。

### 模型提供商配置

- 路由前缀：`/api/providers`
- 默认 provider catalog 定义在 `backend/app/core/provider_catalog.py`
- 当前发现的提供商：
  - OpenAI
  - 阿里云百炼/Qwen
  - OpenRouter
  - Ollama
- API Key、base URL、默认模型和模型列表可通过管理员前端配置
- API Key 加密相关配置为 `API_KEY_ENCRYPTION_SECRET`

### 审计日志与控制台

- 日志路由：`/api/logs`
- 控制台路由：`/api/console/summary`、`/api/console/scanners`、`/api/console/last-scan`、`/api/console/dashboard`、`/api/console/token-usage`
- 数据来自 `scan_events`、`chat_logs`、`uploaded_files` 等表
- 高风险日志会保存原始敏感 prompt 内容；这是当前实现的明确高风险行为

### Token Usage Monitoring

- 管理员页面路径：`/admin/token-usage`
- 后端接口：`GET /api/console/token-usage`
- 当前实现参考 llm-guard `TokenLimit` 的本地计数思路，使用 `tiktoken` 对文本执行 `encode`，并以 4096 token 作为 prompt 阈值。
- 统计按用户聚合 `scan_events` 中的输入文本（未保存原文时回退到脱敏输入）和确认发送后的 assistant 输出，展示总 token、输入/输出 token、请求数、最大单次输入 token、超过阈值次数、主要 provider/model 和 14 天趋势。
- 该功能用于管理侧容量与风险监控，当前 token 数是本地 tokenizer 估算值；如果需要精确计费，应优先读取第三方模型提供商响应中的 `usage` 字段或其官方 token count API。

### 文件上传与文件审核

- 路由前缀：`/api/file-review`
- 支持配置文件存储路径、上传文件、列出文件、查看文件审核详情
- 支持扩展名：
  - `.docx`
  - `.xlsx`
  - `.pptx`
  - `.pdf`
  - `.png`
  - `.jpg`
  - `.jpeg`
  - `.bmp`
  - `.webp`
- 文件解析使用 Office/PDF/图片 OCR 工具
- 文件商务敏感审核通过 `FileReviewScanner` 调用 Ollama 模型
- 上传后通过 FastAPI `BackgroundTasks` 异步处理文件

### 前端应用

- `frontend/src/main.tsx` 定义路由：
  - `/login`：登录页
  - `/app/chat`：用户聊天页
  - `/admin`：管理员首页/驾驶舱
  - `/admin/users`：用户管理
  - `/admin/api-keys`：模型提供商/API Key 管理
  - `/admin/scanners`：扫描器管理
  - `/admin/token-usage`：按用户监控 token 使用量和 TokenLimit 风险
  - `/admin/logs`：日志查看
- 未登录用户会跳转到 `/login`
- 普通用户登录后进入 `/app/chat`
- 管理员登录后进入 `/admin`
- 前端 API 地址默认 `http://127.0.0.1:8002`，可通过 `VITE_API_BASE_URL` 覆盖

## 启动、开发、测试、构建方式

### 后端安装依赖

在 `backend/` 目录执行：

```powershell
uv sync --group dev --link-mode=copy
```

README 中说明 Windows Desktop 或 OneDrive 管理目录中建议使用 `--link-mode=copy` 避免硬链接问题。

### 后端启动

在 `backend/` 目录执行：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

常用地址：

- 服务元数据：`http://127.0.0.1:8002/`
- OpenAPI 文档：`http://127.0.0.1:8002/docs`
- 健康检查：`http://127.0.0.1:8002/api/health`

### 前端安装依赖

在 `frontend/` 目录执行：

```powershell
npm install
```

### 前端开发启动

在 `frontend/` 目录执行：

```powershell
npm run dev
```

默认打开：

- 登录页：`http://127.0.0.1:5173/login`
- 用户聊天页：`http://127.0.0.1:5173/app/chat`
- 管理员平台：`http://127.0.0.1:5173/admin`

### 前端构建

在 `frontend/` 目录执行：

```powershell
npm run build
```

该命令会先执行 `tsc -b`，再执行 `vite build`。

### 前端预览

在 `frontend/` 目录执行：

```powershell
npm run preview
```

预览服务默认运行在 `http://127.0.0.1:4173`。

### 后端测试

`backend/pyproject.toml` 中配置了 pytest 的 `testpaths = ["tests"]`，README 也给出了：

```powershell
uv run pytest
```

但当前项目文件列表中未在 `backend/tests` 或根目录 `tests` 下发现项目测试文件。

README 提到的以下文件当前未在项目文件列表中发现：

- `tests/test_business_sensitive_integration.py`
- `scripts/validate_business_sensitive_ollama.py`

## 重要配置文件说明

- `README.md`
  - 当前根说明，明确前后端拆分、默认端口、登录和角色路由模型。
- `backend/README.md`
  - 后端详细说明，但其中部分内容可能与当前代码存在历史不一致，例如旧静态 UI、无认证等描述；使用时应优先核对当前代码和根 README。
- `backend/pyproject.toml`
  - Python 依赖、开发依赖、pytest 配置和 setuptools 包发现配置。
- `backend/.env.example`
  - 后端环境变量示例，包括 JWT、CORS、数据库、模型提供商、安全扫描、文件审核等配置。
- `backend/app/core/config.py`
  - 后端 Settings 定义；实际读取 `backend/.env`。
- `backend/alembic.ini`
  - Alembic 配置，默认 `sqlalchemy.url = sqlite:///./ai_guard_demo.db`。
- `backend/alembic/versions/20260614_0001_initial_product_schema.py`
  - 初始产品表结构迁移，包含用户、会话、消息、日志、扫描事件、上传文件、系统设置、提供商凭据等表。
- `docker-compose.postgres.yml`
  - 本地 PostgreSQL 16 配置，数据库名 `ai_guard`，用户 `ai_guard_user`，端口 `5432`，数据卷 `./data/postgres`。
- `frontend/package.json`
  - 前端依赖和 `dev`、`build`、`preview` 脚本。
- `frontend/.env.example`
  - 前端 API 地址示例：`VITE_API_BASE_URL=http://127.0.0.1:8002`。
- `frontend/vite.config.ts`
  - Vite React 插件和 dev server 端口配置。
- `.gitignore`
  - 当前未逐项整理；如需修改忽略规则应先查看该文件。

## 开发注意事项

- 不要把后端当作前端静态站点使用；当前根 README 明确产品 UI 由 `frontend/` 的 React 应用提供。
- 后端配置文件解析位置是 `backend/.env`，不是根目录 `.env`。
- 如果需要默认管理员，必须设置 `DEFAULT_ADMIN_PASSWORD`；否则启动时不会自动创建管理员。
- 开发环境默认 CORS 只允许 `http://127.0.0.1:5173`，如前端端口变化需要同步更新 `CORS_ORIGINS`。
- 默认 SQLite 数据库会落在 `backend/ai_guard_demo.db`；如果使用 PostgreSQL，需要设置 `DATABASE_URL` 并可配合根目录的 `docker-compose.postgres.yml`。
- 模型与扫描器可能依赖本地缓存、Hugging Face 模型、Ollama 服务和 PaddleOCR 相关模型；首次运行可能需要下载或准备模型文件。
- 商务敏感扫描和文件审核默认依赖本地 Ollama 地址 `http://127.0.0.1:11434` 和模型 `qwen3.5:4b`。
- Privacy Filter 默认 `PRIVACY_FILTER_AUTO_DOWNLOAD=false`，若本地 `backend/.model-cache/openai-privacy-filter` 不存在，相关扫描器可能不可用或降级。
- `scan_events` 和 `chat_logs` 会保存扫描与高风险日志信息；当前实现会保存原始敏感 prompt 明文，处理真实数据前必须评估合规风险。
- 前端部分中文文案在当前源码中显示为乱码，修改 UI 文案时应特别注意文件编码和实际浏览器显示效果。
- `backend/app/static/` 中仍保留旧静态页面资源；当前主线前端在 `frontend/`，修改产品 UI 时优先改 React 应用。
- 文件上传接口当前在 `routes_file_review.py` 中手写解析 multipart 请求，没有使用 FastAPI `UploadFile`；改动上传逻辑时需要特别小心兼容性。
- `Base.metadata.create_all` 和 Alembic 迁移同时存在；生产化前应明确数据库迁移策略，避免仅依赖自动建表。
- 当前未在项目中发现 CI 配置文件。
- 当前未在项目中发现 Dockerfile。
- 当前未在项目中发现前端单元测试或 E2E 测试配置。

# 基于现有 Demo 的产品化重构开发计划

## 1. 重构策略

本项目不建议完全重写，也不建议直接在 demo 上无边界追加功能。

采用策略：

**核心复用，外围重建。**

复用当前 demo 中已经验证过的安全护栏、聊天编排、provider 调用和 scanner 管理能力；重建认证、权限、数据安全、前后端分离、企业管理平台和部署结构。

目标是将当前 demo 改造成可面向约 100 人企业客户试上线的 AI 聊天助手 + 安全护栏产品。

## 2. 目标产品范围

第一版包含：

- 用户登录
- 管理员 Dashboard
- 用户管理
- API Key 管理
- Scanner 开关管理
- 普通用户聊天界面
- 安全日志查询
- 前后端分离部署
- PostgreSQL 数据库
- 敏感日志不保存原文

第一版不包含：

- 多租户组织管理
- 正式 SSO
- 复杂 RBAC
- 审批流
- 日志原文恢复
- 大规模高可用架构
- 文件审核产品化，除非后续重新确认

## 3. 推荐架构

### 后端

继续使用现有 FastAPI 项目作为基础。

保留：

- `backend/app/services/guardrails/`
- `backend/app/services/chat_service.py`
- `backend/app/services/llm/`
- `backend/app/services/provider_credential_service.py`
- `backend/app/services/system_setting_service.py`
- `backend/app/api/routes_chat.py`
- `backend/app/api/routes_console.py`
- `backend/app/api/routes_providers.py`
- `backend/app/api/routes_logs.py`
- `backend/app/api/routes_sessions.py`

新增：

```text
backend/app/api/routes_auth.py
backend/app/api/routes_admin_users.py
backend/app/core/auth.py
backend/app/core/security.py
backend/app/models/user.py
backend/app/schemas/auth.py
backend/app/schemas/users.py
backend/app/services/auth_service.py
backend/app/services/user_service.py
```

后端技术栈：

- FastAPI
- SQLAlchemy
- PostgreSQL
- Alembic
- JWT
- bcrypt 或 argon2
- CORS 配置支持前后端分离

### 前端

新增 React 项目，不继续扩展现有静态 HTML 页面。

```text
frontend/
  package.json
  vite.config.ts
  src/
    api/
    auth/
    components/
    layouts/
    pages/
    routes/
    styles/
```

前端技术栈：

- React
- TypeScript
- Vite
- React Router
- fetch 或 axios
- React Context 管理登录态

本地开发：

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8002
Database: PostgreSQL
```

## 4. 必须复用的 Scanner 机制明细

后续改造时必须保持当前 scanner 的检测语义，不要简单替换为一个通用 moderation 接口。

当前输入 scanner ID 由 `SystemSettingService.INPUT_SCANNER_IDS` 定义：

```text
bancode
prompt_injection
ban_topics
privacy_filter
business_sensitive
custom_regex
```

默认全部启用。管理员通过 `guardrail.enabled_scanners` 系统配置开关 scanner。

### 4.1 BanCode

用途：

- 检测源代码、代码片段、代码上传尝试、类似代码的 prompt

当前实现机制：

- 优先使用 LLM Guard 的 `BanCode`
- 模型常量来自 `llm_guard.input_scanners.ban_code.MODEL_SM`
- 如果模型不可用，继续启用本地启发式检测
- 支持 ONNX fallback，前提是本地有 cached ONNX snapshot 且 `optimum.onnxruntime` 可用

触发逻辑：

- 代码 fenced block，例如 ```python
- Python 风格：
  - `def`
  - `class`
  - `import`
  - `from`
  - `return`
  - `self.xxx =`
- JavaScript/Java/C 风格：
  - `const`
  - `let`
  - `var`
  - `function`
  - `public/private/protected/static`
  - `=>`
  - `{ ... }`
- 多行缩进代码
- 单行代码-like 内容达到一定长度

触发结果：

- scanner 名称：`BanCode`
- `blocked_reason` 包含中英文阻断说明
- 请求直接 blocked，不调用 LLM provider

产品化要求：

- 必须保留 LLM Guard BanCode + heuristic fallback 双层机制
- 不允许因为模型不可用就完全关闭代码检测
- Scanner 页面中要区分 `enabled`、`available`、`active`

### 4.2 PromptInjection

用途：

- 检测 jailbreak、prompt injection、绕过系统规则、泄露隐藏指令等攻击

当前使用模型：

```env
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-0.6B
QWEN3GUARD_MODEL_PATH=
QWEN3GUARD_MAX_NEW_TOKENS=96
QWEN3GUARD_ENABLED=true
```

当前实现机制：

- 使用本地 Hugging Face Transformers 加载 Qwen3Guard
- 默认模型：`Qwen/Qwen3Guard-Gen-0.6B`
- 优先从本地缓存加载
- 如本地没有模型，尝试通过 `huggingface_hub.snapshot_download` 下载
- 使用 `AutoTokenizer`
- 使用 `AutoModelForCausalLM`
- `trust_remote_code=True`
- `local_files_only=True` 用于实际加载
- CUDA 可用时使用 CUDA；否则使用 CPU；MPS 可用时可使用 MPS
- CUDA 且安装 `accelerate` 时使用 `device_map="auto"`

检测流程：

1. 将用户 prompt 包装成 chat template
2. 调用 Qwen3Guard 生成安全分类
3. 解析模型输出中的：
   - `Safety: Safe`
   - `Safety: Unsafe`
   - `Safety: Controversial`
4. 解析 categories：
   - `Jailbreak`
   - `Violent`
   - `Non-violent Illegal Acts`
   - `Suicide & Self-Harm`
   - `Unethical Acts`
   - `PII`
   - `Copyright Violation`
   - `Politically Sensitive Topics`
   - `None`

PromptInjection 触发条件：

- `safety_label` 为 `Unsafe` 或 `Controversial`
- categories 中包含 `Jailbreak`

触发结果：

- scanner 名称：`PromptInjection`
- 请求 blocked
- 不调用 LLM provider

产品化要求：

- 不要改成仅关键词检测
- 必须保留 Qwen3Guard 的分类结果解析
- 模型不可用时 scanner `available=false`，但系统应继续启动
- Dashboard / Scanner 管理页要展示 Qwen3Guard 当前模型引用路径

### 4.3 BanTopics

用途：

- 检测受限主题，包括危险、违法、自伤、欺诈、骚扰、歧视等

当前使用模型：

- 与 PromptInjection 共用 `Qwen/Qwen3Guard-Gen-0.6B`

当前实现机制：

- 先调用 Qwen3Guard 得到 moderation result
- 当 `safety_label` 为 `Unsafe` 或 `Controversial` 时，根据 category 和本地正则进一步映射为项目内部 banned topics

当前映射规则：

- `Suicide & Self-Harm`
  - 映射为 `self-harm`
- `Violent`
  - 如果命中武器相关 hint，映射为 `weapons`
  - 如果命中指导/教程类 hint，映射为 `illegal violent guidance`
  - 否则映射为 `violent wrongdoing`
- `Non-violent Illegal Acts`
  - 如果命中 phishing、fraud、money laundering、scam 等，映射为 `financial fraud`
  - 否则映射为 `restricted-topic`
- `Unethical Acts`
  - HR 场景歧视：`hr discriminatory or harassing content`
  - 骚扰：`harassment`
  - 歧视/仇恨：`discriminatory abuse`
  - 其他：`restricted-topic`
- `Jailbreak`
  - 不在 BanTopics 中处理，交给 PromptInjection

本地 hint 正则覆盖：

- weapons
- violent guidance
- self-harm
- financial fraud
- HR discrimination
- harassment
- discrimination

触发结果：

- scanner 名称：`BanTopics`
- 请求 blocked
- `blocked_reason` 包含受限主题列表
- 不调用 LLM provider

产品化要求：

- PromptInjection 和 BanTopics 虽然共用 Qwen3Guard，但要保留两个独立 scanner 开关
- 不要把 BanTopics 合并进 PromptInjection
- 本地 hint 正则必须继续保留，用于细分风险主题

### 4.4 Privacy Filter

用途：

- 检测 PII、地址、邮箱、手机号、账号、URL、日期、secret 等隐私和敏感实体

当前使用模型：

```env
PRIVACY_FILTER_MODEL_PATH=./.model-cache/openai-privacy-filter
PRIVACY_FILTER_AUTO_DOWNLOAD=false
PRIVACY_FILTER_DEVICE=auto
PRIVACY_FILTER_DECODE_MODE=viterbi
PRIVACY_FILTER_OUTPUT_MODE=typed
PRIVACY_FILTER_CONTEXT_WINDOW_LENGTH=0
```

模型来源：

```text
openai/privacy-filter
```

依赖包：

```text
opf @ git+https://github.com/openai/privacy-filter.git
```

当前实现机制：

- 使用 `opf.OPF`
- 模型 checkpoint 默认位于：
  - `backend/.model-cache/openai-privacy-filter`
- checkpoint 必须包含：
  - `config.json`
  - `*.safetensors`
- 如果模型缺失且 `PRIVACY_FILTER_AUTO_DOWNLOAD=false`，scanner 初始化失败
- 如果 `PRIVACY_FILTER_AUTO_DOWNLOAD=true`，从 Hugging Face 下载 `openai/privacy-filter`
- 下载时只拉取 `original/*`，然后提升到模型目录根部
- device：
  - `cuda`
  - `cpu`
  - `auto` 自动判断 torch cuda
- decode mode：
  - 默认 `viterbi`
  - 可选 `argmax`
- output mode：
  - 默认 `typed`
  - 可选 `redacted`

当前 label 映射：

```text
private_person    -> PERSON
private_address   -> ADDRESS
private_email     -> EMAIL_ADDRESS
private_phone     -> PHONE_NUMBER
private_url       -> PRIVATE_URL
private_date      -> PRIVATE_DATE
account_number    -> ACCOUNT_NUMBER
secret            -> SECRET
```

触发结果：

- scanner 名称：`Privacy Filter`
- 不一定直接 blocked
- 会生成 `GuardrailEntity`
- 会生成 `sanitized_text`
- 如果仅 PII 命中，进入 preview/confirm 流程，由用户发送脱敏版本
- 如果同时被其他阻断 scanner 命中，则 blocked

产品化要求：

- 必须保留 Privacy Filter 作为主要 PII 检测器
- 不能只依赖 custom regex
- 模型不可用时允许系统启动，但 Scanner 页面必须显示 unavailable
- 日志只保存 sanitized 内容，不保存原始命中文本

### 4.5 Custom Regex

用途：

- 作为 Privacy Filter 的补充，尤其增强中文和本地企业场景敏感信息检测

当前实现机制：

- 使用 `backend/app/services/guardrails/chinese_patterns.py` 中的 `CUSTOM_PATTERNS`
- 与 Privacy Filter 的结果合并
- 合并后进入实体归一化与脱敏流程

当前覆盖方向：

- 中文身份证
- 中国手机号
- 银行卡/信用卡
- 邮箱
- API Key / token / password / credential 类文本
- 数据库连接串、私钥、Authorization header 等 secret 类模式
- 中文上下文中的敏感表达

结果合并机制：

- Privacy Filter 和 Custom Regex 结果会去重
- 中文身份证等特定实体会有更高优先级
- 重叠实体按类型、来源和跨度选择更可信结果
- 相邻手机号实体会合并
- 最终生成统一 `GuardrailEntity`

触发结果：

- scanner 名称：`Custom Regex`
- 产生实体和 sanitized text
- 通常进入 preview/confirm 流程

产品化要求：

- 必须保留 Custom Regex，不能因为引入 Privacy Filter 就删除
- 中国本地客户场景下，Custom Regex 是必要补强
- 后续如果要调规则，应加测试，不要直接改核心合并逻辑

### 4.6 Business Sensitive

用途：

- 检测商务敏感内容，如合同、报价、客户数据、产品规格、投标、保险条款等

当前使用模型：

```env
BUSINESS_SENSITIVE_MODEL=qwen3.5:4b
BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434
BUSINESS_SENSITIVE_TIMEOUT_SECONDS=20
BUSINESS_SENSITIVE_ENABLED=true
```

当前实现机制：

- 使用本地 Ollama
- 调用接口：
  - `POST {OLLAMA_URL}/api/generate`
- 模型默认：
  - `qwen3.5:4b`
- 使用结构化 JSON schema 输出
- prompt 中强制：
  - `/no_think`
  - 不输出 reasoning
  - 不输出 markdown
  - 只输出 JSON
- 模型参数：
  - `temperature: 0`
  - `top_p: 0.1`
  - `repeat_penalty: 1.0`
  - `num_predict: 512`
  - `stream: false`
  - `think: false`

当前分类枚举：

```text
contract_terms
pricing
product_spec
commercial_plan
customer_data
insurance_policy_terms
insurance_coverage
insurance_premium
insurance_claims
insurance_underwriting
insurance_party_data
```

输出结构：

```text
contains_business_sensitive: boolean
risk_level: low | medium | high
categories: list
summary: string
confidence: float
```

当前阻断策略：

- 如果 `contains_business_sensitive=true`，scanner 记录命中
- 如果 `risk_level=high`，直接 blocked
- `medium` 级别一般进入 review / confirmation 相关流程
- 如果模型调用失败，返回 fallback：
  - `contains_business_sensitive=false`
  - `risk_level=low`
  - 不阻断请求

特殊降级逻辑：

- 如果只是个人简历、个人联系方式、个人资料整理等场景
- 且没有明确商务上下文
- 即使模型误判为 business sensitive，也会降级为普通 PII 处理
- 该逻辑用于避免把个人 PII 请求错误阻断为商务敏感

产品化要求：

- 必须保留 Ollama + qwen3.5:4b 的结构化 JSON 检测机制
- 必须保留商务敏感类别枚举
- 必须保留个人 PII 场景降级逻辑
- 高风险商务敏感内容继续 blocked
- 模型失败时不应导致整个聊天不可用，但要在 scanner 状态中体现风险

### 4.7 Deanonymize

用途：

- 将 assistant 输出中的 `[REDACTED_...]` 占位符恢复成用户侧可读内容

当前实现机制：

- 优先使用 LLM Guard 的：
  - `Deanonymize`
  - `Vault`
- 如果不可用，使用手动字符串替换 fallback
- 依赖当前 scan 中的 entity replacement 到 original 映射

当前定位：

- 不是输入 scanner
- 不属于 `INPUT_SCANNER_IDS`
- 在 scanner 状态中展示，但不允许管理员开关
- 用于用户显示层，不应进入安全日志原文保存

产品化要求：

- 可以继续保留
- 安全日志中不能保存 deanonymize 后的敏感原文
- 如果前端展示 deanonymized assistant output，要确保仅展示给对应会话 owner

### 4.8 Sensitive Logging

当前 demo 行为：

- 对敏感 prompt、确认发送、代码上传尝试、prompt injection 等写入 `/log`
- 当前 `ChatLog.original_sensitive_content` 会保存原始敏感内容

产品化必须调整：

- 不再保存原始敏感内容
- 不再保存 `original_sensitive_content`
- 新日志模型只保存：
  - sanitized content
  - entity types
  - scanner names
  - status
  - blocked reason
  - risk level
  - username
  - session id
  - message id
  - created_at

这是本次产品化重构的强制安全要求。

## 5. Guardrail 主流程要求

必须保持当前 preview / confirm 两段式流程。

### 5.1 Preview

接口：

```http
POST /api/chat/preview
```

流程：

1. 后端从 JWT 获取当前用户
2. 读取当前启用 scanner 列表
3. 调用 `GuardrailService.scan_text`
4. 生成：
   - original text
   - sanitized text
   - entities
   - scanners
   - blocked reason
   - business sensitive result
5. 如果 BanCode / PromptInjection / BanTopics / high-risk Business Sensitive 命中：
   - 返回 blocked
   - 不调用 LLM
   - 记录脱敏安全日志
6. 如果只有 PII / secret / custom regex 命中：
   - 返回 needs confirmation
   - 前端展示脱敏版本
7. 如果 clean：
   - 前端可自动进入 confirm

### 5.2 Confirm

接口：

```http
POST /api/chat/confirm
```

流程：

1. 后端再次校验 session owner
2. 重新校验原始输入和 sanitized 输入
3. 禁止绕过 preview 直接提交原文敏感内容
4. 只将允许发送的 sanitized prompt 发送给 LLM provider
5. 保存聊天记录
6. 保存 scan event
7. 安全日志只保存 sanitized 内容

## 6. 认证与权限计划

新增本地用户登录，预留 SSO 扩展。

角色：

```text
admin
user
```

新增表：

```text
users
  id
  username
  password_hash
  display_name
  role
  is_active
  created_at
  updated_at
  last_login_at
```

新增接口：

```http
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
POST /api/auth/change-password
```

管理员用户管理：

```http
GET    /api/admin/users
POST   /api/admin/users
PATCH  /api/admin/users/{user_id}
POST   /api/admin/users/{user_id}/reset-password
DELETE /api/admin/users/{user_id}
```

权限规则：

- admin 可访问 Dashboard、Users、API Keys、Scanners、Logs、Chat
- user 只能访问 Chat 和自己的 session
- 所有管理接口必须使用 `require_admin`
- Chat 和 Sessions 必须使用 `get_current_user`
- 后端不再信任前端传入的 username

## 7. 数据库改造计划

从 SQLite 产品化迁移到 PostgreSQL。

新增：

- PostgreSQL driver
- Alembic
- migration scripts
- `.env.example` 中的 PostgreSQL 配置

建议配置：

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/ai_guard
```

改造要求：

- 保留 SQLAlchemy ORM
- 现有 model 可迁移到 PostgreSQL
- 不再依赖 `ensure_schema_compatibility` 做生产迁移
- 生产 schema 变更必须通过 Alembic

## 8. API Key 安全计划

当前 demo 中 `ProviderCredential.api_key` 是明文。产品化必须改造。

目标：

- API Key 不明文返回前端
- 数据库中不建议明文存储
- 后端调用 provider 时可解密使用

改造：

```text
provider_credentials
  encrypted_api_key
```

新增配置：

```env
API_KEY_ENCRYPTION_SECRET=replace-me
```

接口响应：

```json
{
  "provider": "openai",
  "display_name": "OpenAI",
  "masked_api_key": "sk-****abcd",
  "base_url": "https://api.openai.com/v1",
  "default_model": "gpt-4.1-mini",
  "models": ["gpt-4.1-mini"]
}
```

要求：

- admin 可新增、更新、删除 key
- user 不可访问 key 管理接口
- 普通聊天页如需 provider/model 列表，使用 safe runtime provider API

## 9. React 前端计划

新增 React 应用，不复用静态 HTML 文件。

页面：

```text
/login
/app/chat
/app/dashboard
/app/users
/app/api-keys
/app/scanners
/app/logs
```

权限：

- 未登录跳转 `/login`
- admin 默认进入 `/app/dashboard`
- user 默认进入 `/app/chat`
- user 访问管理路由时显示无权限或重定向

### Chat 页面

必须实现：

- 会话列表
- 新建会话
- 删除会话
- 消息列表
- provider/model 选择
- prompt 输入
- preview/confirm 安全流程
- blocked 状态提示
- needs confirmation 弹窗
- sanitized 内容确认发送

### Dashboard 页面

展示：

- 总请求数
- blocked 数
- review required 数
- PII 命中数
- 商务敏感命中数
- 活跃用户
- 风险趋势
- 高频风险用户
- 最近安全事件
- scanner governance snapshot

不得展示：

- 原始敏感 prompt
- 原始 API Key
- deanonymize 后的敏感日志内容

### Users 页面

admin only：

- 用户列表
- 新建用户
- 禁用用户
- 重置密码
- 修改角色

### API Keys 页面

admin only：

- provider 配置
- base url
- default model
- model list
- masked key
- 新增/更新 key

### Scanners 页面

admin only：

- 展示 scanner id
- 展示 scanner name
- 展示 enabled
- 展示 available
- 展示 active
- 展示模型或检测机制说明
- 支持开关输入 scanner

必须展示的模型说明：

```text
BanCode: LLM Guard BanCode + heuristic fallback
PromptInjection: Qwen/Qwen3Guard-Gen-0.6B
BanTopics: Qwen/Qwen3Guard-Gen-0.6B + local topic mapping
Privacy Filter: openai/privacy-filter via OPF
Business Sensitive: Ollama qwen3.5:4b structured JSON classifier
Custom Regex: local Chinese/English sensitive patterns
Deanonymize: LLM Guard Deanonymize/Vault or manual replacement fallback
```

### Logs 页面

admin only：

- 分页
- 用户过滤
- scanner 过滤
- 风险等级过滤
- 时间过滤
- 展示 sanitized content
- 展示 entity types
- 展示 scanners
- 展示 status
- 展示 blocked reason

禁止：

- 原文查看
- 原文恢复
- 导出原始敏感内容

## 10. 开发阶段拆分

### 阶段 1：后端产品化基础

任务：

- 引入 PostgreSQL
- 引入 Alembic
- 添加生产 `.env.example`
- 建立 migration
- 保持现有 guardrail service 可启动
- CORS 支持 React 前端域名

验收：

- PostgreSQL 可创建所有表
- `/api/health` 正常
- 现有 scanner 初始化状态可通过 API 查看

### 阶段 2：认证与用户系统

任务：

- 新增 User model
- 新增 auth schemas
- 新增 password hash
- 新增 JWT 工具
- 新增 login/me 接口
- 新增默认 admin 初始化方式
- 新增 admin user management API

验收：

- admin 可登录
- user 可登录
- 禁用用户不可登录
- 错误密码返回 401
- `/api/auth/me` 返回当前用户

### 阶段 3：权限接入

任务：

- sessions 接入 current user
- chat 接入 current user
- providers admin only
- logs admin only
- scanner update admin only
- dashboard admin only
- 移除前端 username 信任

验收：

- user 不能访问管理 API
- user 不能访问其他用户 session
- admin 可访问管理 API
- 所有 chat/session 数据归属于当前用户

### 阶段 4：敏感日志改造

任务：

- 停止写入 `original_sensitive_content`
- 新增或重构为 `security_logs`
- scan event 中不保存原始敏感输入
- logs API 返回脱敏内容
- dashboard 不返回原始输入
- 增加数据库内容检查测试

验收：

- 输入手机号后，数据库中不出现手机号原文
- 输入邮箱后，数据库中不出现邮箱原文
- 输入 API key 后，数据库中不出现 key 原文
- logs API 只返回 sanitized 内容

### 阶段 5：API Key 安全改造

任务：

- 增加加密工具
- ProviderCredential 改为 encrypted key
- 响应只返回 masked key
- provider 调用时后端解密
- 增加测试

验收：

- API Key 可保存并用于调用
- API 响应不含明文 key
- 数据库不直接出现明文 key

### 阶段 6：React 应用初始化

任务：

- 创建 Vite React TypeScript 项目
- 配置 API client
- 配置 auth context
- 配置 protected routes
- 配置 admin routes
- 配置基础布局

验收：

- 前端可启动
- 登录后按角色跳转
- 刷新页面可恢复登录态

### 阶段 7：React Chat

任务：

- 实现 session list
- 实现 message list
- 实现 send prompt
- 接入 preview/confirm
- 实现 blocked UI
- 实现 needs confirmation modal
- 实现 sanitized send

验收：

- clean prompt 正常回复
- PII prompt 进入确认流程
- prompt injection blocked
- source code blocked
- high-risk business sensitive blocked

### 阶段 8：React 管理平台

任务：

- Dashboard
- Users
- API Keys
- Scanners
- Logs

验收：

- admin 完成所有管理操作
- user 看不到管理入口
- scanner 开关后后端行为变化
- logs 中无原始敏感内容

### 阶段 9：回归测试与安全验收

必须测试的 scanner 场景：

- BanCode:
  - 输入 Python/JS 代码，应 blocked
- PromptInjection:
  - 输入绕过系统规则、忽略 previous instructions 类 prompt，应 blocked
- BanTopics:
  - 输入武器制作、自伤、诈骗、骚扰、歧视等，应 blocked
- Privacy Filter:
  - 输入邮箱、手机号、地址、账号，应产生 sanitized text
- Custom Regex:
  - 输入中国身份证、中文手机号、API token，应命中
- Business Sensitive:
  - 输入报价、合同条款、客户名单、投标方案，应命中
  - high risk 应 blocked
  - 个人简历/个人联系方式整理不应误判为商务敏感 blocked
- Logging:
  - 所有命中场景均不得在日志中保存原文

## 11. 配置清单

后端：

```env
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8002

DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/ai_guard

JWT_SECRET_KEY=replace-me
JWT_EXPIRES_MINUTES=480
CORS_ORIGINS=http://127.0.0.1:5173

API_KEY_ENCRYPTION_SECRET=replace-me

DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4.1-mini

PRIVACY_FILTER_ENABLED=true
PRIVACY_FILTER_MODEL_PATH=./.model-cache/openai-privacy-filter
PRIVACY_FILTER_AUTO_DOWNLOAD=false
PRIVACY_FILTER_DEVICE=auto
PRIVACY_FILTER_DECODE_MODE=viterbi
PRIVACY_FILTER_OUTPUT_MODE=typed
PRIVACY_FILTER_CONTEXT_WINDOW_LENGTH=0

BUSINESS_SENSITIVE_ENABLED=true
BUSINESS_SENSITIVE_MODEL=qwen3.5:4b
BUSINESS_SENSITIVE_OLLAMA_URL=http://127.0.0.1:11434
BUSINESS_SENSITIVE_TIMEOUT_SECONDS=20

QWEN3GUARD_ENABLED=true
QWEN3GUARD_MODEL=Qwen/Qwen3Guard-Gen-0.6B
QWEN3GUARD_MODEL_PATH=
QWEN3GUARD_MAX_NEW_TOKENS=96
```

前端：

```env
VITE_API_BASE_URL=http://127.0.0.1:8002
```

## 12. 交付物

最终应交付：

- 产品化 FastAPI 后端
- React 前端
- PostgreSQL migration
- 默认管理员初始化方式
- 本地双服务启动说明
- Scanner 明细文档
- API 权限说明
- 敏感日志安全说明
- 核心自动化测试
- 企业试上线部署建议

## 13. 给 Codex 的关键约束

实施时必须遵守：

- 不重写 scanner 核心机制，优先复用现有 guardrail service
- 不删除 Qwen3Guard、Privacy Filter、Business Sensitive、Custom Regex 的组合检测
- 不把所有 scanner 合并成单一 moderation 调用
- 不保存原始敏感日志
- 不信任前端传入 username
- 不让普通用户访问管理接口
- 不在前端或 API 响应中暴露明文 API Key
- 不在模型不可用时让整个系统崩溃，scanner 状态应体现 unavailable

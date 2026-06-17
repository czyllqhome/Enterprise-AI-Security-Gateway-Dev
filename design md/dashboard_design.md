我当前项目是 React + Vite。请不要修改现有左侧导航、路由壳、全局 layout，只在现有页面内容区域内实现一个 “AI Security Guardrail Dashboard” 主内容页。

目标：
复刻一个面向管理层的 AI 安全网关 Dashboard，展示实时请求风险、拦截、复核、PII/商业敏感命中、文档风险、高风险用户、治理动作和事件审计。页面应是企业级安全运营驾驶舱风格，信息密度高、适合大屏监控，不要做营销页或 landing page。

实现范围：
1. 新增或替换 Dashboard 页面组件。
2. 不改现有 Sidebar / AppShell / Header 导航结构。
3. 主内容区需要自适应现有 layout 的宽度。
4. 如果项目已有 UI 组件、卡片、按钮、主题变量，优先复用；否则用普通 React + CSS Modules 或普通 CSS 实现。
5. 图表可以优先用 SVG 手写，避免额外依赖；如果项目已有 recharts/echarts，可使用已有库。

页面模块顺序：

1. Dashboard Header
   - eyebrow: Executive Oversight
   - h1: AI Security Guardrail Dashboard
   - 中文摘要：面向管理层的实时风险态势：请求量、拦截、复核、文档风险、高风险用户和审计证据集中呈现。
   - 右侧 Scanner Statuses 状态网格。
   - 扫描器包括：
     - Source Code Scanner
     - Prompt Injection Scanner
     - AI Ethical Scanner
     - Privacy Information Scanner
     - Business Sensitive Scanner
     - Custom Rule Match
   - 状态分为 Active / Disabled / Unavailable。
   - Active 绿色，Disabled 红色，Unavailable 灰色。

2. Live Request Posture
   - 深色横向风险态势条。
   - 默认选中 24H。
   - 时间窗口 tab：
     - 1H, 6H, 24H, 7D, 1M, 3M, 6M, 1Y
   - 展示：
     - 风险等级：Elevated Risk / Review Watch / Nominal
     - Monitoring {total} requests / {requests_per_minute} req/min
     - {risk_count} risks detected
     - sparkline 小折线图
   - 风险等级规则：
     - blocked > 0 或 risk_count >= 3：Elevated Risk
     - needs_review > 0 或 risk_count > 0：Review Watch
     - 其他：Nominal

3. KPI Metrics
   - 8 张紧凑 KPI 卡片：
     - Requests
     - Blocked
     - Needs Review
     - PII Hits
     - Business Sensitive
     - Confirmed Sends
     - Active Users
     - High-risk Files
   - 每张卡显示 label、数值、说明文案、彩色小圆点。
   - 卡片 hover/click 后展示右侧详情面板内容。

4. Primary Dashboard Grid
   - 左侧：Risk Intelligence
   - 右侧：Daily Security Trend + Daily Risk Cards
   - 详情面板作为浮层，不占主布局固定空间。

5. Risk Intelligence
   - 深色卡片。
   - 包含两个子区域：
     - Top Risk Categories：donut chart + 类别百分比列表
     - Risk Trend (Last 24h)：多条小折线趋势
   - 风险类别颜色：
     - prompt_injection: #ef4444
     - pii_or_secret: #a855f7
     - business_sensitive: #f59e0b
     - source_code: #0ea5e9
     - restricted_topic: #14b8a6
     - document_risk: #8b5cf6
     - manual_rejection: #f43f5e
     - other: #64748b

6. Daily Security Trend
   - 标题：Requests, blocks, and reviews by day
   - 展示 14 天折线图：
     - Requests: #0ea5e9
     - Blocked: #ef4444
     - Needs Review: #f59e0b
   - 图表点和 legend 可点击，联动详情面板。
   - 下方 legend 显示三条线名称。

7. Daily Risk Cards
   - 4 张小卡：
     - Blocked Requests
     - PII Detections
     - Business-Sensitive
     - Prompt Injections
   - 显示数值、delta 百分比、迷你 sparkline。
   - delta 计算方式：趋势数组前半段总和 vs 后半段总和。

8. Insight Detail Panel
   - 右侧 fixed 或 absolute 浮层。
   - 默认隐藏，用户 hover/click KPI 卡片、图表点、风险类别、use case、user、incident、governance item 时显示。
   - 内容：
     - 标题
     - Focus
     - Summary
     - Related Count
     - 详情条目列表
   - 鼠标离开后 220ms 隐藏；鼠标进入详情面板时保持显示。
   - 移动端可改为底部抽屉或普通块状详情区域。

9. Secondary Grid
   - 两列：
     - Guardrail Use Cases
     - High-Risk User Focus
   - Use Cases 卡片：
     - Sales And Contracts
     - HR And Recruiting
     - Engineering And Code
     - Privacy And Customer Data
     - Document Review
   - 每张卡显示 total、blocked、needs review。
   - High-Risk User Focus 显示用户排行榜：
     - username
     - Blocked n / Review n / Files n
     - total_events 分数

10. Extra Grid
   - 两列：
     - Weekly Trend
     - Governance Posture
   - Weekly Trend 展示每日 total scans、blocked、review。
   - Governance Posture 展示：
     - Scanner coverage
     - Configured providers
     - Sensitive audit logs
     - Reviewed uploads
     - High-risk documents

11. Management Actions + Incident Feed
   - 两列。
   - Management Actions 根据当前数据动态生成：
     - blocked_requests >= 3：Tighten coaching for repeat violations
     - business_sensitive_requests > 0：Add an approval lane for commercial content
     - confirmed_sensitive_sends > 0：Review confirmed sends in audit
     - configured_providers === 0：Finish provider setup
     - high_risk_files > 0：Investigate high-risk file uploads
     - 如果没有触发项：Controls look healthy
   - Incident Feed 卡片显示：
     - title
     - channel/status
     - summary
     - actor
     - created_at
   - severity 决定左边框颜色：
     - high 红
     - medium amber
     - low 绿

数据结构：
请先用 mock data 实现，后续再接 API。mock 数据结构应与下面一致：

type DashboardData = {
  total_requests: number;
  blocked_requests: number;
  review_required_requests: number;
  pii_requests: number;
  business_sensitive_requests: number;
  confirmed_sensitive_sends: number;
  active_users: number;
  trend: {
    label: string;
    total: number;
    blocked: number;
    needs_review: number;
  }[];
  request_windows: {
    key: "1h" | "6h" | "24h" | "7d" | "1m" | "3m" | "6m" | "1y";
    label: string;
    total: number;
    blocked: number;
    needs_review: number;
    risk_count: number;
    requests_per_minute: number;
    sparkline: number[];
  }[];
  use_cases: {
    key: string;
    title: string;
    description: string;
    total: number;
    blocked: number;
    review_needed: number;
  }[];
  top_risk_users: {
    username: string;
    total_events: number;
    blocked_events: number;
    review_events: number;
    file_uploads: number;
    latest_activity: string | null;
  }[];
  incidents: {
    channel: "chat" | "file" | "audit";
    severity: "high" | "medium" | "low";
    title: string;
    summary: string;
    actor: string;
    status: string;
    created_at: string | null;
  }[];
  governance: {
    active_scanners: number;
    total_scanners: number;
    configured_providers: number;
    audit_logs: number;
    uploaded_files: number;
    high_risk_files: number;
  };
  intervention_types: {
    key: string;
    label: string;
    count: number;
    description: string;
  }[];
  intervention_trend: {
    key: string;
    label: string;
    points: number[];
  }[];
};

type ScannerStatus = {
  id: string;
  name: string;
  enabled: boolean;
  available: boolean;
  active: boolean;
  detail: string;
};

组件拆分建议：
- DashboardPage
- DashboardHeader
- ScannerStatusGrid
- RiskPosturePanel
- MetricGrid
- MetricCard
- RiskIntelligencePanel
- DonutChart
- MiniSparkline
- LineTrendChart
- DailyRiskCards
- InsightDetailPanel
- UseCaseGrid
- RiskUserList
- GovernanceList
- ManagementActions
- IncidentFeed

样式要求：
- 主内容背景：浅灰蓝或继承现有页面背景。
- 卡片：白色或半透明白，1px 浅边框，8px 圆角。
- 关键风险模块使用深色面板。
- 主色：
  - cyan #0ea5e9
  - teal #14b8a6
  - green #10b981
  - amber #f59e0b
  - red #ef4444
  - indigo #6366f1
- 信息密度要高，dashboard 首屏尽量能看到 Header、Risk Posture、KPI、主图表区域。
- 不要使用大 hero，不要使用营销式插画。
- 所有文本不能溢出卡片；长文本用 ellipsis 或换行。
- 卡片 hover 可以轻微上移 1px，边框高亮。

响应式：
- 桌面：
  - KPI 8 列
  - primary grid 左 0.72fr，右 2.28fr
  - secondary/extra grid 两列
- 小于 1180px：
  - KPI 4 列
  - primary grid 一列
  - detail panel 宽度变为 calc(100vw - 36px)
- 小于 900px：
  - KPI 2 列
  - 所有 grid 一列
  - scanner grid 一列
  - risk posture 一列
- 小于 560px：
  - Daily Risk Cards 一列

验收标准：
1. 不修改左侧导航。
2. Dashboard 主内容完整显示上述模块。
3. 所有 mock 数据都能渲染。
4. KPI、图表点、风险类别、use case、user、incident、governance item 点击后都能更新 Insight Detail Panel。
5. 页面在桌面和移动宽度下无明显重叠、溢出。
6. 图表非空，颜色和 legend 一致。
7. 代码结构清晰，组件拆分合理，后续可以把 mock data 替换成 API。
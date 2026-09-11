import { useEffect, useRef, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Circle, Eye, FileWarning, ShieldAlert } from "lucide-react";
import { apiFetch } from "../../api/client";
import { formatDateTime } from "../../utils/format";

type RequestWindowKey = "1h" | "6h" | "24h" | "7d" | "1m" | "3m" | "6m" | "1y";

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
    key: RequestWindowKey;
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

type ConsoleScannersResponse = {
  scanners: ScannerStatus[];
  enabled_scanners: string[];
};

type Insight = {
  title: string;
  focus: string;
  summary: string;
  relatedCount: number;
  details: string[];
};

const riskColors: Record<string, string> = {
  prompt_injection: "#ef4444",
  pii_or_secret: "#a855f7",
  business_sensitive: "#f59e0b",
  source_code: "#0ea5e9",
  restricted_topic: "#14b8a6",
  document_risk: "#8b5cf6",
  manual_rejection: "#f43f5e",
  other: "#64748b",
};

type RiskCategoryDatum = {
  key: string;
  label: string;
  value: number;
  count: number;
  description: string;
};

export function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [scanners, setScanners] = useState<ScannerStatus[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedWindow, setSelectedWindow] = useState<RequestWindowKey>("24h");
  const [insight, setInsight] = useState<Insight | null>(null);
  const hideTimer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      apiFetch<DashboardData>("/api/console/dashboard"),
      apiFetch<ConsoleScannersResponse>("/api/console/scanners"),
    ])
      .then(([dashboardData, scannerData]) => {
        if (!alive) {
          return;
        }
        setDashboard(normalizeDashboardData(dashboardData));
        setScanners(mapDashboardScanners(scannerData.scanners));
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (!alive) {
          return;
        }
        setLoadError(error instanceof Error ? error.message : "Unable to load dashboard data.");
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loadError) {
    return (
      <div className="dashboard-panel">
        <p className="eyebrow">Dashboard unavailable</p>
        <h2>Unable to load AI Security Guardrail Dashboard</h2>
        <p className="muted">{loadError}</p>
      </div>
    );
  }

  if (!dashboard) {
    return <div className="screen-loader">Loading dashboard...</div>;
  }

  const selectedPosture = dashboard.request_windows.find((item) => item.key === selectedWindow) ?? dashboard.request_windows[0];

  const showInsight = (nextInsight: Insight) => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
    }
    setInsight(nextInsight);
  };

  const scheduleHide = () => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
    }
    hideTimer.current = window.setTimeout(() => setInsight(null), 220);
  };

  const holdPanel = () => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current);
    }
  };

  return (
    <div className="admin-dashboard">
      <DashboardHeader scanners={scanners} onInsight={showInsight} onLeave={scheduleHide} />
      <RiskPosturePanel
        selected={selectedPosture}
        windows={dashboard.request_windows}
        onSelect={setSelectedWindow}
        onInsight={showInsight}
        onLeave={scheduleHide}
      />
      <MetricGrid data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
      <section className="dashboard-primary-grid">
        <RiskIntelligencePanel data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
        <div className="dashboard-stack">
          <DailySecurityTrend data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
          <DailyRiskCards data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
        </div>
      </section>
      <section className="dashboard-secondary-grid">
        <UseCaseGrid data={dashboard.use_cases} onInsight={showInsight} onLeave={scheduleHide} />
        <RiskUserList users={dashboard.top_risk_users} onInsight={showInsight} onLeave={scheduleHide} />
      </section>
      <section className="dashboard-secondary-grid">
        <WeeklyTrend data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
        <GovernanceList data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
      </section>
      <section className="dashboard-secondary-grid">
        <ManagementActions data={dashboard} onInsight={showInsight} onLeave={scheduleHide} />
        <IncidentFeed incidents={dashboard.incidents} onInsight={showInsight} onLeave={scheduleHide} />
      </section>
      <InsightDetailPanel insight={insight} onEnter={holdPanel} onLeave={scheduleHide} />
    </div>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="workspace-header">
      <div>
        <p className="eyebrow">Admin</p>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>
      </div>
    </header>
  );
}

function DashboardHeader({ scanners, onInsight, onLeave }: { scanners: ScannerStatus[]; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  return (
    <header className="dashboard-header">
      <div className="dashboard-header-copy">
        <p className="eyebrow">Executive Oversight</p>
        <h1>AI Security Guardrail Dashboard</h1>
        <p className="muted">面向管理层的实时风险态势：请求量、拦截、复核、文档风险、高风险用户和审计证据集中呈现。</p>
      </div>
      <ScannerStatusGrid scanners={scanners} onInsight={onInsight} onLeave={onLeave} />
    </header>
  );
}

function ScannerStatusGrid({ scanners, onInsight, onLeave }: { scanners: ScannerStatus[]; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  return (
    <div className="scanner-status-grid" aria-label="Scanner statuses">
      {scanners.map((scanner) => {
        const status = getScannerStatus(scanner);
        return (
          <button
            key={scanner.id}
            className={`scanner-status-card ${status.toLowerCase()}`}
            onClick={() => onInsight(scannerInsight(scanner))}
            onMouseEnter={() => onInsight(scannerInsight(scanner))}
            onMouseLeave={onLeave}
          >
            <span>{scanner.name}</span>
            <strong><Circle size={9} fill="currentColor" />{status}</strong>
          </button>
        );
      })}
    </div>
  );
}

function RiskPosturePanel({
  selected,
  windows,
  onSelect,
  onInsight,
  onLeave,
}: {
  selected: DashboardData["request_windows"][number];
  windows: DashboardData["request_windows"];
  onSelect: (key: RequestWindowKey) => void;
  onInsight: (insight: Insight) => void;
  onLeave: () => void;
}) {
  const posture = getRiskPosture(selected);
  return (
    <section
      className={`risk-posture-panel ${posture.className}`}
      onMouseEnter={() => onInsight(windowInsight(selected))}
      onMouseLeave={onLeave}
    >
      <div className="posture-tabs" role="tablist" aria-label="Request time window">
        {windows.map((windowItem) => (
          <button
            key={windowItem.key}
            className={windowItem.key === selected.key ? "active" : ""}
            onClick={() => {
              onSelect(windowItem.key);
              onInsight(windowInsight(windowItem));
            }}
          >
            {windowItem.label}
          </button>
        ))}
      </div>
      <div className="posture-summary">
        <div>
          <span>{posture.label}</span>
          <strong>Monitoring {formatNumber(selected.total)} requests / {selected.requests_per_minute} req/min</strong>
        </div>
        <div>
          <span>Risk Signals</span>
          <strong>{formatNumber(selected.risk_count)} risks detected</strong>
        </div>
        <MiniSparkline points={selected.sparkline} color={posture.color} width={190} height={54} />
      </div>
    </section>
  );
}

function MetricGrid({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const metrics = [
    { label: "Requests", value: data.total_requests, help: "Total traffic processed by guardrails.", color: "#0ea5e9" },
    { label: "Blocked", value: data.blocked_requests, help: "Requests stopped before model delivery.", color: "#ef4444" },
    { label: "Needs Review", value: data.review_required_requests, help: "Requests waiting for human confirmation.", color: "#f59e0b" },
    { label: "PII Hits", value: data.pii_requests, help: "Privacy entities detected or masked.", color: "#a855f7" },
    { label: "Business Sensitive", value: data.business_sensitive_requests, help: "Commercially sensitive content matches.", color: "#f59e0b" },
    { label: "Confirmed Sends", value: data.confirmed_sensitive_sends, help: "Sensitive sends released after confirmation.", color: "#6366f1" },
    { label: "Active Users", value: data.active_users, help: "Distinct users with recent activity.", color: "#10b981" },
    { label: "High-risk Files", value: data.governance.high_risk_files, help: "Uploaded files requiring investigation.", color: "#f43f5e" },
  ];

  return (
    <section className="dashboard-metric-grid">
      {metrics.map((metric) => (
        <MetricCard
          key={metric.label}
          metric={metric}
          onInsight={onInsight}
          onLeave={onLeave}
        />
      ))}
    </section>
  );
}

function MetricCard({
  metric,
  onInsight,
  onLeave,
}: {
  metric: { label: string; value: number; help: string; color: string };
  onInsight: (insight: Insight) => void;
  onLeave: () => void;
}) {
  const insight = {
    title: metric.label,
    focus: "KPI Metric",
    summary: metric.help,
    relatedCount: metric.value,
    details: ["Compared against recent operating baseline.", "Click-through target can map to filtered logs when API is connected.", `Signal color: ${metric.color}`],
  };
  return (
    <button className="dashboard-metric-card" onClick={() => onInsight(insight)} onMouseEnter={() => onInsight(insight)} onMouseLeave={onLeave}>
      <span className="metric-dot" style={{ backgroundColor: metric.color }} />
      <span>{metric.label}</span>
      <strong>{formatNumber(metric.value)}</strong>
      <em>{metric.help}</em>
    </button>
  );
}

function RiskIntelligencePanel({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const riskCategoryData = buildRiskCategoryData(data);
  return (
    <section className="risk-intelligence-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Risk Intelligence</p>
          <h2>Top categories and 24h movement</h2>
        </div>
        <ShieldAlert size={22} />
      </div>
      <div className="risk-intelligence-grid">
        <div>
          <h3>Top Risk Categories</h3>
          <DonutChart data={riskCategoryData} onInsight={onInsight} onLeave={onLeave} />
          <div className="risk-category-list">
            {riskCategoryData.map((item) => (
              <button
                key={item.key}
                onClick={() => onInsight(riskCategoryInsight(item))}
                onMouseEnter={() => onInsight(riskCategoryInsight(item))}
                onMouseLeave={onLeave}
              >
                <span style={{ backgroundColor: riskColors[item.key] ?? riskColors.other }} />
                <strong>{item.label}</strong>
                <em>{item.value}%</em>
              </button>
            ))}
          </div>
        </div>
        <div>
          <h3>Risk Trend (Last 24h)</h3>
          <div className="multi-sparkline-list">
            {data.intervention_trend.map((series) => (
              <button
                key={series.key}
                onClick={() => onInsight(interventionTrendInsight(series))}
                onMouseEnter={() => onInsight(interventionTrendInsight(series))}
                onMouseLeave={onLeave}
              >
                <span>{series.label}</span>
                <MiniSparkline points={series.points} color={seriesColor(series.key)} width={210} height={40} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function DonutChart({
  data,
  onInsight,
  onLeave,
}: {
  data: RiskCategoryDatum[];
  onInsight: (insight: Insight) => void;
  onLeave: () => void;
}) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <svg className="donut-chart" viewBox="0 0 120 120" role="img" aria-label="Risk category donut chart">
      <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="18" />
      {data.map((item) => {
        const dash = (item.value / 100) * circumference;
        const segment = (
          <circle
            key={item.key}
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke={riskColors[item.key] ?? riskColors.other}
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeDashoffset={-offset}
            strokeLinecap="butt"
            strokeWidth="18"
            onClick={() => onInsight(riskCategoryInsight(item))}
            onMouseEnter={() => onInsight(riskCategoryInsight(item))}
            onMouseLeave={onLeave}
          />
        );
        offset += dash;
        return segment;
      })}
      <text x="60" y="56" textAnchor="middle">100%</text>
      <text x="60" y="72" textAnchor="middle">risk mix</text>
    </svg>
  );
}

function DailySecurityTrend({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const series = [
    { key: "total", label: "Requests", color: "#0ea5e9", values: data.trend.map((point) => point.total) },
    { key: "blocked", label: "Blocked", color: "#ef4444", values: data.trend.map((point) => point.blocked) },
    { key: "needs_review", label: "Needs Review", color: "#f59e0b", values: data.trend.map((point) => point.needs_review) },
  ];
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Daily Security Trend</p>
          <h2>Requests, blocks, and reviews by day</h2>
        </div>
        <Activity size={22} />
      </div>
      <LineTrendChart trend={data.trend} series={series} onInsight={onInsight} onLeave={onLeave} />
      <div className="chart-legend">
        {series.map((item) => (
          <button
            key={item.key}
            onClick={() => onInsight(lineSeriesInsight(item))}
            onMouseEnter={() => onInsight(lineSeriesInsight(item))}
            onMouseLeave={onLeave}
          >
            <span style={{ backgroundColor: item.color }} />
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function LineTrendChart({
  trend,
  series,
  onInsight,
  onLeave,
}: {
  trend: DashboardData["trend"];
  series: { key: string; label: string; color: string; values: number[] }[];
  onInsight: (insight: Insight) => void;
  onLeave: () => void;
}) {
  const width = 720;
  const height = 220;
  const padding = 28;
  const max = Math.max(1, ...series.flatMap((item) => item.values));
  const xFor = (index: number) => padding + (index * (width - padding * 2)) / (trend.length - 1);
  const yFor = (value: number) => height - padding - (value / max) * (height - padding * 2);

  return (
    <svg className="line-trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Fourteen day request trend">
      {[0, 1, 2, 3].map((tick) => (
        <line key={tick} x1={padding} x2={width - padding} y1={padding + tick * 45} y2={padding + tick * 45} />
      ))}
      {series.map((item) => (
        <path
          key={item.key}
          d={item.values.map((value, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(value)}`).join(" ")}
          fill="none"
          stroke={item.color}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={item.key === "total" ? 3 : 2.4}
        />
      ))}
      {trend.map((point, index) => (
        <g key={point.label}>
          {series.map((item) => (
            <circle
              key={item.key}
              cx={xFor(index)}
              cy={yFor(item.values[index])}
              r={4.5}
              fill={item.color}
              onClick={() => onInsight(linePointInsight(point, item))}
              onMouseEnter={() => onInsight(linePointInsight(point, item))}
              onMouseLeave={onLeave}
            />
          ))}
          {index % 2 === 0 && <text x={xFor(index)} y={height - 6} textAnchor="middle">{point.label.slice(4)}</text>}
        </g>
      ))}
    </svg>
  );
}

function DailyRiskCards({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const trendByKey = new Map(data.intervention_trend.map((series) => [series.key, series.points]));
  const blockedPoints = data.trend.map((point) => point.blocked);
  const piiPoints = trendByKey.get("pii_or_secret") ?? trendByKey.get("pii") ?? zeroLike(blockedPoints);
  const businessPoints = trendByKey.get("business_sensitive") ?? trendByKey.get("business") ?? zeroLike(blockedPoints);
  const promptPoints = trendByKey.get("prompt_injection") ?? trendByKey.get("prompt") ?? zeroLike(blockedPoints);
  const promptCount = data.intervention_types.find((item) => item.key === "prompt_injection")?.count ?? promptPoints.reduce((sum, value) => sum + value, 0);
  const cards = [
    { label: "Blocked Requests", value: data.blocked_requests, points: blockedPoints, color: "#ef4444" },
    { label: "PII Detections", value: data.pii_requests, points: piiPoints, color: "#a855f7" },
    { label: "Business-Sensitive", value: data.business_sensitive_requests, points: businessPoints, color: "#f59e0b" },
    { label: "Prompt Injections", value: promptCount, points: promptPoints, color: "#ef4444" },
  ];

  return (
    <section className="daily-risk-grid">
      {cards.map((card) => (
        <button
          key={card.label}
          className="daily-risk-card"
          onClick={() => onInsight(dailyRiskInsight(card))}
          onMouseEnter={() => onInsight(dailyRiskInsight(card))}
          onMouseLeave={onLeave}
        >
          <span>{card.label}</span>
          <strong>{formatNumber(card.value)}</strong>
          <em className={deltaPercent(card.points) >= 0 ? "delta-up" : "delta-down"}>{deltaPercent(card.points) >= 0 ? "+" : ""}{deltaPercent(card.points)}%</em>
          <MiniSparkline points={card.points} color={card.color} width={142} height={38} />
        </button>
      ))}
    </section>
  );
}

function UseCaseGrid({ data, onInsight, onLeave }: { data: DashboardData["use_cases"]; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Guardrail Use Cases</p>
          <h2>Business workflows under protection</h2>
        </div>
        <CheckCircle2 size={22} />
      </div>
      <div className="use-case-grid">
        {data.map((item) => (
          <button
            key={item.key}
            className="use-case-card"
            onClick={() => onInsight(useCaseInsight(item))}
            onMouseEnter={() => onInsight(useCaseInsight(item))}
            onMouseLeave={onLeave}
          >
            <strong>{item.title}</strong>
            <span>{item.description}</span>
            <dl>
              <dt>Total</dt><dd>{formatNumber(item.total)}</dd>
              <dt>Blocked</dt><dd>{item.blocked}</dd>
              <dt>Review</dt><dd>{item.review_needed}</dd>
            </dl>
          </button>
        ))}
      </div>
    </section>
  );
}

function RiskUserList({ users, onInsight, onLeave }: { users: DashboardData["top_risk_users"]; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">High-Risk User Focus</p>
          <h2>Ranked by event concentration</h2>
        </div>
        <Eye size={22} />
      </div>
      <div className="risk-user-list">
        {users.map((user, index) => (
          <button
            key={user.username}
            onClick={() => onInsight(userInsight(user))}
            onMouseEnter={() => onInsight(userInsight(user))}
            onMouseLeave={onLeave}
          >
            <span className="rank">#{index + 1}</span>
            <strong>{user.username}</strong>
            <span>Blocked {user.blocked_events} / Review {user.review_events} / Files {user.file_uploads}</span>
            <em>{user.total_events}</em>
          </button>
        ))}
      </div>
    </section>
  );
}

function WeeklyTrend({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const week = data.trend.slice(-7);
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Weekly Trend</p>
          <h2>Daily total scans, blocked, review</h2>
        </div>
      </div>
      <div className="weekly-bars">
        {week.map((day) => (
          <button
            key={day.label}
            onClick={() => onInsight(weeklyInsight(day))}
            onMouseEnter={() => onInsight(weeklyInsight(day))}
            onMouseLeave={onLeave}
          >
            <div>
              <span style={{ height: `${Math.max(18, day.total / 22)}px` }} />
              <span style={{ height: `${Math.max(10, day.blocked * 2.2)}px` }} />
              <span style={{ height: `${Math.max(10, day.needs_review * 1.5)}px` }} />
            </div>
            <strong>{day.label.slice(4)}</strong>
          </button>
        ))}
      </div>
    </section>
  );
}

function GovernanceList({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const items = [
    { label: "Scanner coverage", value: `${data.governance.active_scanners}/${data.governance.total_scanners}`, count: data.governance.active_scanners, summary: "Enabled and available scanners protecting the gateway." },
    { label: "Configured providers", value: data.governance.configured_providers, count: data.governance.configured_providers, summary: "Model providers configured for controlled access." },
    { label: "Prompt audit logs", value: formatNumber(data.governance.audit_logs), count: data.governance.audit_logs, summary: "All prompt decisions available for review." },
    { label: "Reviewed uploads", value: formatNumber(data.governance.uploaded_files), count: data.governance.uploaded_files, summary: "Files processed by document review controls." },
    { label: "High-risk documents", value: data.governance.high_risk_files, count: data.governance.high_risk_files, summary: "Files carrying elevated policy or data leakage risk." },
  ];

  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Governance Posture</p>
          <h2>Control coverage and audit readiness</h2>
        </div>
      </div>
      <div className="governance-list">
        {items.map((item) => (
          <button
            key={item.label}
            onClick={() => onInsight(governanceInsight(item))}
            onMouseEnter={() => onInsight(governanceInsight(item))}
            onMouseLeave={onLeave}
          >
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </button>
        ))}
      </div>
    </section>
  );
}

function ManagementActions({ data, onInsight, onLeave }: { data: DashboardData; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  const actions = buildManagementActions(data);
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Management Actions</p>
          <h2>Recommended next controls</h2>
        </div>
        <AlertTriangle size={22} />
      </div>
      <div className="action-list">
        {actions.map((action) => (
          <button
            key={action.title}
            onClick={() => onInsight(action)}
            onMouseEnter={() => onInsight(action)}
            onMouseLeave={onLeave}
          >
            <strong>{action.title}</strong>
            <span>{action.summary}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function IncidentFeed({ incidents, onInsight, onLeave }: { incidents: DashboardData["incidents"]; onInsight: (insight: Insight) => void; onLeave: () => void }) {
  return (
    <section className="dashboard-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Incident Feed</p>
          <h2>Latest audit evidence</h2>
        </div>
        <FileWarning size={22} />
      </div>
      <div className="incident-feed">
        {incidents.map((incident) => (
          <button
            key={`${incident.title}-${incident.created_at}`}
            className={`severity-${incident.severity}`}
            onClick={() => onInsight(incidentInsight(incident))}
            onMouseEnter={() => onInsight(incidentInsight(incident))}
            onMouseLeave={onLeave}
          >
            <span>{incident.channel} / {incident.status}</span>
            <strong>{incident.title}</strong>
            <em>{incident.summary}</em>
            <small>{incident.actor} · {formatDateTime(incident.created_at)}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function InsightDetailPanel({ insight, onEnter, onLeave }: { insight: Insight | null; onEnter: () => void; onLeave: () => void }) {
  if (!insight) {
    return null;
  }

  return (
    <aside className="insight-detail-panel" onMouseEnter={onEnter} onMouseLeave={onLeave}>
      <p className="eyebrow">Insight Detail</p>
      <h2>{insight.title}</h2>
      <dl>
        <dt>Focus</dt>
        <dd>{insight.focus}</dd>
        <dt>Summary</dt>
        <dd>{insight.summary}</dd>
        <dt>Related Count</dt>
        <dd>{formatNumber(insight.relatedCount)}</dd>
      </dl>
      <ul>
        {insight.details.map((detail) => (
          <li key={detail}>{detail}</li>
        ))}
      </ul>
    </aside>
  );
}

function MiniSparkline({ points, color, width, height }: { points: number[]; color: string; width: number; height: number }) {
  const safePoints = points.length > 1 ? points : [points[0] ?? 0, points[0] ?? 0];
  const min = Math.min(...safePoints);
  const max = Math.max(...safePoints);
  const spread = max - min || 1;
  const path = safePoints
    .map((point, index) => {
      const x = (index * (width - 8)) / (safePoints.length - 1) + 4;
      const y = height - 5 - ((point - min) / spread) * (height - 10);
      return `${index === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");

  return (
    <svg className="mini-sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Sparkline">
      <path d={path} fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" />
    </svg>
  );
}

function normalizeDashboardData(data: DashboardData): DashboardData {
  const trend = data.trend.length > 0 ? data.trend : buildEmptyTrend();
  const requestWindows = data.request_windows.length > 0 ? data.request_windows : buildEmptyRequestWindows();
  return {
    ...data,
    trend,
    request_windows: requestWindows.map((windowItem) => ({
      ...windowItem,
      sparkline: windowItem.sparkline.length > 1 ? windowItem.sparkline : [0, 0],
    })),
    intervention_trend: data.intervention_trend.map((series) => ({
      ...series,
      points: series.points.length > 1 ? series.points : [0, 0],
    })),
  };
}

function buildEmptyTrend() {
  return Array.from({ length: 14 }, (_, index) => ({
    label: `D-${13 - index}`,
    total: 0,
    blocked: 0,
    needs_review: 0,
  }));
}

function buildEmptyRequestWindows(): DashboardData["request_windows"] {
  const windows: Array<{ key: RequestWindowKey; label: string }> = [
    { key: "1h", label: "1H" },
    { key: "6h", label: "6H" },
    { key: "24h", label: "24H" },
    { key: "7d", label: "7D" },
    { key: "1m", label: "1M" },
    { key: "3m", label: "3M" },
    { key: "6m", label: "6M" },
    { key: "1y", label: "1Y" },
  ];
  return windows.map((item) => ({
    ...item,
    total: 0,
    blocked: 0,
    needs_review: 0,
    risk_count: 0,
    requests_per_minute: 0,
    sparkline: [0, 0],
  }));
}

function mapDashboardScanners(scanners: ScannerStatus[]): ScannerStatus[] {
  const sourceScanner = scanners.find((scanner) => scanner.id === "bancode");
  const promptScanner = scanners.find((scanner) => scanner.id === "prompt_injection");
  const ethicsScanner = scanners.find((scanner) => scanner.id === "ban_topics");
  const privacyScanner = scanners.find((scanner) => scanner.id === "privacy_filter");
  const businessScanner = scanners.find((scanner) => scanner.id === "business_sensitive");
  const customScanner = scanners.find((scanner) => scanner.id === "custom_regex");
  return [
    remapScanner(sourceScanner, "source_code", "Source Code Scanner"),
    remapScanner(promptScanner, "prompt_injection", "Prompt Injection Scanner"),
    remapScanner(ethicsScanner, "ai_ethical", "AI Ethical Scanner"),
    remapScanner(privacyScanner, "privacy_information", "Privacy Information Scanner"),
    remapScanner(businessScanner, "business_sensitive", "Business Sensitive Scanner"),
    remapScanner(customScanner, "custom_rule", "Custom Rule Match"),
  ];
}

function remapScanner(scanner: ScannerStatus | undefined, id: string, name: string): ScannerStatus {
  return {
    id,
    name,
    enabled: scanner?.enabled ?? false,
    available: scanner?.available ?? false,
    active: scanner?.active ?? false,
    detail: scanner?.detail ?? "Scanner state is not available from the backend.",
  };
}

function buildRiskCategoryData(data: DashboardData): RiskCategoryDatum[] {
  const total = data.intervention_types.reduce((sum, item) => sum + item.count, 0);
  if (total <= 0) {
    return [{ key: "other", label: "Other", value: 100, count: 0, description: "No risk categories have been recorded yet." }];
  }
  return data.intervention_types.map((item) => ({
    key: item.key,
    label: item.label,
    value: Math.max(1, Math.round((item.count / total) * 100)),
    count: item.count,
    description: item.description,
  }));
}

function zeroLike(points: number[]) {
  return Array.from({ length: Math.max(points.length, 2) }, () => 0);
}

function getScannerStatus(scanner: ScannerStatus) {
  if (!scanner.enabled) {
    return "Disabled";
  }
  if (!scanner.available) {
    return "Unavailable";
  }
  return scanner.active ? "Active" : "Disabled";
}

function getRiskPosture(windowItem: DashboardData["request_windows"][number]) {
  if (windowItem.blocked > 0 || windowItem.risk_count >= 3) {
    return { label: "Elevated Risk", color: "#ef4444", className: "elevated" };
  }
  if (windowItem.needs_review > 0 || windowItem.risk_count > 0) {
    return { label: "Review Watch", color: "#f59e0b", className: "watch" };
  }
  return { label: "Nominal", color: "#10b981", className: "nominal" };
}

function deltaPercent(points: number[]) {
  const midpoint = Math.floor(points.length / 2);
  const previous = points.slice(0, midpoint).reduce((sum, point) => sum + point, 0);
  const current = points.slice(midpoint).reduce((sum, point) => sum + point, 0);
  return Math.round(((current - previous) / Math.max(previous, 1)) * 100);
}

function seriesColor(key: string) {
  if (key === "prompt_injection" || key === "blocked") {
    return "#ef4444";
  }
  if (key === "pii_or_secret" || key === "pii") {
    return "#a855f7";
  }
  if (key === "business_sensitive" || key === "business") {
    return "#f59e0b";
  }
  return riskColors[key] ?? "#14b8a6";
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function scannerInsight(scanner: ScannerStatus): Insight {
  return {
    title: scanner.name,
    focus: getScannerStatus(scanner),
    summary: scanner.detail,
    relatedCount: scanner.active ? 1 : 0,
    details: [`Enabled: ${scanner.enabled ? "yes" : "no"}`, `Available: ${scanner.available ? "yes" : "no"}`, `Active: ${scanner.active ? "yes" : "no"}`],
  };
}

function windowInsight(windowItem: DashboardData["request_windows"][number]): Insight {
  const posture = getRiskPosture(windowItem);
  return {
    title: `${windowItem.label} Request Posture`,
    focus: posture.label,
    summary: `${formatNumber(windowItem.total)} requests at ${windowItem.requests_per_minute} req/min.`,
    relatedCount: windowItem.risk_count,
    details: [`Blocked requests: ${windowItem.blocked}`, `Needs review: ${windowItem.needs_review}`, `Risk threshold result: ${posture.label}`],
  };
}

function riskCategoryInsight(item: RiskCategoryDatum): Insight {
  return {
    title: item.label,
    focus: "Risk Category",
    summary: `${item.value}% of current risk mix is attributed to ${item.label.toLowerCase()}.`,
    relatedCount: item.count,
    details: [item.description, "Use this to prioritize scanner tuning and manager coaching.", `Color: ${riskColors[item.key] ?? riskColors.other}`],
  };
}

function interventionTrendInsight(series: DashboardData["intervention_trend"][number]): Insight {
  return {
    title: series.label,
    focus: "24h Risk Trend",
    summary: `${series.label} movement across the most recent operating window.`,
    relatedCount: series.points.reduce((sum, value) => sum + value, 0),
    details: [`Peak interval: ${Math.max(...series.points)}`, `Lowest interval: ${Math.min(...series.points)}`, `Delta: ${deltaPercent(series.points)}%`],
  };
}

function lineSeriesInsight(item: { label: string; values: number[] }): Insight {
  return {
    title: item.label,
    focus: "14-day Series",
    summary: `${item.label} across the last 14 daily operating periods.`,
    relatedCount: item.values.reduce((sum, value) => sum + value, 0),
    details: [`Peak day value: ${Math.max(...item.values)}`, `Lowest day value: ${Math.min(...item.values)}`, `Recent delta: ${deltaPercent(item.values)}%`],
  };
}

function linePointInsight(point: DashboardData["trend"][number], item: { label: string; values: number[]; key: string }): Insight {
  const value = item.key === "total" ? point.total : item.key === "blocked" ? point.blocked : point.needs_review;
  return {
    title: `${point.label} ${item.label}`,
    focus: "Daily Point",
    summary: `${item.label} registered ${formatNumber(value)} events on ${point.label}.`,
    relatedCount: value,
    details: [`Requests: ${point.total}`, `Blocked: ${point.blocked}`, `Needs review: ${point.needs_review}`],
  };
}

function dailyRiskInsight(card: { label: string; value: number; points: number[] }): Insight {
  return {
    title: card.label,
    focus: "Daily Risk Card",
    summary: `${card.label} current total is ${formatNumber(card.value)} with recent movement of ${deltaPercent(card.points)}%.`,
    relatedCount: card.value,
    details: [`First half total: ${card.points.slice(0, Math.floor(card.points.length / 2)).reduce((sum, value) => sum + value, 0)}`, `Second half total: ${card.points.slice(Math.floor(card.points.length / 2)).reduce((sum, value) => sum + value, 0)}`, "Use for executive trend scanning."],
  };
}

function useCaseInsight(item: DashboardData["use_cases"][number]): Insight {
  return {
    title: item.title,
    focus: "Guardrail Use Case",
    summary: item.description,
    relatedCount: item.total,
    details: [`Blocked: ${item.blocked}`, `Needs review: ${item.review_needed}`, `Review rate: ${Math.round((item.review_needed / item.total) * 1000) / 10}%`],
  };
}

function userInsight(user: DashboardData["top_risk_users"][number]): Insight {
  return {
    title: user.username,
    focus: "High-Risk User",
    summary: `${user.username} has ${user.total_events} risk-related events in the current window.`,
    relatedCount: user.total_events,
    details: [`Blocked ${user.blocked_events} / Review ${user.review_events} / Files ${user.file_uploads}`, `Latest activity: ${formatDateTime(user.latest_activity)}`, "Candidate for targeted coaching or workflow review."],
  };
}

function weeklyInsight(day: DashboardData["trend"][number]): Insight {
  return {
    title: day.label,
    focus: "Weekly Trend Day",
    summary: `${formatNumber(day.total)} total scans with ${day.blocked} blocks and ${day.needs_review} reviews.`,
    relatedCount: day.total,
    details: [`Blocked ratio: ${Math.round((day.blocked / day.total) * 1000) / 10}%`, `Review ratio: ${Math.round((day.needs_review / day.total) * 1000) / 10}%`, "Daily bar selection can map to audit logs."],
  };
}

function governanceInsight(item: { label: string; summary: string; count: number; value: string | number }): Insight {
  return {
    title: item.label,
    focus: "Governance Posture",
    summary: item.summary,
    relatedCount: item.count,
    details: [`Current value: ${item.value}`, "Track this item in executive control reviews.", "Connect API data to make the posture live."],
  };
}

function buildManagementActions(data: DashboardData): Insight[] {
  const actions: Insight[] = [];
  if (data.blocked_requests >= 3) {
    actions.push({ title: "Tighten coaching for repeat violations", focus: "Management Action", summary: "Blocked activity is above the executive review threshold.", relatedCount: data.blocked_requests, details: ["Identify repeated actors.", "Publish short policy reminders.", "Review blocked prompt samples with team owners."] });
  }
  if (data.business_sensitive_requests > 0) {
    actions.push({ title: "Add an approval lane for commercial content", focus: "Management Action", summary: "Business-sensitive content is appearing in day-to-day workflows.", relatedCount: data.business_sensitive_requests, details: ["Route pricing and contract prompts to deal desk.", "Require manager confirmation for external sends.", "Audit sampled approvals weekly."] });
  }
  if (data.confirmed_sensitive_sends > 0) {
    actions.push({ title: "Review confirmed sends in audit", focus: "Management Action", summary: "Sensitive sends were released after user confirmation.", relatedCount: data.confirmed_sensitive_sends, details: ["Verify approvals match policy.", "Check masking quality.", "Escalate repeat confirmations."] });
  }
  if (data.governance.configured_providers === 0) {
    actions.push({ title: "Finish provider setup", focus: "Management Action", summary: "No configured providers are available for controlled access.", relatedCount: 0, details: ["Configure at least one provider.", "Validate model access.", "Confirm audit logging before launch."] });
  }
  if (data.governance.high_risk_files > 0) {
    actions.push({ title: "Investigate high-risk file uploads", focus: "Management Action", summary: "Uploaded documents have been classified as elevated risk.", relatedCount: data.governance.high_risk_files, details: ["Review documents by owner.", "Confirm document retention requirements.", "Tune file review scanner categories."] });
  }
  return actions.length > 0 ? actions : [{ title: "Controls look healthy", focus: "Management Action", summary: "No immediate management action thresholds are triggered.", relatedCount: 0, details: ["Continue monitoring.", "Review weekly governance posture.", "Keep scanner coverage current."] }];
}

function incidentInsight(incident: DashboardData["incidents"][number]): Insight {
  return {
    title: incident.title,
    focus: `${incident.severity.toUpperCase()} / ${incident.channel}`,
    summary: incident.summary,
    relatedCount: 1,
    details: [`Actor: ${incident.actor}`, `Status: ${incident.status}`, `Created: ${formatDateTime(incident.created_at)}`],
  };
}

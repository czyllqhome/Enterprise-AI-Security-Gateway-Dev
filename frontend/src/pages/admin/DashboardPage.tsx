import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import type { Dashboard } from "../../api/types";
import { formatDateTime } from "../../utils/format";

export function DashboardPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);

  useEffect(() => {
    apiFetch<Dashboard>("/api/console/dashboard").then(setDashboard);
  }, []);

  if (!dashboard) {
    return <div className="screen-loader">Loading dashboard...</div>;
  }

  return (
    <>
      <PageTitle title="Dashboard" subtitle="管理员安全态势总览" />
      <section className="metric-grid">
        <Metric label="总请求" value={dashboard.total_requests} />
        <Metric label="拦截" value={dashboard.blocked_requests} />
        <Metric label="待确认" value={dashboard.review_required_requests} />
        <Metric label="PII 命中" value={dashboard.pii_requests} />
        <Metric label="商务敏感" value={dashboard.business_sensitive_requests} />
        <Metric label="活跃用户" value={dashboard.active_users} />
      </section>
      <section className="two-column">
        <div className="panel">
          <h2>风险趋势</h2>
          <div className="trend-list">
            {dashboard.trend.map((point) => (
              <div key={point.label}>
                <span>{point.label}</span>
                <strong>{point.total}</strong>
                <em>blocked {point.blocked} / review {point.needs_review}</em>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h2>治理快照</h2>
          <dl className="detail-list">
            <dt>Scanners</dt><dd>{dashboard.governance.active_scanners}/{dashboard.governance.total_scanners}</dd>
            <dt>Providers</dt><dd>{dashboard.governance.configured_providers}</dd>
            <dt>Audit logs</dt><dd>{dashboard.governance.audit_logs}</dd>
          </dl>
        </div>
      </section>
      <section className="panel">
        <h2>最近安全事件</h2>
        <div className="table-like">
          {dashboard.incidents.map((incident, index) => (
            <div key={`${incident.title}-${index}`} className="table-row">
              <span>{incident.title}</span>
              <span>{incident.actor}</span>
              <span>{incident.status}</span>
              <span>{formatDateTime(incident.created_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </>
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

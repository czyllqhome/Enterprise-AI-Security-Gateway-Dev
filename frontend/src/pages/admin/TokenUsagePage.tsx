import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Gauge, RefreshCw } from "lucide-react";
import { apiFetch } from "../../api/client";
import type { TokenUsageMonitoring, TokenUsageUser } from "../../api/types";
import { formatDateTime } from "../../utils/format";
import { PageTitle } from "./DashboardPage";

const numberFormatter = new Intl.NumberFormat("en-US");

export function TokenUsagePage() {
  const [data, setData] = useState<TokenUsageMonitoring | null>(null);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    loadUsage();
  }, []);

  async function loadUsage() {
    setStatus("");
    try {
      setData(await apiFetch<TokenUsageMonitoring>("/api/console/token-usage"));
      setStatus("Token usage refreshed.");
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "Unable to load token usage.");
    }
  }

  const visibleUsers = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    if (!data || !keyword) {
      return data?.users || [];
    }
    return data.users.filter((user) => (
      user.username.toLowerCase().includes(keyword) ||
      user.primary_provider.toLowerCase().includes(keyword) ||
      user.primary_model.toLowerCase().includes(keyword)
    ));
  }, [data, filter]);

  if (!data) {
    return (
      <>
        <PageTitle title="Token Usage" subtitle="Monitor per-user token consumption and prompt size thresholds." />
        <section className="panel">Loading token usage...</section>
      </>
    );
  }

  const topUser = data.users[0];

  return (
    <>
      <PageTitle title="Token Usage" subtitle="Monitor each user's estimated token consumption with a TokenLimit-style threshold." />
      <section className="token-usage-shell">
        <div className="token-summary-grid">
          <TokenMetric label="Total Tokens" value={data.total_tokens} detail={`${formatNumber(data.total_requests)} scanned requests`} />
          <TokenMetric label="Input Tokens" value={data.input_tokens} detail={`${data.encoding_name} tokenizer`} />
          <TokenMetric label="Output Tokens" value={data.output_tokens} detail="Assistant responses captured on confirmed sends" />
          <TokenMetric label="Limit Events" value={data.over_limit_events} detail={`${formatNumber(data.token_limit)} token prompt limit`} tone={data.over_limit_events ? "limit" : "normal"} />
        </div>

        <div className="token-main-grid">
          <section className="panel token-trend-panel">
            <div className="panel-title-row">
              <div>
                <p className="eyebrow">14 Day Usage</p>
                <h2>Input and output token trend</h2>
              </div>
              <button className="icon-btn" onClick={loadUsage} title="Refresh token usage">
                <RefreshCw size={17} />
              </button>
            </div>
            <TokenTrend data={data.trend} />
          </section>

          <section className="panel token-limit-panel">
            <p className="eyebrow">TokenLimit Guard</p>
            <h2>Prompt size posture</h2>
            {topUser ? (
              <UserLimitFocus user={topUser} tokenLimit={data.token_limit} />
            ) : (
              <p className="empty-state">No usage records yet.</p>
            )}
          </section>
        </div>

        <section className="panel">
          <div className="token-table-toolbar">
            <div>
              <p className="eyebrow">Users</p>
              <h2>Per-user token usage</h2>
            </div>
            <input className="search-input token-search" placeholder="Filter by user, provider, or model" value={filter} onChange={(event) => setFilter(event.target.value)} />
          </div>
          <div className="token-usage-table">
            {visibleUsers.map((user) => (
              <UserUsageRow key={user.username} user={user} tokenLimit={data.token_limit} />
            ))}
            {!visibleUsers.length ? <p className="empty-state">No matching users.</p> : null}
          </div>
        </section>
      </section>
      <div className="status-line">{status}</div>
    </>
  );
}

function TokenMetric({ label, value, detail, tone = "normal" }: { label: string; value: number; detail: string; tone?: string }) {
  return (
    <article className={`metric-card token-metric ${tone}`}>
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
      <em>{detail}</em>
    </article>
  );
}

function TokenTrend({ data }: { data: TokenUsageMonitoring["trend"] }) {
  const maxValue = Math.max(...data.map((point) => point.total_tokens), 1);
  return (
    <div className="token-trend-bars">
      {data.map((point) => {
        const inputHeight = Math.max((point.input_tokens / maxValue) * 100, point.input_tokens ? 6 : 0);
        const outputHeight = Math.max((point.output_tokens / maxValue) * 100, point.output_tokens ? 6 : 0);
        return (
          <div className="token-trend-day" key={point.label} title={`${point.label}: ${formatNumber(point.total_tokens)} tokens`}>
            <div>
              <span style={{ height: `${inputHeight}%` }} />
              <span style={{ height: `${outputHeight}%` }} />
            </div>
            <strong>{point.label}</strong>
          </div>
        );
      })}
    </div>
  );
}

function UserLimitFocus({ user, tokenLimit }: { user: TokenUsageUser; tokenLimit: number }) {
  return (
    <div className={`token-focus-card ${user.risk_level}`}>
      <div className="token-gauge">
        <Gauge size={28} />
        <strong>{user.utilization_percent}%</strong>
      </div>
      <div>
        <strong>{user.username}</strong>
        <span>{formatNumber(user.max_input_tokens)} / {formatNumber(tokenLimit)} max input tokens</span>
        <p>{user.over_limit_events ? "This user has prompts at or above the configured token limit." : "Largest prompt remains below the current token limit."}</p>
      </div>
    </div>
  );
}

function UserUsageRow({ user, tokenLimit }: { user: TokenUsageUser; tokenLimit: number }) {
  return (
    <article className={`token-user-row ${user.risk_level}`}>
      <div>
        <strong>{user.username}</strong>
        <small>{user.primary_provider} / {user.primary_model}</small>
      </div>
      <div>
        <span>Total</span>
        <strong>{formatNumber(user.total_tokens)}</strong>
      </div>
      <div>
        <span>Input / Output</span>
        <strong>{formatNumber(user.input_tokens)} / {formatNumber(user.output_tokens)}</strong>
      </div>
      <div>
        <span>Requests</span>
        <strong>{formatNumber(user.request_count)}</strong>
      </div>
      <div>
        <span>Max Prompt</span>
        <strong>{formatNumber(user.max_input_tokens)} / {formatNumber(tokenLimit)}</strong>
      </div>
      <div className="token-risk-cell">
        {user.over_limit_events ? <AlertTriangle size={16} /> : null}
        <span>{riskLabel(user)}</span>
        <small>{formatDateTime(user.latest_activity)}</small>
      </div>
    </article>
  );
}

function riskLabel(user: TokenUsageUser) {
  if (user.risk_level === "limit") {
    return `${user.over_limit_events || 1} limit hit${user.over_limit_events === 1 ? "" : "s"}`;
  }
  if (user.risk_level === "watch") {
    return "Watch";
  }
  return "Normal";
}

function formatNumber(value: number) {
  return numberFormatter.format(value);
}

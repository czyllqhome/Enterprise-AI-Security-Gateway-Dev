import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api/client";
import type { LogEntry } from "../../api/types";
import { formatDateTime } from "../../utils/format";
import { PageTitle } from "./DashboardPage";

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [keywordFilter, setKeywordFilter] = useState("");
  const [decisionFilter, setDecisionFilter] = useState<"" | LogEntry["decision"]>("");

  useEffect(() => {
    let active = true;
    const query = decisionFilter ? `?decision=${decisionFilter}` : "";
    apiFetch<LogEntry[]>(`/api/logs${query}`).then((items) => {
      if (active) {
        setLogs(items);
      }
    });
    return () => {
      active = false;
    };
  }, [decisionFilter]);

  const visibleLogs = useMemo(() => {
    const keyword = keywordFilter.trim().toLowerCase();
    if (!keyword) {
      return logs;
    }
    return logs.filter((log) => (
      log.username.toLowerCase().includes(keyword) ||
      log.sanitized_content.toLowerCase().includes(keyword) ||
      (log.detected_entity_types || []).join(" ").toLowerCase().includes(keyword)
    ));
  }, [logs, keywordFilter]);

  const decisionLabels: Record<LogEntry["decision"], string> = {
    allowed: "放行",
    review: "需审查",
    blocked: "已拦截",
  };

  return (
    <>
      <PageTitle title="Logs" subtitle="记录所有用户 Prompt；敏感内容只展示脱敏版本，不提供原文恢复" />
      <section className="panel">
        <div className="log-toolbar">
          <input
            className="search-input"
            placeholder="按用户、脱敏内容或实体类型过滤"
            value={keywordFilter}
            onChange={(event) => setKeywordFilter(event.target.value)}
          />
          <select
            aria-label="按处理结果筛选"
            value={decisionFilter}
            onChange={(event) => setDecisionFilter(event.target.value as "" | LogEntry["decision"])}
          >
            <option value="">全部处理结果</option>
            <option value="allowed">放行</option>
            <option value="review">需审查</option>
            <option value="blocked">已拦截</option>
          </select>
        </div>
        <div className="table-like">
          <div className="table-row log-row log-header" aria-hidden="true">
            <span>用户</span>
            <span>Prompt</span>
            <span>处理结果</span>
            <span>命中类型</span>
            <span>时间</span>
          </div>
          {visibleLogs.map((log) => (
            <div className="table-row log-row" key={log.id}>
              <span>{log.username}</span>
              <span>{log.sanitized_content}</span>
              <span className={`log-decision log-decision-${log.decision}`}>{decisionLabels[log.decision]}</span>
              <span>{(log.detected_entity_types || []).join(", ") || "-"}</span>
              <span>{formatDateTime(log.created_at)}</span>
            </div>
          ))}
          {visibleLogs.length === 0 ? <p className="empty-copy">没有符合当前筛选条件的日志。</p> : null}
        </div>
      </section>
    </>
  );
}

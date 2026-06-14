import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api/client";
import type { LogEntry } from "../../api/types";
import { formatDateTime } from "../../utils/format";
import { PageTitle } from "./DashboardPage";

export function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    apiFetch<LogEntry[]>("/api/logs").then(setLogs);
  }, []);

  const visibleLogs = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    if (!keyword) {
      return logs;
    }
    return logs.filter((log) => (
      log.username.toLowerCase().includes(keyword) ||
      log.sanitized_content.toLowerCase().includes(keyword) ||
      (log.detected_entity_types || []).join(" ").toLowerCase().includes(keyword)
    ));
  }, [logs, filter]);

  return (
    <>
      <PageTitle title="Logs" subtitle="只展示脱敏内容、实体类型、状态信息，不提供原文恢复" />
      <section className="panel">
        <input className="search-input" placeholder="按用户、脱敏内容或实体类型过滤" value={filter} onChange={(event) => setFilter(event.target.value)} />
        <div className="table-like">
          {visibleLogs.map((log) => (
            <div className="table-row log-row" key={log.id}>
              <span>{log.username}</span>
              <span>{log.sanitized_content}</span>
              <span>{(log.detected_entity_types || []).join(", ") || "-"}</span>
              <span>{formatDateTime(log.created_at)}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

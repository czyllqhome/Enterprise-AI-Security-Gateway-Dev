import { FormEvent, useEffect, useMemo, useState } from "react";
import { LogOut, MessageSquarePlus, Send, ShieldAlert, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { ChatPreview, ChatSession, ChatSessionDetail, Provider } from "../api/types";
import { useAuth } from "../state/AuthContext";
import { formatDateTime, messageText } from "../utils/format";

export function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selected, setSelected] = useState<ChatSessionDetail | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<ChatPreview | null>(null);
  const [loading, setLoading] = useState(false);

  const currentProvider = useMemo(() => providers.find((item) => item.provider === provider), [providers, provider]);

  useEffect(() => {
    bootstrap();
  }, []);

  async function bootstrap() {
    const providerData = await apiFetch<{ providers: Provider[] }>("/api/providers");
    setProviders(providerData.providers);
    const firstProvider = providerData.providers[0];
    if (firstProvider) {
      setProvider(firstProvider.provider);
      setModel(firstProvider.default_model || firstProvider.models[0] || "");
    }
    await loadSessions();
  }

  async function loadSessions(selectId?: number) {
    const data = await apiFetch<ChatSession[]>("/api/sessions");
    setSessions(data);
    const targetId = selectId ?? selected?.id ?? data[0]?.id;
    if (targetId) {
      await loadSession(targetId);
    } else {
      setSelected(null);
    }
  }

  async function loadSession(sessionId: number) {
    const detail = await apiFetch<ChatSessionDetail>(`/api/sessions/${sessionId}`);
    setSelected(detail);
    setProvider(detail.provider);
    setModel(detail.model);
  }

  async function createSession() {
    const created = await apiFetch<ChatSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "", provider, model }),
    });
    await loadSessions(created.id);
  }

  async function deleteSession() {
    if (!selected) {
      return;
    }
    await apiFetch<void>(`/api/sessions/${selected.id}`, { method: "DELETE" });
    setSelected(null);
    await loadSessions();
  }

  async function syncSessionSettings(nextProvider = provider, nextModel = model) {
    if (!selected) {
      return;
    }
    await apiFetch<ChatSession>(`/api/sessions/${selected.id}/settings`, {
      method: "PATCH",
      body: JSON.stringify({ provider: nextProvider, model: nextModel }),
    });
    await loadSessions(selected.id);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !message.trim()) {
      return;
    }
    setLoading(true);
    setStatus("正在进行安全扫描...");
    setPreview(null);
    try {
      const result = await apiFetch<ChatPreview>("/api/chat/preview", {
        method: "POST",
        body: JSON.stringify({ session_id: selected.id, message: message.trim() }),
      });
      if (result.status === "blocked") {
        setStatus(result.blocked_reason || "请求已被安全策略拦截。");
        return;
      }
      if (result.status === "needs_confirmation") {
        setPreview(result);
        setStatus("检测到敏感内容，请确认脱敏版本。");
        return;
      }
      await confirmSend(result);
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "发送失败。");
    } finally {
      setLoading(false);
    }
  }

  async function confirmSend(targetPreview: ChatPreview) {
    if (!selected) {
      return;
    }
    setLoading(true);
    setStatus("正在等待模型回复...");
    try {
      await apiFetch("/api/chat/confirm", {
        method: "POST",
        body: JSON.stringify({
          session_id: selected.id,
          original_message: targetPreview.original_message,
          sanitized_message: targetPreview.sanitized_message,
          scan_event_id: targetPreview.scan_event_id,
          enabled_scanners: targetPreview.enabled_scanners,
        }),
      });
      setMessage("");
      setPreview(null);
      setStatus("已发送。");
      await loadSessions(selected.id);
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "确认发送失败。");
    } finally {
      setLoading(false);
    }
  }

  function handleProviderChange(nextProvider: string) {
    const target = providers.find((item) => item.provider === nextProvider);
    const nextModel = target?.default_model || target?.models[0] || "";
    setProvider(nextProvider);
    setModel(nextModel);
    syncSessionSettings(nextProvider, nextModel);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-head">
          <strong>AI Gateway</strong>
          <button className="icon-btn" onClick={() => { logout(); navigate("/login"); }} title="退出登录">
            <LogOut size={18} />
          </button>
        </div>
        <div className="user-card">
          <span>{user?.display_name || user?.username}</span>
          <small>{user?.role === "admin" ? "管理员也可使用聊天侧" : "用户侧聊天"}</small>
        </div>
        <button className="secondary-btn full-width" onClick={createSession}>
          <MessageSquarePlus size={17} />
          新建会话
        </button>
        <div className="session-list">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={`session-row ${selected?.id === session.id ? "active" : ""}`}
              onClick={() => loadSession(session.id)}
            >
              <strong>{session.title}</strong>
              <span>{session.provider} / {session.model}</span>
            </button>
          ))}
          {!sessions.length ? <p className="empty-state">还没有会话。</p> : null}
        </div>
      </aside>

      <section className="chat-workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">User Chat</p>
            <h1>{selected?.title || "请选择或创建会话"}</h1>
          </div>
          {user?.role === "admin" ? <button className="secondary-btn" onClick={() => navigate("/admin")}>进入管理平台</button> : null}
        </header>

        <div className="toolbar">
          <label>
            Provider
            <select value={provider} onChange={(event) => handleProviderChange(event.target.value)}>
              {providers.map((item) => <option key={item.provider} value={item.provider}>{item.display_name}</option>)}
            </select>
          </label>
          <label>
            Model
            <select value={model} onChange={(event) => { setModel(event.target.value); syncSessionSettings(provider, event.target.value); }}>
              {(currentProvider?.models.length ? currentProvider.models : [currentProvider?.default_model || model]).map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <span className={`pill ${currentProvider?.configured || currentProvider?.requires_api_key === false ? "ok" : "warn"}`}>
            {currentProvider?.requires_api_key === false ? "Local provider" : currentProvider?.configured ? currentProvider.masked_api_key : "Key not configured"}
          </span>
          <button className="icon-btn danger" onClick={deleteSession} disabled={!selected} title="删除会话">
            <Trash2 size={18} />
          </button>
        </div>

        <div className="message-pane">
          {selected?.messages.map((item) => (
            <article className={`message ${item.role}`} key={item.id}>
              <span>{item.role === "user" ? "你" : "助手"}</span>
              <p>{messageText(item)}</p>
              <small>{formatDateTime(item.created_at)}</small>
            </article>
          ))}
          {selected && !selected.messages.length ? <p className="empty-state">输入第一条消息开始安全聊天。</p> : null}
          {!selected ? <p className="empty-state">创建会话后即可开始。</p> : null}
        </div>

        {preview ? (
          <section className="review-panel">
            <div>
              <ShieldAlert size={18} />
              <strong>敏感内容确认</strong>
            </div>
            <div className="review-grid">
              <label>原始内容<textarea value={preview.original_message} readOnly /></label>
              <label>脱敏内容<textarea value={preview.sanitized_message} readOnly /></label>
            </div>
            <div className="entity-strip">
              {preview.entity_types.map((item) => <span key={item}>{item}</span>)}
              {preview.business_sensitive_result?.contains_business_sensitive ? <span>Business: {preview.business_sensitive_result.risk_level}</span> : null}
            </div>
            <button className="primary-btn" onClick={() => confirmSend(preview)} disabled={loading}>
              <Send size={17} />
              发送脱敏版本
            </button>
          </section>
        ) : null}

        <form className="composer" onSubmit={handleSubmit}>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="输入消息，系统会先进行安全扫描..." />
          <button className="primary-btn" disabled={!selected || loading || !message.trim()}>
            <Send size={18} />
            发送
          </button>
        </form>
        <div className="status-line">{status}</div>
      </section>
    </main>
  );
}

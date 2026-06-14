import { FormEvent, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import { useAuth } from "../state/AuthContext";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (user) {
    return <Navigate to={user.role === "admin" ? "/admin" : "/app/chat"} replace />;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const currentUser = await login(username.trim(), password);
      navigate(currentUser.role === "admin" ? "/admin" : "/app/chat", { replace: true });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "登录失败，请检查账号和密码。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel" aria-label="Gateway login">
        <div className="brand-mark">
          <ShieldCheck size={30} />
          <span>Enterprise AI Security Gateway</span>
        </div>
        <h1>登录</h1>
        <p className="muted">用户登录后进入聊天界面，管理员通过独立的管理平台治理安全策略。</p>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            账号
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            密码
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>
          {error ? <div className="error-text">{error}</div> : null}
          <button className="primary-btn" type="submit" disabled={loading}>
            <LockKeyhole size={18} />
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}

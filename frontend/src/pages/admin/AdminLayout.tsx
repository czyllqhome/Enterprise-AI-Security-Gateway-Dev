import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Activity, BarChart3, KeyRound, LogOut, MessageSquare, ScanLine, Users } from "lucide-react";
import { useAuth } from "../../state/AuthContext";

export function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <main className="admin-shell">
      <aside className="sidebar admin-sidebar">
        <div className="sidebar-head">
          <strong>Admin</strong>
          <button className="icon-btn" onClick={() => { logout(); navigate("/login"); }} title="退出登录">
            <LogOut size={18} />
          </button>
        </div>
        <div className="user-card">
          <span>{user?.display_name || user?.username}</span>
          <small>管理平台</small>
        </div>
        <nav className="nav-stack">
          <NavLink to="/admin" end><BarChart3 size={18} />Dashboard</NavLink>
          <NavLink to="/admin/users"><Users size={18} />Users</NavLink>
          <NavLink to="/admin/api-keys"><KeyRound size={18} />API Keys</NavLink>
          <NavLink to="/admin/scanners"><ScanLine size={18} />Scanners</NavLink>
          <NavLink to="/admin/token-usage"><Activity size={18} />Token Usage</NavLink>
          <NavLink to="/admin/logs"><BarChart3 size={18} />Logs</NavLink>
        </nav>
        <Link className="secondary-btn full-width" to="/app/chat">
          <MessageSquare size={17} />
          用户侧聊天
        </Link>
      </aside>
      <section className="admin-content">
        <Outlet />
      </section>
    </main>
  );
}

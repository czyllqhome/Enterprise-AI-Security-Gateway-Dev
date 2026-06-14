import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import type { User } from "../../api/types";
import { formatDateTime } from "../../utils/format";
import { PageTitle } from "./DashboardPage";

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [status, setStatus] = useState("");

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    setUsers(await apiFetch<User[]>("/api/admin/users"));
  }

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setStatus("");
    try {
      await apiFetch<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({ username, password, display_name: displayName || null, role, is_active: true }),
      });
      setUsername("");
      setPassword("");
      setDisplayName("");
      await loadUsers();
      setStatus("用户已创建。");
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "创建失败。");
    }
  }

  async function patchUser(user: User, payload: Partial<User>) {
    await apiFetch<User>(`/api/admin/users/${user.id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    await loadUsers();
  }

  async function resetPassword(user: User) {
    const nextPassword = window.prompt(`为 ${user.username} 设置新密码`);
    if (!nextPassword) {
      return;
    }
    await apiFetch<User>(`/api/admin/users/${user.id}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: nextPassword }),
    });
    setStatus("密码已重置。");
  }

  return (
    <>
      <PageTitle title="Users" subtitle="创建、禁用和调整用户角色" />
      <form className="panel form-grid" onSubmit={createUser}>
        <input placeholder="username" value={username} onChange={(event) => setUsername(event.target.value)} />
        <input placeholder="display name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        <input placeholder="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        <select value={role} onChange={(event) => setRole(event.target.value as "user" | "admin")}>
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <button className="primary-btn">创建用户</button>
      </form>
      <section className="panel">
        <div className="table-like">
          {users.map((user) => (
            <div className="table-row user-row" key={user.id}>
              <span><strong>{user.username}</strong><small>{user.display_name}</small></span>
              <select value={user.role} onChange={(event) => patchUser(user, { role: event.target.value as User["role"] })}>
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
              <label className="inline-toggle">
                <input type="checkbox" checked={user.is_active} onChange={(event) => patchUser(user, { is_active: event.target.checked })} />
                active
              </label>
              <span>{formatDateTime(user.last_login_at)}</span>
              <button className="secondary-btn" onClick={() => resetPassword(user)}>重置密码</button>
            </div>
          ))}
        </div>
      </section>
      <div className="status-line">{status}</div>
    </>
  );
}

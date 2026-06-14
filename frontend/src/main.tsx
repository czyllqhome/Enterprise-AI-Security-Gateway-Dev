import React from "react";
import ReactDOM from "react-dom/client";
import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "./state/AuthContext";
import { LoginPage } from "./pages/LoginPage";
import { ChatPage } from "./pages/ChatPage";
import { AdminLayout } from "./pages/admin/AdminLayout";
import { DashboardPage } from "./pages/admin/DashboardPage";
import { UsersPage } from "./pages/admin/UsersPage";
import { ApiKeysPage } from "./pages/admin/ApiKeysPage";
import { ScannersPage } from "./pages/admin/ScannersPage";
import { LogsPage } from "./pages/admin/LogsPage";
import "./styles.css";

function RootRedirect() {
  const { user, bootstrapped } = useAuth();
  if (!bootstrapped) {
    return <div className="screen-loader">Loading...</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <Navigate to={user.role === "admin" ? "/admin" : "/app/chat"} replace />;
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, bootstrapped } = useAuth();
  if (!bootstrapped) {
    return <div className="screen-loader">Loading...</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, bootstrapped } = useAuth();
  if (!bootstrapped) {
    return <div className="screen-loader">Loading...</div>;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (user.role !== "admin") {
    return <Navigate to="/app/chat" replace />;
  }
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  { path: "/login", element: <LoginPage /> },
  {
    path: "/app/chat",
    element: (
      <RequireAuth>
        <ChatPage />
      </RequireAuth>
    ),
  },
  {
    path: "/admin",
    element: (
      <RequireAdmin>
        <AdminLayout />
      </RequireAdmin>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "users", element: <UsersPage /> },
      { path: "api-keys", element: <ApiKeysPage /> },
      { path: "scanners", element: <ScannersPage /> },
      { path: "logs", element: <LogsPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </React.StrictMode>,
);

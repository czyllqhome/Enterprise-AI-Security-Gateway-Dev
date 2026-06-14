# Enterprise AI Security Gateway

This repository is now split into two local services:

- Backend API: `http://127.0.0.1:8002`
- Frontend app: `http://127.0.0.1:5173`

The backend no longer serves the product UI from `8002`. It exposes API routes, OpenAPI docs, health checks, authentication, chat, scanner governance, logs, provider configuration, and admin user management.

## Local Startup

Backend:

```powershell
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open the product at:

- Login: `http://127.0.0.1:5173/login`
- User chat: `http://127.0.0.1:5173/app/chat`
- Admin platform: `http://127.0.0.1:5173/admin`

The frontend uses `VITE_API_BASE_URL=http://127.0.0.1:8002` by default.

## Routing Model

- Unauthenticated users are sent to `/login`.
- A user with role `user` is sent to `/app/chat` after login.
- A user with role `admin` is sent to `/admin` after login.
- `/admin/*` is protected on both frontend route guards and backend API authorization.
- Chat/session requests use the JWT user from the backend. The frontend does not trust or submit a browser-controlled username.

## Backend Root

`http://127.0.0.1:8002/` returns service metadata only. Use `/docs` for API inspection and `/api/health` for the health check.

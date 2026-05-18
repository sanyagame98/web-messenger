# Web Messenger

Telegram-like web messenger MVP.

- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **Backend**: FastAPI + SQLAlchemy + SQLite (PostgreSQL-ready)
- **Realtime**: WebSocket (messages, typing, presence)
- **Auth**: JWT, email + username (5–32 chars) + password

## Project structure

```
backend/   FastAPI app (REST + WebSocket)
frontend/  Next.js app (App Router)
```

## Quickstart

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Default DB is SQLite at `backend/data/app.db`. Override with `DATABASE_URL`.

API docs: <http://localhost:8000/docs>

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` to the backend URL (default `http://localhost:8000`).

App: <http://localhost:3000>

## Features (MVP)

- Registration/login by email + username + password
- Profiles with avatar and bio
- User search by username
- 1-to-1 and group chats
- Text and image messages
- Typing indicators
- Online/offline presence
- Read state per chat
- Realtime updates via WebSocket

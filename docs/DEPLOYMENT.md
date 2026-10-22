# Deployment

The app is one container (FastAPI + model) plus a PostgreSQL database. Whisper `small` needs
~1 GB RAM and a few CPU cores; microphones require **HTTPS**, which all hosts below provide.

## Local (Docker Compose, Postgres)
```bash
docker compose up --build        # http://localhost:8000
```

## Local (no Docker, SQLite)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

## Hugging Face Spaces (Docker SDK) – free CPU, HTTPS included
1. Create a Space → SDK **Docker**; push this repo (port 7860: set `PORT=7860` in Space variables).
2. Create a free Postgres at neon.tech / supabase.com and add `DATABASE_URL` as a Space secret.

## Render / Railway / Fly.io
- Deploy the Dockerfile as a Web Service (≥1 GB RAM). Add a managed Postgres and set
  `DATABASE_URL`. Health check path: `/api/health`.
- Use `WHISPER_MODEL=base` if memory is tight.

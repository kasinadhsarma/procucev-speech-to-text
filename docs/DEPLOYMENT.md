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

## Hugging Face Spaces (live deployment) – free, HTTPS included
Live: https://kasinadhsarma-speech-to-text.hf.space

Free accounts only get **ZeroGPU** hardware for Gradio-SDK Spaces (Docker and CPU basic need PRO),
and ZeroGPU refuses to start unless Gradio launches an app with an `@spaces.GPU` function.
`hf_entry.py` handles this: Gradio owns port 7860 with a hidden placeholder GPU function, and
the FastAPI routes (UI, REST, WebSocket) are injected ahead of Gradio's own (`app_kwargs.routes`).
SSR is disabled (`ssr_mode=False`) because its Node proxy would otherwise hide those routes.
Transcription itself runs on CPU.

1. Create a Space: SDK **Gradio**, template Blank.
2. Upload: `hf upload <user>/<space> . . --repo-type=space --exclude ".git/*" --exclude ".venv/*"`
3. Space secret `DATABASE_URL` = Neon connection string (without `channel_binding=require`).
   Without it the app falls back to SQLite inside the container, which resets on restart.

## Render / Railway / Fly.io
- Deploy the Dockerfile as a Web Service (≥1 GB RAM). Add a managed Postgres and set
  `DATABASE_URL`. Health check path: `/api/health`.
- Use `WHISPER_MODEL=base` if memory is tight.

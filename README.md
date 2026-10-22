---
title: Speech to Text
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: hf_entry.py
python_version: "3.12"
pinned: false
---

# Real-time Speech-to-Text (Hindi · English · Hinglish)

Web app that transcribes speech **live** from the microphone, stores each transcript in a
relational database and offers a dashboard with full CRUD + search.

- **STT:** open-source [Whisper](https://github.com/openai/whisper) via `faster-whisper`, self-hosted (no 3rd-party API)
- **Backend:** Python, FastAPI, WebSockets, SQLAlchemy
- **Database:** PostgreSQL (docker-compose) — SQLite fallback for quick local runs
- **Frontend:** vanilla JS + AudioWorklet, no build step

## Features
- Live streaming transcription with greyed-out partial results that firm up when you pause
- Mixed Hindi + English (auto-detect per segment, or force `hi` / `en`)
- Transcripts auto-saved on stop; dashboard to **create, read, update, delete**, and search
- REST API + Swagger docs at `/docs`

## Quick start
```bash
docker compose up --build         # open http://localhost:8000
```
or without Docker:
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app    # first start downloads the Whisper model (~460 MB)
```
Click **Start recording**, speak, click **Stop & save**.

## Configuration
See [`.env.example`](.env.example). Main knobs: `DATABASE_URL`, `WHISPER_MODEL`, `WHISPER_COMPUTE`.

## Tests
```bash
.venv/bin/pytest -q
```

## Docs
- [Architecture & API](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Submission email draft](docs/SUBMISSION_EMAIL.md)

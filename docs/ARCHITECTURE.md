# Architecture

Real-time, multilingual (Hindi · English · Hinglish) speech-to-text service with a CRUD dashboard.

- **Live:** https://kasinadhsarma-speech-to-text.hf.space
- **Related docs:** [API reference](API.md) · [Database schema](DATABASE.md) · [Tech stack](TECH_STACK.md) · [Deployment](DEPLOYMENT.md) · [PDF (LaTeX)](latex/documentation.pdf)

---

## 1. System context

```mermaid
flowchart LR
    user([User<br/>speaks Hindi / English])
    browser[Web browser<br/>Recorder + Dashboard]
    server[Speech-to-Text service<br/>FastAPI + Whisper]
    db[(PostgreSQL<br/>Neon)]
    hub[(Hugging Face Hub<br/>model weights)]

    user -- microphone --> browser
    browser -- "WebSocket: PCM audio" --> server
    server -- "partial / final text" --> browser
    browser -- "REST: CRUD" --> server
    server -- SQL --> db
    server -. "first start: download model" .-> hub
```

## 2. Components

```mermaid
flowchart TB
    subgraph Client["Browser (static/)"]
        UI[index.html + style.css]
        APP[app.js<br/>recorder · live view · CRUD UI]
        WK[AudioWorklet 'pcm'<br/>Float32 to Int16 at 16 kHz]
        APP --> WK
    end

    subgraph Server["Python service (app/)"]
        MAIN[main.py<br/>FastAPI app]
        REST[REST router<br/>/api/transcriptions]
        WS[WebSocket handler<br/>/ws/transcribe]
        SEG[Segmenter<br/>buffer + silence detection]
        STT[stt.py<br/>faster-whisper wrapper]
        DBM[db.py<br/>SQLAlchemy ORM]
        MAIN --> REST
        MAIN --> WS
        WS --> SEG --> STT
        REST --> DBM
        WS --> DBM
    end

    ENTRY[hf_entry.py<br/>Gradio host for HF ZeroGPU]
    ENTRY -. injects routes .-> MAIN

    WK -- binary frames --> WS
    APP -- fetch JSON --> REST
    DBM --> PG[(PostgreSQL / SQLite)]
    STT --> MODEL[[Whisper small<br/>CTranslate2 int8, CPU]]
```

| Module | Responsibility |
|---|---|
| `static/app.js` | Microphone capture, WebSocket streaming, live transcript rendering, dashboard CRUD |
| `app/main.py` | FastAPI app: REST endpoints, WebSocket endpoint, segmentation loop, static hosting |
| `app/stt.py` | Lazily loads one shared Whisper model; `transcribe(audio, language)` |
| `app/db.py` | Engine/session setup, `Transcription` ORM model, `DATABASE_URL` normalisation |
| `hf_entry.py` | Hugging Face entry point: Gradio owns port 7860, FastAPI routes injected first |

## 3. Real-time transcription sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser (app.js)
    participant W as AudioWorklet
    participant S as FastAPI /ws/transcribe
    participant M as Whisper (thread pool)
    participant D as PostgreSQL

    U->>B: Click "Start recording"
    B->>B: getUserMedia() + AudioContext(16 kHz)
    B->>S: WebSocket open ?language=auto
    loop every audio frame
        W->>B: Int16 PCM chunk
        B->>S: binary frame
        S->>S: append to segment buffer
        alt 1.5 s of new audio
            S->>M: transcribe(segment)
            M-->>S: text, language
            S-->>B: {"type":"partial","text":...}
        else 0.8 s silence or segment over 25 s
            S->>M: transcribe(segment)
            M-->>S: text, language
            S-->>B: {"type":"final","text":...}
            S->>S: reset segment
        end
    end
    U->>B: Click "Stop & save"
    B->>S: text frame "stop"
    S->>M: transcribe(remaining audio)
    S->>D: INSERT transcription
    D-->>S: row
    S-->>B: {"type":"saved","transcription":{...}}
    B->>B: refresh history list
```

## 4. Segmenter state machine

```mermaid
stateDiagram-v2
    [*] --> Listening
    Listening --> Listening: audio chunk
    Listening --> DecodingPartial: 1.5 s new audio
    DecodingPartial --> Listening: send partial
    Listening --> DecodingFinal: 0.8 s silence or segment over 25 s
    DecodingFinal --> Listening: send final, clear buffer
    Listening --> Flushing: stop or disconnect
    Flushing --> Saved: INSERT row
    Saved --> [*]
```

| Parameter | Value | Where |
|---|---|---|
| Sample rate | 16 000 Hz mono, Int16 | `stt.SAMPLE_RATE`, `app.js` |
| Partial re-decode interval | 1.5 s | `PARTIAL_EVERY_SEC` |
| Silence window / threshold | 0.8 s / RMS 0.012 | `SILENCE_SEC`, `SILENCE_RMS` |
| Max segment length | 25 s | `MAX_SEGMENT_SEC` |
| Decoder | beam 1, VAD filter on, Hinglish `initial_prompt` | `stt.transcribe` |

## 5. Data model

```mermaid
erDiagram
    TRANSCRIPTIONS {
        INTEGER id PK "auto-increment"
        VARCHAR title "max 200, default Untitled"
        TEXT text "full transcript, UTF-8"
        VARCHAR language "max 32: auto, hi, en, detected code"
        FLOAT duration_sec "audio length in seconds"
        TIMESTAMPTZ created_at "UTC"
        TIMESTAMPTZ updated_at "UTC, set on update"
    }
```

Full DDL, constraints and example rows: [DATABASE.md](DATABASE.md).

## 6. Deployment

```mermaid
flowchart LR
    dev[Developer laptop] -- git push --> gh[GitHub repo]
    dev -- hf upload --> space

    subgraph HF["Hugging Face Space (ZeroGPU, free)"]
        space[Container: Python 3.12]
        gradio[Gradio server :7860<br/>SSR off]
        fast[FastAPI routes<br/>UI, REST, WS]
        whisper[Whisper small<br/>CPU int8]
        space --> gradio --> fast --> whisper
    end

    fast -- TLS, psycopg2 --> neon[(Neon PostgreSQL)]
    browser[User browser] -- HTTPS / WSS --> gradio
```

Other targets (Docker Compose with Postgres, Render, Railway, Fly.io) are in [DEPLOYMENT.md](DEPLOYMENT.md).

## 7. Multilingual handling

- Whisper is trained on 99 languages, including Hindi, and handles code-switching within one utterance.
- `language=auto` detects the language per segment; the saved row stores the most frequent one.
- A Hinglish `initial_prompt` biases decoding toward mixed Hindi/English output.
- Hindi words come out in Devanagari and English words usually in Latin script. Heavily accented English may be transliterated into Devanagari; larger models (`medium`, `large-v3`) reduce this.

## 8. Design decisions and trade-offs

| Decision | Reason | Trade-off |
|---|---|---|
| Self-hosted Whisper (faster-whisper) | Open source, no API keys, strong Hindi support | 1–3 s CPU latency per decode on free hardware |
| Re-decode the live segment for partials | Whisper is not a streaming model | Repeated compute, bounded by 25 s segments |
| Energy-based silence detection | Simple, no extra dependency | Can mis-segment in noisy rooms (Whisper VAD also on) |
| Raw PCM over WebSocket | No codec on either side, low latency | About 32 KB/s upstream |
| SQLAlchemy + `DATABASE_URL` | Same code on PostgreSQL and SQLite | No migration tool yet (table created on start) |
| Vanilla JS frontend | No build step, small surface | No component framework |

## 9. Known limitations

- No authentication: every visitor shares one history.
- No schema migrations (Alembic) yet; `create_all` runs on startup.
- One shared model instance, so concurrent sessions queue for CPU.
- Microphone access requires HTTPS or `localhost`.

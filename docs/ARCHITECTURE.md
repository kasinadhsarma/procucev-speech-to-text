# Architecture

```
Browser (mic) ──AudioWorklet──▶ 16 kHz mono Int16 PCM ──WebSocket /ws/transcribe──▶ FastAPI
                                                                                      │
                                         rolling buffer + silence detection           │
                                                                                      ▼
                                              faster-whisper (open-source Whisper, CPU int8)
                                                                                      │ partial / final JSON
Browser live view ◀───────────────────────────────────────────────────────────────────┘
                                                                                      │ on "stop"
Dashboard (CRUD) ◀──── REST /api/transcriptions ◀──── SQLAlchemy ◀──── PostgreSQL / SQLite
```

## Real-time pipeline
1. `getUserMedia` captures the mic; an `AudioContext({sampleRate:16000})` resamples; an inline
   `AudioWorklet` converts Float32 → Int16 and posts ~128-sample frames.
2. Frames are streamed over a WebSocket as binary messages.
3. The server appends to the current *segment* buffer. Every 1.5 s it re-decodes the segment and
   sends a `partial` message (greyed text in the UI). When ≥0.8 s of trailing silence (RMS < 0.012)
   is detected, or the segment exceeds 25 s, it sends a `final` message and starts a new segment.
4. Sending the text frame `stop` flushes the last segment, saves the combined transcript to the
   DB and replies `{type:"saved", transcription:{…}}`.

## Multilingual (Hindi + English)
Whisper is natively multilingual. Language is auto-detected per segment (override with the
dropdown) and an `initial_prompt` containing a Hinglish sentence biases the decoder towards
code-switched output. Model size is configurable (`WHISPER_MODEL`); `small` is the default
trade-off between accuracy and CPU latency, `medium`/`large-v3` are noticeably better on Hinglish.

## Data model
`transcriptions(id, title, text, language, duration_sec, created_at, updated_at)`

## REST API
| Method | Path | Description |
|---|---|---|
| GET | `/api/transcriptions?q=&limit=&offset=` | List / search (newest first) |
| POST | `/api/transcriptions` | Create `{title, text, language, duration_sec}` |
| GET | `/api/transcriptions/{id}` | Read one |
| PUT | `/api/transcriptions/{id}` | Update `{title?, text?, language?}` |
| DELETE | `/api/transcriptions/{id}` | Delete (204) |
| GET | `/api/health` | Liveness |
| WS | `/ws/transcribe?language=auto\|hi\|en` | Streaming transcription |

Interactive docs: `/docs` (Swagger UI).

## Design trade-offs / known limits
- Whisper isn't a streaming model; re-decoding the live segment gives "partial" results at the cost
  of repeated compute. Segments are capped at 25 s to bound this.
- Energy-based silence detection is simple; it can mis-segment in noisy rooms (Whisper's own VAD
  filter is also on).
- No auth: every visitor shares one history. Add auth before any public production use.
- Microphone access requires HTTPS (or localhost).

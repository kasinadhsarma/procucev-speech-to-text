# API Reference

Base URL (live): `https://kasinadhsarma-speech-to-text.hf.space`
Local: `http://localhost:8000` · Interactive Swagger UI: `/docs` · OpenAPI JSON: `/openapi.json`

All REST bodies are JSON (`Content-Type: application/json`, UTF-8). Timestamps are ISO 8601 in UTC.

## Endpoint summary

| Method | Path | Description | Success |
|---|---|---|---|
| `GET` | `/api/health` | Liveness, model size, database backend | 200 |
| `GET` | `/api/transcriptions` | List and search transcriptions | 200 |
| `POST` | `/api/transcriptions` | Create a transcription | 201 |
| `GET` | `/api/transcriptions/{id}` | Read one transcription | 200 |
| `PUT` | `/api/transcriptions/{id}` | Partially update a transcription | 200 |
| `DELETE` | `/api/transcriptions/{id}` | Delete a transcription | 204 |
| `WS` | `/ws/transcribe` | Stream audio, receive live text | — |

---

## Schemas

### `Transcription` (response)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Transcription",
  "type": "object",
  "required": ["id", "title", "text", "language", "duration_sec", "created_at", "updated_at"],
  "properties": {
    "id":           { "type": "integer", "minimum": 1 },
    "title":        { "type": "string", "maxLength": 200 },
    "text":         { "type": "string" },
    "language":     { "type": "string", "maxLength": 32, "examples": ["auto", "hi", "en"] },
    "duration_sec": { "type": "number", "minimum": 0 },
    "created_at":   { "type": "string", "format": "date-time" },
    "updated_at":   { "type": "string", "format": "date-time" }
  }
}
```

### `TranscriptionIn` (create body)

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `title` | string | no | `"Untitled"` | max 200 chars |
| `text` | string | no | `""` | |
| `language` | string | no | `"auto"` | |
| `duration_sec` | number | no | `0.0` | |

### `TranscriptionUpdate` (update body)

All fields are optional. Omitted or `null` fields are left unchanged.

| Field | Type | Constraints |
|---|---|---|
| `title` | string | max 200 chars |
| `text` | string | |
| `language` | string | |

### Error

```json
{ "detail": "Transcription not found" }
```

Validation errors return **422** with FastAPI's standard `detail` array.

---

## REST endpoints

### `GET /api/health`

```bash
curl https://kasinadhsarma-speech-to-text.hf.space/api/health
```
```json
{ "status": "ok", "model": "small", "database": "postgresql" }
```

### `GET /api/transcriptions`

| Query | Type | Default | Description |
|---|---|---|---|
| `q` | string | — | Case-insensitive substring match on `title` or `text` |
| `limit` | int | 50 | 1–200 |
| `offset` | int | 0 | 0 or more |

Results are sorted newest first.

```bash
curl "https://kasinadhsarma-speech-to-text.hf.space/api/transcriptions?q=meeting&limit=10"
```
```json
[
  {
    "id": 7,
    "title": "Kal subah meeting hai, please…",
    "text": "Kal subah meeting hai, please slides ready rakhna.",
    "language": "hi",
    "duration_sec": 4.12,
    "created_at": "2026-10-22T11:40:02.118Z",
    "updated_at": "2026-10-22T11:40:02.118Z"
  }
]
```

### `POST /api/transcriptions`

```bash
curl -X POST https://kasinadhsarma-speech-to-text.hf.space/api/transcriptions \
  -H "Content-Type: application/json" \
  -d '{"title":"Note","text":"नमस्ते, this is a test","language":"hi"}'
```
Response **201**: a `Transcription`.

### `GET /api/transcriptions/{id}`

Response **200** with a `Transcription`, or **404** `{"detail":"Transcription not found"}`.

### `PUT /api/transcriptions/{id}`

```bash
curl -X PUT https://kasinadhsarma-speech-to-text.hf.space/api/transcriptions/7 \
  -H "Content-Type: application/json" -d '{"title":"Team meeting"}'
```
Response **200** with the updated `Transcription` (`updated_at` refreshed), or **404**.

### `DELETE /api/transcriptions/{id}`

Response **204** with no body, or **404**.

---

## WebSocket: `/ws/transcribe`

```
wss://kasinadhsarma-speech-to-text.hf.space/ws/transcribe?language=auto
```

| Query | Values | Default |
|---|---|---|
| `language` | `auto`, `hi`, `en` (any Whisper language code) | `auto` |

### Client → server

| Frame | Payload | Meaning |
|---|---|---|
| binary | Little-endian **Int16 PCM**, mono, **16 000 Hz**, any chunk size | Audio to transcribe |
| text | `stop` | Finish: flush, save, close |

### Server → client (JSON text frames)

| `type` | Fields | When |
|---|---|---|
| `partial` | `text`, `language` | About every 1.5 s of new audio; may still change |
| `final` | `text`, `language` | Segment closed by 0.8 s of silence or the 25 s cap; stable |
| `saved` | `transcription` (`Transcription` or `null`) | After `stop`; `null` if nothing was recognised |
| `error` | `message` | Unexpected server error |

```json
{"type": "partial", "text": "मेरा नाम काशी है", "language": "hi"}
{"type": "final",   "text": "मेरा नाम काशी है और मैं Bangalore में software engineer हूँ", "language": "hi"}
{"type": "saved",   "transcription": {"id": 8, "title": "मेरा नाम काशी है…"}}
```

### Minimal Python client

```python
import asyncio, json, websockets

async def main(pcm_path):
    url = "wss://kasinadhsarma-speech-to-text.hf.space/ws/transcribe?language=auto"
    async with websockets.connect(url) as ws:
        pcm = open(pcm_path, "rb").read()
        for i in range(0, len(pcm), 3200):        # 100 ms chunks
            await ws.send(pcm[i:i + 3200])
            await asyncio.sleep(0.1)
        await ws.send("stop")
        async for msg in ws:
            print(json.loads(msg))

asyncio.run(main("speech.pcm"))   # ffmpeg -i in.mp3 -ar 16000 -ac 1 -f s16le speech.pcm
```

A complete version is in [`tests/stream_demo.py`](../tests/stream_demo.py).

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import stt
from .db import SessionLocal, Transcription, init_db

STATIC = Path(__file__).resolve().parent.parent / "static"
PARTIAL_EVERY_SEC = 1.5      # re-decode the live segment this often
SILENCE_SEC = 0.8            # trailing silence that closes a segment
SILENCE_RMS = 0.012
MAX_SEGMENT_SEC = 25.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if os.getenv("PRELOAD_MODEL", "1") == "1":
        await asyncio.to_thread(stt.get_model)  # warm up so the first request is fast
    yield


app = FastAPI(title="Speech to Text", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TranscriptionIn(BaseModel):
    title: str = Field("Untitled", max_length=200)
    text: str = ""
    language: str = "auto"
    duration_sec: float = 0.0


class TranscriptionUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    text: str | None = None
    language: str | None = None


# ---------------------------------------------------------------- CRUD API
@app.get("/api/health")
def health():
    return {"status": "ok", "model": stt.MODEL_SIZE}


@app.get("/api/transcriptions")
def list_transcriptions(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Transcription).order_by(Transcription.created_at.desc(), Transcription.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Transcription.text.ilike(like), Transcription.title.ilike(like)))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return [r.to_dict() for r in rows]


@app.post("/api/transcriptions", status_code=201)
def create_transcription(body: TranscriptionIn, db: Session = Depends(get_db)):
    row = Transcription(**body.model_dump())
    db.add(row)
    db.commit()
    return row.to_dict()


def _get_or_404(db: Session, tid: int) -> Transcription:
    row = db.get(Transcription, tid)
    if not row:
        raise HTTPException(404, "Transcription not found")
    return row


@app.get("/api/transcriptions/{tid}")
def get_transcription(tid: int, db: Session = Depends(get_db)):
    return _get_or_404(db, tid).to_dict()


@app.put("/api/transcriptions/{tid}")
def update_transcription(tid: int, body: TranscriptionUpdate, db: Session = Depends(get_db)):
    row = _get_or_404(db, tid)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(row, k, v)
    db.commit()
    return row.to_dict()


@app.delete("/api/transcriptions/{tid}", status_code=204)
def delete_transcription(tid: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, tid))
    db.commit()


# ------------------------------------------------------- real-time WebSocket
@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket, language: str = "auto"):
    """Client streams 16 kHz mono Int16 PCM as binary frames.
    Server replies with JSON: partial | final | saved | error.
    Send the text frame "stop" to end the session; the transcript is then stored.
    """
    await ws.accept()
    sr = stt.SAMPLE_RATE
    segment = np.zeros(0, dtype=np.float32)
    since_decode = 0
    finals: list[str] = []
    langs: list[str] = []
    total_samples = 0

    async def decode(final: bool):
        nonlocal segment, since_decode
        audio = segment.copy()
        since_decode = 0
        text, lang = await asyncio.to_thread(stt.transcribe, audio, language)
        if text:
            if final:
                finals.append(text)
                langs.append(lang)
            await ws.send_json({"type": "final" if final else "partial", "text": text, "language": lang})
        if final:
            segment = np.zeros(0, dtype=np.float32)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("text") is not None:
                if msg["text"].strip().lower() == "stop":
                    break
                continue
            data = msg.get("bytes")
            if not data:
                continue
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            segment = np.concatenate([segment, chunk])
            total_samples += chunk.size
            since_decode += chunk.size

            tail = segment[-int(SILENCE_SEC * sr):]
            silent = segment.size > sr * 1.0 and tail.size >= SILENCE_SEC * sr and float(np.sqrt(np.mean(tail**2))) < SILENCE_RMS
            if silent or segment.size > MAX_SEGMENT_SEC * sr:
                await decode(final=True)
            elif since_decode >= PARTIAL_EVERY_SEC * sr:
                await decode(final=False)

        if segment.size:
            await decode(final=True)

        full_text = " ".join(finals).strip()
        if full_text:
            lang = max(set(langs), key=langs.count) if langs else "auto"
            with SessionLocal() as db:
                row = Transcription(
                    title=full_text[:60] + ("…" if len(full_text) > 60 else ""),
                    text=full_text,
                    language=lang,
                    duration_sec=total_samples / sr,
                )
                db.add(row)
                db.commit()
                await ws.send_json({"type": "saved", "transcription": row.to_dict()})
        else:
            await ws.send_json({"type": "saved", "transcription": None})
        await ws.close()
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:  # noqa: BLE001
            pass


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")

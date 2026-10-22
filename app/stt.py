"""Speech-to-text engine: open-source Whisper via faster-whisper (CTranslate2).

Whisper is multilingual and handles Hindi/English code-switching (Hinglish).
"""
import os
import threading

import numpy as np

SAMPLE_RATE = 16000  # Whisper expects 16 kHz mono audio
MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
# Biases the decoder toward mixed Hindi + English output.
HINGLISH_PROMPT = os.getenv(
    "WHISPER_PROMPT", "Hindi aur English mix. Yeh ek Hinglish sentence hai, for example: meeting kal subah hai."
)

_model = None  # shared WhisperModel, created on first use
_lock = threading.Lock()  # prevents two threads loading the model at once


def get_model():
    """Return the shared ``WhisperModel``, loading it on the first call.

    Thread-safe. The first call downloads the weights from the Hugging Face Hub if they are not
    cached. Device, compute type and thread count come from ``WHISPER_DEVICE``,
    ``WHISPER_COMPUTE`` and ``WHISPER_THREADS``.
    """
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                MODEL_SIZE,
                device=os.getenv("WHISPER_DEVICE", "cpu"),
                compute_type=os.getenv("WHISPER_COMPUTE", "int8"),
                cpu_threads=int(os.getenv("WHISPER_THREADS", "4")),
            )
        return _model


def transcribe(audio: np.ndarray, language: str | None = None) -> tuple[str, str]:
    """Transcribe one audio segment.

    Args:
        audio: Float32 mono samples at 16 kHz, scaled to [-1, 1].
        language: Whisper language code (``"hi"``, ``"en"``, ...). ``None``, ``""`` or ``"auto"``
            lets Whisper detect it.

    Returns:
        ``(text, language)``: the transcript (empty if nothing was recognised) and the detected
        or forced language code. Segments shorter than 0.3 s are skipped and return ``""``.
    """
    if audio.size < SAMPLE_RATE * 0.3:
        return "", language or "auto"
    model = get_model()
    segments, info = model.transcribe(
        audio,
        language=None if language in (None, "", "auto") else language,
        task="transcribe",
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=HINGLISH_PROMPT,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language

"""Entry point for Hugging Face Spaces (Gradio SDK).

ZeroGPU Spaces insist on launching a Gradio app that contains an @spaces.GPU function, so Gradio
owns the server on port 7860 and our FastAPI routes (UI, REST API, WebSocket) are injected into it
ahead of Gradio's own routes. Transcription itself runs on CPU.
"""
import os
import sys
import threading

_default_unraisable = sys.unraisablehook


def _quiet_unraisable(u):
    # ZeroGPU's `spaces` package discards event loops; their cleanup raises a harmless
    # "Invalid file descriptor: -1" that would otherwise flood the logs.
    if isinstance(u.exc_value, ValueError) and "Invalid file descriptor" in str(u.exc_value):
        return
    _default_unraisable(u)


sys.unraisablehook = _quiet_unraisable

import gradio as gr

from app import stt
from app.db import init_db
from app.main import app as stt_app

try:
    import spaces

    gpu = spaces.GPU
except ImportError:  # running outside Hugging Face

    def gpu(fn):
        return fn


@gpu
def _placeholder(x: str) -> str:  # never used for real work
    return x


with gr.Blocks() as demo:
    gr.Markdown("The speech-to-text app is served at the site root.")
    box = gr.Textbox(visible=False)
    box.change(_placeholder, box, box)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=stt.get_model, daemon=True).start()  # warm the model
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        ssr_mode=False,  # SSR puts a Node proxy in front that hides our routes
        app_kwargs={"routes": list(stt_app.routes)},
    )

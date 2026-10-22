"""Entry point for Hugging Face Spaces (Gradio SDK): serves the FastAPI app on port 7860.

ZeroGPU Spaces refuse to start unless a Gradio app with an @spaces.GPU function exists,
so a tiny placeholder Gradio page is mounted at /gradio. Transcription itself runs on CPU.
"""
import os

import uvicorn

from app.main import app

try:
    import gradio as gr
    import spaces

    @spaces.GPU
    def _placeholder(x: str) -> str:  # never used for real work
        return x

    with gr.Blocks() as demo:
        gr.Markdown("The speech-to-text app is served at the site root: [open it](/).")
        t = gr.Textbox(visible=False)
        t.change(_placeholder, t, t)

    app = gr.mount_gradio_app(app, demo, path="/gradio")
except ImportError:  # running outside Hugging Face
    pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))

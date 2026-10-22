"""Entry point for Hugging Face Spaces (Gradio SDK): serves the FastAPI app on port 7860."""
import os

try:  # ZeroGPU Spaces refuse to start unless one @spaces.GPU function exists.
    import spaces

    @spaces.GPU
    def _zerogpu_placeholder():  # never called; transcription runs on CPU
        return None
except ImportError:  # running outside Hugging Face
    pass

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))

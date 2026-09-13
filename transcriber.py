"""Backwards-compat shim — real logic is in transcribers.py."""
import numpy as np
from transcribers import transcribe as _dispatch, preload_local


def load_model(size: str = "base"):
    preload_local(size)


def transcribe(audio: np.ndarray, model_size: str = "base",
               provider: str = "local") -> str:
    return _dispatch(audio, provider=provider, model=model_size)

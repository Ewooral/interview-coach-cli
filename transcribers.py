"""
Multi-provider speech-to-text dispatch.

Each transcriber exposes:
    transcribe(audio: np.ndarray, model: str) -> str

`audio` is a float32 mono numpy array at 16 kHz (what Whisper expects and what
`recorder.py` produces). Cloud providers get it re-encoded to WAV bytes.

Supported:
    - local       (openai-whisper, offline, no key)
    - groq        (Whisper on Groq LPU — very fast, cheap)
    - openai      (Whisper-1 + GPT-4o transcribe family)
    - deepgram    (Nova-3, streaming-quality accuracy)
"""
from __future__ import annotations

import io
import os
import numpy as np


SAMPLE_RATE = 16000


STT_PROVIDERS = {
    "local": {
        "env": None,
        "models": {
            "tiny":   "tiny   — <1s latency, low accuracy",
            "base":   "base   — quick, moderate accuracy",
            "small":  "small  — recommended for real calls (local)",
            "medium": "medium — slower, higher accuracy",
        },
        "default_model": "small",
    },
    "groq": {
        "env": "GROQ_API_KEY",
        "models": {
            "whisper-large-v3-turbo": "Fastest — sub-second on LPU (default)",
            "whisper-large-v3":       "Highest accuracy, still fast",
        },
        "default_model": "whisper-large-v3-turbo",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "models": {
            "whisper-1":            "Classic Whisper API",
            "gpt-4o-mini-transcribe": "Newer, cheaper, accurate (default)",
            "gpt-4o-transcribe":    "Most accurate cloud Whisper",
        },
        "default_model": "gpt-4o-mini-transcribe",
    },
    "deepgram": {
        "env": "DEEPGRAM_API_KEY",
        "models": {
            "nova-3":  "Fastest + most accurate (default)",
            "nova-2":  "Prior generation",
        },
        "default_model": "nova-3",
    },
}


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ─── Local Whisper ─────────────────────────────────────────────────────────
_local_model = None
_local_size = None


def _transcribe_local(audio: np.ndarray, model: str) -> str:
    global _local_model, _local_size
    import whisper
    if _local_model is None or _local_size != model:
        print(f"  [Loading Whisper {model} model...]")
        _local_model = whisper.load_model(model)
        _local_size = model
        print("  [Model ready]")
    result = _local_model.transcribe(audio, fp16=False, language="en")
    return result["text"].strip()


# ─── OpenAI-compatible (OpenAI + Groq) ─────────────────────────────────────
_openai_clients: dict = {}


def _transcribe_openai_compat(provider: str, audio: np.ndarray, model: str) -> str:
    from openai import OpenAI
    if provider not in _openai_clients:
        cfg = STT_PROVIDERS[provider]
        key = os.environ.get(cfg["env"])
        if not key:
            raise RuntimeError(f"Missing env var {cfg['env']}")
        kwargs = {"api_key": key}
        if "base_url" in cfg:
            kwargs["base_url"] = cfg["base_url"]
        _openai_clients[provider] = OpenAI(**kwargs)
    client = _openai_clients[provider]

    wav = _audio_to_wav_bytes(audio)
    resp = client.audio.transcriptions.create(
        model=model,
        file=("audio.wav", wav, "audio/wav"),
        language="en",
    )
    return resp.text.strip()


# ─── Deepgram ──────────────────────────────────────────────────────────────
def _transcribe_deepgram(audio: np.ndarray, model: str) -> str:
    import requests
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("Missing env var DEEPGRAM_API_KEY")

    wav = _audio_to_wav_bytes(audio)
    resp = requests.post(
        "https://api.deepgram.com/v1/listen",
        params={"model": model, "language": "en", "smart_format": "true"},
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": "audio/wav",
        },
        data=wav,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()


# ─── Dispatch ──────────────────────────────────────────────────────────────
def transcribe(audio: np.ndarray, provider: str = "local", model: str = "small") -> str:
    if audio is None or len(audio) == 0:
        return ""
    if provider == "local":
        return _transcribe_local(audio, model)
    if provider in ("openai", "groq"):
        return _transcribe_openai_compat(provider, audio, model)
    if provider == "deepgram":
        return _transcribe_deepgram(audio, model)
    raise ValueError(f"Unknown STT provider: {provider}")


def preload_local(model: str):
    """Warm up the local Whisper model so first turn isn't laggy."""
    _transcribe_local(np.zeros(SAMPLE_RATE // 10, dtype=np.float32), model)


def stt_key_status() -> dict:
    return {
        p: (True if cfg["env"] is None else bool(os.environ.get(cfg["env"])))
        for p, cfg in STT_PROVIDERS.items()
    }

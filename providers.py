"""
Multi-provider LLM support.

Each provider exposes:
    respond(transcript: str, history: list, system_prompt: str, model: str) -> str

`history` is a list of {"role": "user"|"assistant", "content": str}. The provider
mutates it in place with the new turn (user message then assistant reply) so the
caller can persist the running conversation.

Supported providers:
    - anthropic   (Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5)
    - openai      (GPT-5, GPT-5-mini, GPT-4o)
    - deepseek    (DeepSeek V4 chat, DeepSeek Reasoner) via OpenAI-compatible API
    - gemini      (Gemini 2.5 Pro / 2.5 Flash)
"""
from __future__ import annotations

import os


PROVIDERS = {
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "models": {
            "claude-opus-4-7":   "Claude Opus 4.7 — most capable",
            "claude-sonnet-4-6": "Claude Sonnet 4.6 — balanced (default)",
            "claude-haiku-4-5":  "Claude Haiku 4.5 — fastest, cheapest",
        },
        "default_model": "claude-sonnet-4-6",
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "models": {
            "gpt-5":       "GPT-5 — flagship",
            "gpt-5-mini":  "GPT-5 mini — fast + cheap",
            "gpt-4o":      "GPT-4o — mature, real-time",
        },
        "default_model": "gpt-5-mini",
    },
    "deepseek": {
        "env": "DEEPSEEK_API_KEY",
        "models": {
            "deepseek-chat":      "DeepSeek V4 chat — fast, very cheap",
            "deepseek-reasoner":  "DeepSeek Reasoner — chain-of-thought",
        },
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "models": {
            "gemini-2.5-pro":   "Gemini 2.5 Pro — most capable",
            "gemini-2.5-flash": "Gemini 2.5 Flash — fast",
        },
        "default_model": "gemini-2.5-flash",
    },
}


# ─── Anthropic ─────────────────────────────────────────────────────────────
_anthropic_client = None


def _respond_anthropic(transcript, history, system_prompt, model):
    global _anthropic_client
    import anthropic
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()

    history.append({"role": "user", "content": transcript})
    msg = _anthropic_client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=history,
    )
    reply = msg.content[0].text
    history.append({"role": "assistant", "content": reply})
    return reply


# ─── OpenAI + DeepSeek (OpenAI-compatible) ─────────────────────────────────
_openai_clients: dict = {}


def _openai_like(provider: str, transcript, history, system_prompt, model):
    from openai import OpenAI
    if provider not in _openai_clients:
        cfg = PROVIDERS[provider]
        key = os.environ.get(cfg["env"])
        if not key:
            raise RuntimeError(f"Missing env var {cfg['env']}")
        kwargs = {"api_key": key}
        if "base_url" in cfg:
            kwargs["base_url"] = cfg["base_url"]
        _openai_clients[provider] = OpenAI(**kwargs)
    client = _openai_clients[provider]

    history.append({"role": "user", "content": transcript})
    messages = [{"role": "system", "content": system_prompt}] + history
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1024,
    )
    reply = resp.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    return reply


# ─── Gemini ────────────────────────────────────────────────────────────────
_gemini_client = None


def _respond_gemini(transcript, history, system_prompt, model):
    global _gemini_client
    from google import genai
    from google.genai import types
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    history.append({"role": "user", "content": transcript})
    contents = []
    for m in history:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    resp = _gemini_client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=1024,
        ),
    )
    reply = resp.text
    history.append({"role": "assistant", "content": reply})
    return reply


# ─── Dispatch ──────────────────────────────────────────────────────────────
def respond(provider: str, model: str, transcript: str, history: list, system_prompt: str) -> str:
    if provider == "anthropic":
        return _respond_anthropic(transcript, history, system_prompt, model)
    if provider in ("openai", "deepseek"):
        return _openai_like(provider, transcript, history, system_prompt, model)
    if provider == "gemini":
        return _respond_gemini(transcript, history, system_prompt, model)
    raise ValueError(f"Unknown provider: {provider}")


# ─── Vision: analyse an image (screenshot) with a text prompt ──────────────
import base64
from pathlib import Path


def _read_image_b64(image_path: str | Path) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode()


def respond_with_image(provider: str, model: str, image_path: str | Path,
                       prompt: str, system_prompt: str = "") -> str:
    """Vision-model call. Returns text response about the image."""
    if provider == "anthropic":
        return _vision_anthropic(model, image_path, prompt, system_prompt)
    if provider in ("openai", "deepseek"):
        return _vision_openai_compat(provider, model, image_path, prompt, system_prompt)
    if provider == "gemini":
        return _vision_gemini(model, image_path, prompt, system_prompt)
    raise ValueError(f"Vision not implemented for provider: {provider}")


def _vision_anthropic(model, image_path, prompt, system_prompt):
    global _anthropic_client
    import anthropic
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    b64 = _read_image_b64(image_path)
    msg = _anthropic_client.messages.create(
        model=model,
        max_tokens=1500,
        system=system_prompt or (
            "You are a live coach analysing a screenshot the user just showed "
            "you during a conversation. Explain what's on screen, identify the "
            "task or question, and give the user something they can say or do "
            "in the next 30 seconds."
        ),
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return msg.content[0].text


def _vision_openai_compat(provider, model, image_path, prompt, system_prompt):
    from openai import OpenAI
    if provider not in _openai_clients:
        cfg = PROVIDERS[provider]
        key = os.environ.get(cfg["env"])
        if not key:
            raise RuntimeError(f"Missing env var {cfg['env']}")
        kwargs = {"api_key": key}
        if "base_url" in cfg:
            kwargs["base_url"] = cfg["base_url"]
        _openai_clients[provider] = OpenAI(**kwargs)
    client = _openai_clients[provider]
    b64 = _read_image_b64(image_path)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ],
    })
    resp = client.chat.completions.create(model=model, messages=messages, max_tokens=1500)
    return resp.choices[0].message.content


def _vision_gemini(model, image_path, prompt, system_prompt):
    global _gemini_client
    from google import genai
    from google.genai import types
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    image_bytes = Path(image_path).read_bytes()
    resp = _gemini_client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            max_output_tokens=1500,
        ),
    )
    return resp.text


def key_status() -> dict:
    """Return {provider: bool} — True if API key env var is set."""
    return {p: bool(os.environ.get(cfg["env"])) for p, cfg in PROVIDERS.items()}

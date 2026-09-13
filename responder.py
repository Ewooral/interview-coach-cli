"""Thin wrapper — routes to the chosen provider (see providers.py)."""
from providers import respond as _provider_respond


def respond(transcript: str, history: list, system_prompt: str,
            provider: str = "anthropic",
            model: str = "claude-sonnet-4-6") -> str:
    return _provider_respond(provider, model, transcript, history, system_prompt)

"""
Configuration: choose LLM + STT providers, store API keys in .env, remember choice.

Files:
    .env               — API keys (git-ignored). Loaded on startup.
    ~/.config/interview-coach/config.json — last-used choices
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from providers import PROVIDERS, key_status
from transcribers import STT_PROVIDERS, stt_key_status


PROJECT_DIR = Path(__file__).parent
ENV_PATH = PROJECT_DIR / ".env"
CONFIG_DIR = Path.home() / ".config" / "interview-coach"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_env():
    """Load .env into os.environ (does not override existing vars)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _write_env_var(key: str, value: str):
    """Append or replace a KEY=value line in .env (chmod 600)."""
    lines = []
    found = False
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    os.chmod(ENV_PATH, 0o600)
    os.environ[key] = value


def _pick(kind: str, catalog: dict, current: str | None) -> tuple[str, str]:
    """Interactive picker for a provider + model. Returns (provider, model)."""
    keys = list(catalog.keys())
    print(f"\n  Choose a {kind} provider:\n")
    for i, p in enumerate(keys, 1):
        env = catalog[p].get("env")
        if env is None:
            state = "✓ no key needed"
        elif os.environ.get(env):
            state = "✓ key set"
        else:
            state = "  needs key"
        marker = "  ← current" if p == current else ""
        print(f"    {i}. {p:<10} [{state}]{marker}")

    while True:
        raw = input(f"\n  Pick {kind} provider (1-{len(keys)}, Enter to keep current): ").strip()
        if raw == "" and current:
            provider = current
            break
        if raw.isdigit() and 1 <= int(raw) <= len(keys):
            provider = keys[int(raw) - 1]
            break
        print("  Invalid choice.")

    cfg = catalog[provider]
    models = list(cfg["models"].keys())
    print(f"\n  Choose a {provider} model:\n")
    for i, m in enumerate(models, 1):
        tag = "  (default)" if m == cfg["default_model"] else ""
        print(f"    {i}. {m:<26} — {cfg['models'][m]}{tag}")

    while True:
        raw = input(f"\n  Pick model (1-{len(models)}, Enter for default): ").strip()
        if raw == "":
            model = cfg["default_model"]
            break
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            model = models[int(raw) - 1]
            break
        print("  Invalid choice.")

    env_var = cfg.get("env")
    if env_var and not os.environ.get(env_var):
        print(f"\n  No {env_var} found.")
        key = input(f"  Paste your {provider} API key (or Enter to skip): ").strip()
        if key:
            _write_env_var(env_var, key)
            print(f"  Saved to {ENV_PATH} (chmod 600).")
        else:
            print(f"  Skipped — set {env_var} before running.")

    return provider, model


def interactive_setup() -> dict:
    """First-run wizard: pick LLM + STT provider/model, paste keys if missing."""
    print("\n" + "─" * 60)
    print("  CLI Interview Recorder — Setup")
    print("─" * 60)
    saved = load_config()

    print("\n" + "=" * 60)
    print("  STEP 1 of 2 — Language model (answers your interview questions)")
    print("=" * 60)
    llm_provider, llm_model = _pick("LLM", PROVIDERS, saved.get("provider"))

    print("\n" + "=" * 60)
    print("  STEP 2 of 2 — Speech-to-text (transcribes the audio)")
    print("=" * 60)
    stt_provider, stt_model = _pick("STT", STT_PROVIDERS, saved.get("stt_provider"))

    choice = {
        "provider": llm_provider,
        "model": llm_model,
        "stt_provider": stt_provider,
        "stt_model": stt_model,
    }
    save_config(choice)
    print(f"\n  Saved to {CONFIG_PATH}")
    print("─" * 60 + "\n")
    return choice


def show_status():
    print("\n  LLM providers:")
    for provider, has_key in key_status().items():
        marker = "✓" if has_key else "✗"
        env = PROVIDERS[provider]["env"]
        print(f"    {marker} {provider:<10} ({env})")

    print("\n  STT providers:")
    for provider, has_key in stt_key_status().items():
        marker = "✓" if has_key else "✗"
        env = STT_PROVIDERS[provider].get("env") or "no key needed"
        print(f"    {marker} {provider:<10} ({env})")

    saved = load_config()
    if saved:
        print(f"\n  Saved LLM: {saved.get('provider')} / {saved.get('model')}")
        print(f"  Saved STT: {saved.get('stt_provider', 'local')} / {saved.get('stt_model', 'small')}")
    print()

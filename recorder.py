import os
import queue
import subprocess
import threading
import time

import numpy as np
import sounddevice as sd

from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner


SAMPLE_RATE = 16000  # Whisper expects 16kHz

_console = Console()


# Distinct spinner style per speaker (visible cue: who's mic'd)
SPINNER_STYLES = {
    "you":         {"spinner": "bouncingBar", "style": "bold bright_cyan",   "icon": "🎙️",  "label": "YOU are speaking"},
    "interviewer": {"spinner": "earth",       "style": "bold bright_yellow", "icon": "👂", "label": "Listening to interviewer"},
    "unknown":     {"spinner": "dots",        "style": "bold white",         "icon": "🎧",  "label": "Recording"},
}


def _detect_system_monitor() -> str | None:
    try:
        out = subprocess.check_output(
            ["pw-cli", "ls", "Node"], stderr=subprocess.DEVNULL, text=True
        )
    except Exception:
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("node.name") and ".HiFi__hw_sofhdadsp__sink" in line:
            return line.split('=', 1)[1].strip().strip('"') + ".monitor"
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("node.name") and "alsa_output" in line and "sink" in line:
            return line.split('=', 1)[1].strip().strip('"') + ".monitor"
    return None


def _set_source(source: str) -> str:
    if source == "mic":
        os.environ.pop("PULSE_SOURCE", None)
        return "microphone"
    monitor = _detect_system_monitor()
    if not monitor:
        _console.print("  [yellow][Could not find system-audio monitor — falling back to mic][/]")
        os.environ.pop("PULSE_SOURCE", None)
        return "microphone (fallback)"
    os.environ["PULSE_SOURCE"] = monitor
    return "system audio"


def _live_status(speaker: str, extra: str = "") -> Live:
    """Build a Live spinner scoped to the recording session."""
    cfg = SPINNER_STYLES.get(speaker, SPINNER_STYLES["unknown"])
    text = Text(f" {cfg['icon']}  {cfg['label']}", style=cfg["style"])
    if extra:
        text.append(f"  {extra}", style="dim italic")
    return Live(
        Spinner(cfg["spinner"], text=text, style=cfg["style"]),
        console=_console,
        refresh_per_second=12,
        transient=True,
    )


def record_until_keypress(source: str = "mic", speaker: str = "you") -> np.ndarray:
    """Record from source until user presses Enter. Shows a per-speaker spinner."""
    label = _set_source(source)
    chunks = []

    def callback(indata, frames, t, status):
        chunks.append(indata.copy())

    stop_flag = threading.Event()

    def wait_for_enter():
        try:
            input()
        finally:
            stop_flag.set()

    reader = threading.Thread(target=wait_for_enter, daemon=True)
    reader.start()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        callback=callback), _live_status(
                            speaker, f"({label}) — press Enter to stop"
                        ):
        while not stop_flag.is_set():
            time.sleep(0.05)

    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks, axis=0).flatten()


def record_until_silence(
    source: str = "system",
    speaker: str = "interviewer",
    silence_threshold: float = 0.01,
    silence_duration: float = 1.5,
    max_duration: float = 90.0,
    min_speech_duration: float = 0.5,
) -> np.ndarray:
    """Auto-stop recording after `silence_duration` seconds of quiet."""
    label = _set_source(source)

    q: queue.Queue = queue.Queue()

    def callback(indata, frames, t, status):
        q.put(indata.copy())

    frame_ms = 100
    block = int(SAMPLE_RATE * frame_ms / 1000)

    chunks = []
    started_speaking = False
    speech_time = 0.0
    silence_time = 0.0

    cfg = SPINNER_STYLES.get(speaker, SPINNER_STYLES["unknown"])

    def build_spinner(started: bool, elapsed: float) -> Spinner:
        base = Text(f" {cfg['icon']}  {cfg['label']}", style=cfg["style"])
        base.append(f"  ({label})", style="dim")
        if started:
            base.append(f"  •  captured {elapsed:.1f}s", style="dim italic green")
        else:
            base.append("  •  waiting for speech…", style="dim italic")
        return Spinner(cfg["spinner"], text=base, style=cfg["style"])

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32",
        blocksize=block, callback=callback,
    ), Live(build_spinner(False, 0.0), console=_console,
            refresh_per_second=10, transient=True) as live:
        start = time.time()
        speech_seconds = 0.0
        while True:
            try:
                buf = q.get(timeout=0.5)
            except queue.Empty:
                if time.time() - start >= max_duration:
                    break
                continue

            rms = float(np.sqrt(np.mean(buf ** 2)))
            elapsed = time.time() - start

            if rms > silence_threshold:
                if not started_speaking:
                    started_speaking = True
                chunks.append(buf)
                speech_time += frame_ms / 1000
                speech_seconds = speech_time
                silence_time = 0.0
            elif started_speaking:
                chunks.append(buf)
                silence_time += frame_ms / 1000
                if silence_time >= silence_duration and speech_time >= min_speech_duration:
                    break

            live.update(build_spinner(started_speaking, speech_seconds))

            if elapsed >= max_duration:
                break

    if not chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(chunks, axis=0).flatten()

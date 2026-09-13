# Installation & distribution guide

Four ways to install Interview Coach CLI. Pick based on your audience.

| Method | Best for | Who has to have Python? |
|--------|----------|-------------------------|
| **pipx (recommended)** | End users on Linux/macOS with any Python 3.10+ | Yes — but pipx isolates the app in its own venv |
| **pip in a venv** | Developers hacking on the code | Yes |
| **Docker image** | CI, servers, users who don't want to install anything | No |
| **PyInstaller onefile binary** | Users with no Python at all | No |

---

## 1. pipx (recommended for end users)

`pipx` installs each CLI tool into its own private virtualenv, adds the entry-point commands to your PATH, and lets you upgrade or uninstall cleanly. This is the cleanest way to distribute a Python CLI.

### System dependencies (once)

```bash
# Linux (Ubuntu / Debian)
sudo apt install -y pipx portaudio19-dev pipewire-utils imagemagick
pipx ensurepath   # adds ~/.local/bin to PATH

# macOS
brew install pipx portaudio imagemagick
pipx ensurepath
```

### Install the app

From a locally built wheel:

```bash
cd /home/ewooral/personal/cli-interview-recorder
python -m build --wheel                    # produces dist/*.whl
pipx install ./dist/interview_coach_cli-0.3.0-py3-none-any.whl
```

Or (once published to PyPI):

```bash
pipx install interview-coach-cli
```

### Verify

```bash
which interview-recorder
# → ~/.local/pipx/venvs/interview-coach-cli/bin/interview-recorder
interview-recorder --status
```

### Upgrade / uninstall

```bash
pipx upgrade interview-coach-cli
pipx uninstall interview-coach-cli
```

---

## 2. pip in a venv (for developers)

If you're editing the code, this is the right path.

```bash
git clone <repo-url>
cd cli-interview-recorder
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                          # editable install
# or with extras:
pip install -e ".[gemini,dev]"
interview-recorder --help
```

Changes to `.py` files take effect immediately with the `-e` (editable) install.

---

## 3. Docker image (portable, no host Python)

The Dockerfile below packages the app so users can run it with `docker run`. Audio pass-through requires the host to have PulseAudio / PipeWire and X11.

### Dockerfile (add to repo root)

```dockerfile
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev pipewire-utils imagemagick pulseaudio-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir .

ENTRYPOINT ["interview-recorder"]
CMD ["--help"]
```

### Build + run

```bash
docker build -t interview-coach-cli .

# Run — mount audio + config + screens + .env
docker run --rm -it \
    -e PULSE_SERVER=unix:/run/user/1000/pulse/native \
    -v /run/user/1000/pulse/native:/run/user/1000/pulse/native \
    -v $HOME/.local/share/interview-coach:/root/.local/share/interview-coach \
    -v $HOME/.config/interview-coach:/root/.config/interview-coach \
    -v $(pwd)/.env:/app/.env:ro \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e DISPLAY=$DISPLAY \
    interview-coach-cli
```

Note: screen capture inside Docker on Linux needs X11 socket pass-through as shown. Audio needs PipeWire/Pulse pass-through.

---

## 4. PyInstaller onefile binary (no Python on target)

For users who can't install Python at all, PyInstaller freezes everything into a single executable. This is heavier (~200 MB per binary) and Whisper models still need to be downloaded at runtime.

### Build

```bash
pip install pyinstaller
pyinstaller --onefile \
  --name interview-recorder \
  --add-data ".env.example:." \
  --hidden-import langgraph.pregel \
  --hidden-import openai_whisper \
  main.py

# Output: dist/interview-recorder (Linux) or interview-recorder.exe (Windows)
```

Copy `dist/interview-recorder` to `~/.local/bin/` or share as an artifact. System deps (portaudio, imagemagick) still need to be installed on the target machine.

---

## Publishing to PyPI (project maintainer only)

To make `pip install interview-coach-cli` work globally:

```bash
# 1. Get a PyPI account: https://pypi.org/account/register/
# 2. Generate an API token in Account Settings

# 3. Install upload tools
pip install --upgrade build twine

# 4. Build
rm -rf dist build *.egg-info
python -m build

# 5. Upload to TestPyPI first (safe rehearsal)
python -m twine upload --repository testpypi dist/*
pipx install --index-url https://test.pypi.org/simple/ interview-coach-cli

# 6. Real PyPI
python -m twine upload dist/*
```

Bump `version` in `pyproject.toml` between releases (PyPI won't accept the same version twice).

---

## Bundled files

The wheel currently bundles:

| File | Why |
|------|-----|
| All top-level `.py` modules | The app code |
| `README.md` | Rendered on PyPI |
| `.env.example` | Users copy this to `.env` |
| `LICENSE` | Legal |

Whisper model weights are downloaded **at first use** to `~/.cache/whisper/` — they are not bundled (they'd bloat the wheel from ~50 KB to ~150 MB+).

---

## Post-install

Regardless of install method:

```bash
# 1. Configure API keys and models
cp .env.example .env && chmod 600 .env && $EDITOR .env
# or use the interactive wizard:
interview-recorder --setup

# 2. Create your profile
interview-recorder --onboard

# 3. Run a session
interview-recorder
```

---

## Uninstall / cleanup

```bash
# pipx
pipx uninstall interview-coach-cli

# pip in venv
rm -rf .venv

# state (profiles, sessions, screens) — remove manually if you want them gone
rm -rf ~/.local/share/interview-coach ~/.config/interview-coach
```

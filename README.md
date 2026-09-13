# Interview Coach CLI

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/interview-coach-cli)](https://pypi.org/project/interview-coach-cli/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/Ewooral?style=social)](https://github.com/sponsors/Ewooral)

Voice-driven real-time coaching for any high-stakes conversation — interview, sales discovery, academic call, medical consult, whatever. Captures mic or system audio (Zoom / Teams / Meet), transcribes with Whisper (local, Groq, OpenAI, or Deepgram), and answers with your chosen LLM (Claude / GPT / DeepSeek / Gemini) in a structured `SAY THIS / ANALYSIS / WHY IT WORKS` format.

Two-way memory. Multi-profile. Per-conversation meeting plans with agenda, prepared answers, and traps to avoid. Live web-research briefings on your counterparty. Screen capture with vision-LLM analysis for coding challenges and diagrams. LangGraph-based routing that picks a cheap or premium model per turn.

---

## Table of contents

1. [Quick start](#quick-start)
2. [Installation](#installation)
3. [First-run configuration](#first-run-configuration)
4. [Concepts](#concepts)
5. [Running a session](#running-a-session)
6. [Every hotkey, explained](#every-hotkey-explained)
7. [Command-line flags](#command-line-flags)
8. [Meeting plans in depth](#meeting-plans-in-depth)
9. [Research module](#research-module)
10. [Screen capture](#screen-capture)
11. [LLM providers](#llm-providers)
12. [STT (transcription) providers](#stt-providers)
13. [Data locations](#data-locations)
14. [Troubleshooting](#troubleshooting)

---

## Quick start

```bash
# One-time system dependencies (Ubuntu / Debian):
sudo apt install -y portaudio19-dev pipewire-utils imagemagick

# Copy the env template, then paste your API keys into `.env`
cp .env.example .env
chmod 600 .env
$EDITOR .env

# OR: interactive wizard fills .env for you
interview-recorder --setup

# Then create your profile
interview-recorder --onboard

# Optional but recommended: build a meeting plan and briefing before the call
interview-recorder --make-plan
interview-recorder --research

# Then run the session
interview-recorder
```

**Which keys do I actually need?** See [`.env.example`](.env.example) — it lists every env var, groups them by feature, shows recommended combos, and links to where to get each key.

---

## Installation

```bash
# 1. Python dependencies (uses the shared venv in this workspace)
source /home/ewooral/personal/venv-py3.13/bin/activate
cd /home/ewooral/personal/cli-interview-recorder
pip install -r requirements.txt

# 2. Global launcher (installs once)
# Already installed at ~/.local/bin/interview-recorder — usable from any directory.

# 3. System deps
sudo apt install -y portaudio19-dev pipewire-utils imagemagick
# portaudio: mic capture · pipewire: system-audio monitor · imagemagick: screen capture
```

---

## First-run configuration

Two setup wizards run separately:

### Provider setup

```bash
interview-recorder --setup
```

- Pick an LLM provider (Anthropic / OpenAI / DeepSeek / Gemini)
- Pick an STT provider (local Whisper / Groq / OpenAI / Deepgram)
- Paste API keys — stored in `.env` (chmod 600) inside the repo
- Optional: paste **Tavily API key** for the research feature (`TAVILY_API_KEY` in the same `.env`)

### Profile onboarding

```bash
interview-recorder --onboard
```

Interactive wizard asks for:
- Name and pronouns
- Background (one paragraph — what you've done)
- Target role / opportunity you're preparing for
- Strengths to lean on (bullet list)
- Weaknesses to defuse (bullet list)
- Extra context (any freeform notes)

The profile becomes the persistent "who you are" that the coach uses across every session.

Check status any time:
```bash
interview-recorder --status
```

---

## Concepts

The app has four persistent objects:

| Object | What it is | Lifespan |
|--------|-----------|----------|
| **Profile** | You. Name, background, strengths, weaknesses. | Long-lived. Multiple profiles supported; switch with `--onboard`. |
| **Template** | Style of coaching. `academic-phd` / `tech-interview` / `product-management` / `sales-discovery` / `medical-residency` / `general`. | Choose per session. |
| **Meeting plan** | Game plan for one specific upcoming conversation: sections, answers to prep, questions to ask, traps to avoid, briefing on counterparty. | Attach to any number of sessions. |
| **Session** | The actual live conversation — transcripts + coach responses + which plan/template were used. | Autosaved every turn to SQLite. |

At session start you pick: profile (defaults to active) → template → plan (optional) → session (new or continue).

---

## Running a session

```bash
interview-recorder                 # standard flow: pick session → interview loop
interview-recorder --live          # start in auto-stop mode (system audio + VAD)
interview-recorder --new-session   # skip session picker, straight into a fresh one
interview-recorder --no-plan       # skip the plan picker this run
```

At each turn you either **record audio** (default), or **type** the transcript (`t`), or **capture a screenshot** (`c`), or advance the plan (`§`), or fetch fresh research (`b`), or inject live context (`x`). All of these produce a structured coach response in the same format.

### Structured coach output

Every turn produces three colored panels:

- 💬 **SAY THIS** (green) — exact words to speak in the next 30-90 seconds
- 🧠 **ANALYSIS** (blue) — subtext, traps, what the counterparty is really asking
- ✨ **WHY IT WORKS** (magenta) — one-line justification for the framing

If a meeting plan is active, the coach also references the current agenda section, flags when you're about to hit a listed trap, and reminds you of unanswered questions from your plan.

Every turn also shows a routing badge:

```
⚙  turn=question · tier=default · fresh — question needs briefing-informed answer
```

This tells you which model tier the LangGraph coach chose (cheap / default / premium), the turn type it detected, and whether a prepared answer was matched.

---

## Every hotkey, explained

At the turn prompt:

| Key | Action | Notes |
|-----|--------|-------|
| **Enter** | Start recording with the current source | Mic if speaker=you, system audio if speaker=interviewer |
| **y** | Switch to your voice (mic) | Speaker becomes "you" |
| **i** | Switch to interviewer (system audio) | Speaker becomes "interviewer" |
| **l** | Live mode — system audio + auto-stop on silence | For hands-free Zoom / Teams |
| **t** | Type or paste text as a transcript | Use when audio fails or to paste from chat/email. Prompts for speaker after. |
| **x** | Add extra context to the coach's memory | Appends to the system prompt for the rest of the session. E.g. "she just mentioned Anthropic — adjust framing." |
| **c** | Screen capture → vision LLM analysis | For coding questions, whiteboard diagrams, forms. Uses your active LLM in vision mode. |
| **p** | Show the current meeting plan | Full readout: agenda, answers, questions, traps, commitments, briefing. |
| **§** or **s** | Advance to next agenda section | Only when a plan is active. Section marker is prepended to future turns. |
| **b** | Fetch fresh research on someone | Prompts for name + affiliation. Attaches briefing to the current plan and re-renders system prompt. |
| **n** | Start a new session | Same profile / template / plan, fresh history. |
| **r** | Rename current session | For organization in the sessions picker. |
| **q** | Quit | Session is already saved. |

---

## Command-line flags

```bash
interview-recorder [flags]
```

### Setup & configuration

| Flag | Purpose |
|------|---------|
| `--setup` | Provider + model + API key wizard |
| `--status` | Show which providers have keys configured |
| `--onboard` | Profile wizard (create / edit / switch) |
| `--edit-profile` | Edit the active profile |
| `--make-plan` | Build a meeting plan interactively |
| `--research` | Research a counterparty and attach a briefing to a plan |

### Session behavior

| Flag | Purpose |
|------|---------|
| `--new-session` | Skip the session picker |
| `--no-plan` | Skip the meeting-plan picker this run |
| `--live` | Start with system-audio + auto-stop on silence |
| `--source {mic,system}` | Force a specific audio source |
| `--silence N` | Silence duration in live mode (default 1.5s) |
| `--speaker {you,interviewer,unknown}` | Default speaker for this session |

### Model choices

| Flag | Purpose |
|------|---------|
| `--provider {anthropic,openai,deepseek,gemini}` | Override the saved LLM provider |
| `--llm-model MODEL_ID` | Override the saved LLM model |
| `--stt {local,groq,openai,deepgram}` | Override the saved STT provider |
| `--stt-model MODEL_ID` | Override the saved STT model |
| `--model {tiny,base,small,medium}` | Shortcut for local Whisper model size |

### Debug / A/B

| Flag | Purpose |
|------|---------|
| `--no-graph` | Bypass the LangGraph coach and use the direct single-call path |
| `--template ID` | Skip the template picker |
| `--mode {interview,meeting,general}` | Coaching mode preset |

---

## Meeting plans in depth

A meeting plan is a game plan for one specific conversation. When active, it steers the coach's every response.

### Creating a plan

```bash
interview-recorder --make-plan
```

The wizard asks for:

- **Title** — how it appears in the picker (e.g., "Call with Dr. Watkins — Oxford")
- **Counterparty** — name and role of who you're talking with
- **Purpose** — one paragraph on what you want out of this conversation
- **Duration** — planned minutes
- **Sections** — ordered agenda blocks. Each has a title, minutes, and goal.
- **Answers to prepare** — questions you expect to be asked
- **Questions to ask** — things you want to learn from them
- **Traps to avoid** — mistakes to preempt
- **Commitments** — concrete outcomes you want to leave with
- **Notes** — freeform

### How plans influence the coach

When you attach a plan to a session, the coach:

- Sees the entire plan in its system prompt on every turn
- References the current section (`[CURRENT SECTION §N: title]` is prefixed to your transcript before it reaches the LLM)
- Points out when your prepared answer applies to the interviewer's question
- Flags when you're walking into a listed trap
- Reminds you of unasked questions from your list
- Suggests advancing the section when the current one is winding down

### Managing plans

- **List:** shown in the picker when starting a session (or press `p` mid-session)
- **Delete:** `d<n>` in the picker
- **Rename / edit fields:** currently by running `interview-recorder --make-plan` and picking to overwrite, or editing directly in SQLite

---

## Research module

Given a counterparty's name + optional affiliation, the app runs three parallel searches and synthesizes a briefing.

```bash
interview-recorder --research
```

Sources (all optional; each degrades gracefully):

| Source | What it provides | Cost |
|--------|------------------|------|
| **Tavily API** | Web search results, news, blog posts, talks, LinkedIn public info | ~$1/1000 queries |
| **Semantic Scholar** | Academic papers (title, abstract, year, authors) | Free (public API) |
| **GitHub API** | Bio, repos, followers, code presence | Free (60 req/hr without token) |

An LLM synthesis pass turns raw results into a structured briefing:

- Snapshot (30-second essentials)
- Recent focus (last 2 years)
- Signature themes
- Tone and style
- Conversation openings (3-5 questions to raise)
- Watch-outs
- Sources cited

The briefing is attached to the meeting plan and injected into the coach's system prompt. Every turn from that point on has full context on who you're talking to.

### Mid-session research (`b`)

If someone new joins the call, press `b`, type their name and affiliation, and the coach fetches + synthesizes a briefing in ~15-20 seconds. Immediately available in subsequent turns.

### Tavily key

Sign up at https://tavily.com — free tier is 1,000 queries/month. Paste into `.env`:

```bash
echo "TAVILY_API_KEY=tvly-your-key-here" >> .env
```

---

## Screen capture

For coding questions, whiteboard diagrams, forms, reference documents:

Press `c` at the turn prompt → choose:
- **r** — region select (drag to define an area)
- **f** — full screen
- **w** — click a window (captured whole)

The screenshot is saved to `~/.local/share/interview-coach/screens/<session_id>/<timestamp>.png` and sent along with your active system prompt to the LLM's vision endpoint (Claude / GPT / Gemini all support it).

You'll be prompted to optionally type a specific question; if you leave it blank, the default prompt is: *"Analyse this screenshot. Identify what's on screen. If it's a question or task, give me a clear answer or approach I can say in the next 30-60 seconds."*

The result appears in a bright-cyan **📸 SCREEN ANALYSIS** panel and is saved to session history for reference in future turns.

---

## LLM providers

Configure in `--setup`. All models can be overridden per-session with `--llm-model`.

| Provider | Env var | Cheap tier | Default tier | Premium tier |
|----------|---------|------------|--------------|--------------|
| Anthropic | `ANTHROPIC_API_KEY` | claude-haiku-4-5 | claude-sonnet-4-6 | claude-opus-4-7 |
| OpenAI | `OPENAI_API_KEY` | gpt-5-mini | gpt-5-mini | gpt-5 |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat | deepseek-chat | deepseek-reasoner |
| Gemini | `GEMINI_API_KEY` | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-pro |

**Cheapest usable choice:** DeepSeek `deepseek-chat` (~20× cheaper than Claude Haiku). Within Anthropic, Haiku 4.5 is the cost-effective sweet spot.

The LangGraph coach picks the cheap tier for small talk and matched-prep answers; the default tier for real questions.

Cost estimate: ~$0.001-0.02 per turn with default tier on Claude Sonnet.

---

## STT providers

Configure in `--setup`. All can be overridden with `--stt`.

| Provider | Default model | Latency | Cost |
|----------|---------------|---------|------|
| **local** | whisper base (or your choice) | 1-5s local CPU | Free |
| **groq** | whisper-large-v3-turbo | ~0.5s | Free tier 7200s/min; then ~$0.02/hr |
| **openai** | gpt-4o-mini-transcribe | ~1-2s | ~$0.006/min |
| **deepgram** | nova-3 | Streaming | ~$0.0043/min |

Local Whisper needs a `.bin` model set in Settings. Groq is recommended for cost + speed. Deepgram is the only true streaming backend.

Language: pass `--language en` (default). Whisper supports 100+ languages.

---

## Data locations

| Path | Contents | Lifespan |
|------|----------|----------|
| `.env` in repo | API keys (chmod 600, gitignored) | Persistent |
| `~/.config/interview-coach/config.json` | Last-used provider + model | Persistent |
| `~/.local/share/interview-coach/sessions.db` | Profiles, sessions, messages, plans, briefings | Persistent |
| `~/.local/share/interview-coach/screens/<session_id>/` | Captured PNG screenshots | Persistent |

Back up by copying `sessions.db` + the screens folder + `.env`.

---

## Troubleshooting

**"No audio captured"**
- Check mic volume: `wpctl status | grep Microphone`. Boost to 100%: `wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 1.0`
- Speak closer to the mic; internal laptop mics need less than 30cm distance
- On Linux, ensure PipeWire is running: `pgrep -af pipewire`

**System audio capture fails on Bluetooth**
- The app dynamically resolves the default sink via `wpctl inspect @DEFAULT_AUDIO_SINK@`. If a new Bluetooth device just connected, kill and restart — sometimes PipeWire caches the previous sink.

**Whisper hallucinates "Thank you" repeatedly**
- Audio is too quiet for the model. Switch to a bigger local model (`--model small` or `medium`), or use Groq/OpenAI which handle low-level audio better.

**Coach responses are slow**
- Check `⚙ tier=` on each turn. If everything says `tier=default`, small talk should be `tier=cheap`. Might be worth restarting to reset the LangGraph state.
- Try `--no-graph` to A/B compare — if faster, the classifier is misfiring.

**"Groq selected but no Groq key set"**
- The key isn't in `.env`. Run `interview-recorder --setup` and paste.

**Provider key seemingly saves but nothing changes**
- On Linux, the `keyring` crate needs a running secret-service daemon. This CLI uses `.env` directly and doesn't have that issue. The Tauri UI version did — irrelevant here.

**Screen capture asks for a window forever**
- ImageMagick's `import` blocks waiting for a click when no region is passed. Click any window (or click-and-drag for a region). Ctrl+C to cancel.

**Semantic Scholar 429s during research**
- Public API is rate-limited. The pipeline still delivers a useful briefing from web + GitHub + LLM synthesis. If you need paper coverage, sign up for a free Semantic Scholar API key and add `SEMANTIC_SCHOLAR_API_KEY` to `.env` (requires a small code tweak).

---

## Where things live in the code

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI entry point, argument parsing, turn loop |
| `recorder.py` | Audio capture (mic + system audio via PipeWire monitor) |
| `transcribers.py` | Multi-backend STT dispatch |
| `providers.py` | Multi-provider LLM dispatch + vision endpoints |
| `coach_graph.py` | LangGraph state machine for turn routing |
| `responder.py` | Thin wrapper (legacy) |
| `config.py` | .env loader + settings storage |
| `sessions.py` | SQLite schema + session persistence |
| `profile_store.py` | Profile CRUD |
| `templates.py` | Coaching prompt templates + `render_prompt(template, profile, plan)` |
| `meeting_plans.py` | MeetingPlan CRUD + `render_plan_for_prompt` |
| `plan_wizard.py` | Interactive plan creation and picker |
| `onboarding.py` | Profile wizard |
| `research.py` | Tavily + Semantic Scholar + GitHub + LLM synthesis |
| `screen_capture.py` | Multi-backend screenshot |

---

## License

MIT. See `LICENSE`.

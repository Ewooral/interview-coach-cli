#!/usr/bin/env python3
"""
Interview Coach CLI
-------------------
Record audio (mic or system), transcribe with a chosen STT provider, answer with
a chosen LLM. Multi-profile, multi-template, session-persistent.

Usage:
    interview-recorder --setup           # LLM + STT provider wizard
    interview-recorder --onboard         # profile wizard
    interview-recorder --status          # provider key status
    interview-recorder                   # session picker then interview loop
    interview-recorder --live            # Zoom/Teams system-audio mode
    interview-recorder --new-session --template tech-interview
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import load_env, load_config, interactive_setup, show_status, PROVIDERS

load_env()

from recorder import record_until_keypress, record_until_silence
from transcribers import STT_PROVIDERS, transcribe as stt_transcribe, preload_local
from responder import respond
import sessions as sess
import profile_store
from templates import render_prompt, TEMPLATES, list_template_choices
from onboarding import pick_or_create_profile, pick_template, edit_profile_wizard
import meeting_plans
from plan_wizard import pick_plan, create_plan_wizard
import screen_capture
from providers import respond_with_image
from coach_graph import run_turn as coach_run_turn

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


APP_NAME = "Interview Coach"
APP_VERSION = "0.3.0"


def parse_reply(reply: str) -> dict:
    """Split the LLM reply into SAY / ANALYSIS / WHY sections."""
    sections = {"SAY": "", "ANALYSIS": "", "WHY": ""}
    pattern = re.compile(r"^\s*(SAY|ANALYSIS|WHY)\s*:\s*$", re.MULTILINE | re.IGNORECASE)
    matches = list(pattern.finditer(reply))
    if not matches:
        sections["SAY"] = reply.strip()
        return sections
    for i, m in enumerate(matches):
        key = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(reply)
        sections[key] = reply[start:end].strip()
    return sections


def print_banner(profile, template_id, live, llm, stt):
    header = Text()
    header.append(f"  {APP_NAME} ", style="bold cyan")
    header.append(f"v{APP_VERSION}\n", style="dim")
    header.append("  Profile:  ", style="dim")
    header.append(f"{profile['name']}", style="bold yellow")
    if profile["target_role"]:
        header.append(f"  →  {profile['target_role']}", style="yellow")
    header.append(f"\n  Template: ", style="dim")
    header.append(f"{TEMPLATES[template_id]['label']}", style="magenta")
    header.append(f"\n  Source:   ", style="dim")
    header.append("SYSTEM AUDIO (live)" if live else "MICROPHONE", style="bold magenta")
    header.append(f"\n  STT:      ", style="dim")
    header.append(f"{stt[0]} / {stt[1]}", style="green")
    header.append(f"\n  LLM:      ", style="dim")
    header.append(f"{llm[0]} / {llm[1]}", style="green")
    console.print(Panel(header, border_style="cyan", padding=(1, 2)))


def show_transcript(transcript: str, speaker: str, name: str, turn: int):
    label_map = {
        "interviewer": ("👂 INTERVIEWER", "bright_yellow"),
        "you":         (f"🎙️ {name.upper()}", "bright_cyan"),
        "unknown":     ("🎧 HEARD", "bright_white"),
    }
    label, style = label_map[speaker]
    console.print(
        Panel(
            Text(transcript, style="white"),
            title=f"[bold {style}]{label}[/]",
            subtitle=f"[dim]turn {turn}[/]",
            border_style=style,
            padding=(0, 2),
        )
    )


def show_reply(sections: dict, turn: int):
    say = sections.get("SAY", "").strip()
    analysis = sections.get("ANALYSIS", "").strip()
    why = sections.get("WHY", "").strip()

    if say:
        console.print(
            Panel(
                Text(say, style="bold white"),
                title="[bold bright_green]💬 SAY THIS[/]",
                subtitle=f"[dim]turn {turn} — speak this out loud[/]",
                border_style="bright_green",
                padding=(1, 2),
            )
        )
    if analysis:
        console.print(
            Panel(
                Text(analysis, style="white"),
                title="[bold bright_blue]🧠 ANALYSIS[/]",
                border_style="blue",
                padding=(0, 2),
            )
        )
    if why:
        console.print(
            Panel(
                Text(why, style="italic"),
                title="[bold magenta]✨ WHY IT WORKS[/]",
                border_style="magenta",
                padding=(0, 2),
            )
        )


def _default_session_title(template_id: str) -> str:
    from datetime import datetime
    label = TEMPLATES[template_id]["label"]
    return f"{label} — {datetime.now().strftime('%b %d %H:%M')}"


def pick_session(profile_id: int, template_id: str, llm_provider: str, llm_model: str):
    rows = sess.list_sessions(limit=15)

    def _new():
        title = console.input(
            f"  New session title [dim](Enter for '{_default_session_title(template_id)}')[/]: "
        ).strip() or _default_session_title(template_id)
        sid = sess.create_session(title, template_id, llm_provider, llm_model)
        # Link session to profile + template (columns added by profile_store migration)
        from sessions import _connect
        with _connect() as conn:
            conn.execute("UPDATE sessions SET profile_id = ?, template_id = ? WHERE id = ?",
                         (profile_id, template_id, sid))
        console.print(f"[green]  ✓ New session #{sid}: {title}[/]\n")
        return sid, []

    if not rows:
        return _new()

    table = Table(title="Saved sessions", border_style="dim")
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Title", style="white")
    table.add_column("Template", style="magenta")
    table.add_column("Turns", justify="right", style="green")
    table.add_column("Last updated", style="dim")
    for i, r in enumerate(rows, 1):
        table.add_row(str(i), r["title"], r["mode"], str(r["turns"]),
                      r["updated_at"].replace("T", " "))
    console.print(table)

    while True:
        raw = console.input(
            "\n[bold]Pick session[/]: [cyan]<number>[/]=continue  "
            "[bold green]n[/]=new  [bold red]d<number>[/]=delete  "
            "[dim](Enter=new)[/] ▸ "
        ).strip().lower()
        if raw in ("", "n"):
            return _new()
        if raw.startswith("d") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            if 0 <= idx < len(rows):
                sess.delete_session(rows[idx]["id"])
                console.print(f"[red]  ✗ Deleted '{rows[idx]['title']}'[/]\n")
                return pick_session(profile_id, template_id, llm_provider, llm_model)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(rows):
                sid = rows[idx]["id"]
                history = sess.load_messages(sid)
                console.print(
                    f"[green]  ✓ Continuing '{rows[idx]['title']}' "
                    f"— {len(history)} messages loaded[/]\n"
                )
                return sid, history
        console.print("[yellow]  Invalid choice.[/]")


def _run_research_cli(args):
    """`interview-recorder --research` — attach a briefing to an existing plan."""
    from plan_wizard import pick_plan
    import research

    active = profile_store.get_active_profile()
    profile_id = active["id"] if active else None

    console.print(Panel(
        Text(
            "Research a counterparty and attach a briefing to a meeting plan.\n"
            "Sources: web (Tavily), academic papers (Semantic Scholar), GitHub.",
            style="white",
        ),
        title="[bold bright_cyan]🔎 Research[/]",
        border_style="bright_cyan", padding=(1, 2),
    ))

    plan_id = pick_plan(profile_id=profile_id)
    if plan_id is None:
        console.print("[yellow]  No plan selected.[/]")
        return
    plan = meeting_plans.get_plan(plan_id)

    name = console.input(
        f"[cyan]  Counterparty name to research[/] "
        f"[dim](Enter for '{(plan.get('counterparty') or '').split(',')[0]}')[/]: "
    ).strip() or (plan.get("counterparty") or "").split(",")[0].strip()
    if not name:
        console.print("[red]  Need a name to research.[/]")
        return
    affiliation = console.input(
        "[cyan]  Affiliation / institution / company[/] [dim](optional)[/]: "
    ).strip()

    llm_provider, llm_model = resolve_llm(args)

    with console.status("[cyan]  Gathering sources...[/]", spinner="dots"):
        raw = research.research_counterparty(name, affiliation)
    console.print(
        f"[dim]  Web: {len(raw.by_source('web'))} · "
        f"Papers: {len(raw.by_source('semantic-scholar'))} · "
        f"GitHub: {len(raw.by_source('github'))} · "
        f"Errors: {len(raw.errors)}[/]"
    )
    for err in raw.errors:
        console.print(f"[yellow]    ! {err}[/]")

    with console.status("[cyan]  Synthesising briefing...[/]", spinner="dots"):
        briefing = research.synthesize_briefing(raw, llm_provider, llm_model)

    console.print(Panel(
        Text(briefing.strip(), style="white"),
        title="[bold bright_cyan]📄 Briefing[/]",
        border_style="bright_cyan", padding=(1, 2),
    ))

    meeting_plans.update_plan(
        plan_id,
        briefing=briefing,
        raw_research_json=json.dumps(raw.to_dict()),
    )
    console.print(f"\n[green]  ✓ Briefing attached to plan #{plan_id}.[/]")


def resolve_llm(args):
    saved = load_config()
    provider = args.provider or saved.get("provider") or "anthropic"
    if provider not in PROVIDERS:
        raise SystemExit(f"Unknown LLM provider: {provider}")
    if args.llm_model:
        model = args.llm_model
    elif saved.get("provider") == provider and saved.get("model"):
        model = saved["model"]
    else:
        model = PROVIDERS[provider]["default_model"]
    env = PROVIDERS[provider]["env"]
    if not os.environ.get(env):
        raise SystemExit(
            f"\n  ✗ No API key for LLM provider {provider} — env var {env} not set.\n"
            f"  Run:  interview-recorder --setup\n"
        )
    return provider, model


def resolve_stt(args):
    saved = load_config()
    provider = args.stt or saved.get("stt_provider") or "local"
    if provider not in STT_PROVIDERS:
        raise SystemExit(f"Unknown STT provider: {provider}")
    if args.stt_model:
        model = args.stt_model
    elif saved.get("stt_provider") == provider and saved.get("stt_model"):
        model = saved["stt_model"]
    elif args.model and provider == "local":
        model = args.model
    else:
        model = STT_PROVIDERS[provider]["default_model"]
    env = STT_PROVIDERS[provider].get("env")
    if env and not os.environ.get(env):
        raise SystemExit(
            f"\n  ✗ No API key for STT provider {provider} — env var {env} not set.\n"
            f"  Run:  interview-recorder --setup\n"
        )
    return provider, model


def main():
    parser = argparse.ArgumentParser(
        prog="interview-recorder",
        description=f"{APP_NAME} v{APP_VERSION} — voice-driven interview coach",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")

    parser.add_argument("--template", choices=list(TEMPLATES.keys()), default=None,
                        help="Interview template (skips picker)")
    parser.add_argument("--live", action="store_true",
                        help="Capture SYSTEM AUDIO with auto-stop on silence")
    parser.add_argument("--source", choices=["mic", "system"], default=None)
    parser.add_argument("--silence", type=float, default=1.5)
    parser.add_argument("--speaker", choices=["you", "interviewer", "unknown"], default=None)

    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--stt", choices=list(STT_PROVIDERS.keys()), default=None)
    parser.add_argument("--stt-model", default=None)
    parser.add_argument("--model", choices=["tiny", "base", "small", "medium"], default=None,
                        help="Shortcut: local Whisper model size")

    parser.add_argument("--new-session", action="store_true",
                        help="Skip session picker; start a fresh conversation")
    parser.add_argument("--setup", action="store_true",
                        help="Provider setup wizard (API keys + models)")
    parser.add_argument("--onboard", action="store_true",
                        help="Profile wizard (create / edit / switch)")
    parser.add_argument("--edit-profile", action="store_true",
                        help="Edit the active profile")
    parser.add_argument("--make-plan", action="store_true",
                        help="Build a meeting plan (structure + questions + traps)")
    parser.add_argument("--no-plan", action="store_true",
                        help="Skip the meeting-plan picker this run")
    parser.add_argument("--research", action="store_true",
                        help="Research a counterparty and attach briefing to a plan")
    parser.add_argument("--no-graph", action="store_true",
                        help="Bypass the LangGraph coach; use the direct single-call path")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        show_status()
        return
    if args.setup:
        interactive_setup()
        return
    if args.onboard:
        pick_or_create_profile()
        return
    if args.edit_profile:
        active = profile_store.get_active_profile()
        if not active:
            console.print("[yellow]  No active profile — run --onboard first.[/]")
            return
        edit_profile_wizard(active["id"])
        return
    if args.make_plan:
        active = profile_store.get_active_profile()
        pid_owner = active["id"] if active else None
        create_plan_wizard(profile_id=pid_owner)
        return
    if args.research:
        _run_research_cli(args)
        return

    llm_provider, llm_model = resolve_llm(args)
    stt_provider, stt_model = resolve_stt(args)

    # ── Profile ──────────────────────────────────────────────────────────
    profile_row = profile_store.get_active_profile()
    if not profile_row:
        profile_id = pick_or_create_profile()
        profile_row = profile_store.get_profile(profile_id)
    profile = dict(profile_row)

    # ── Template ─────────────────────────────────────────────────────────
    template_id = args.template or pick_template(default="academic-phd")

    # ── Meeting Plan (optional per-conversation game plan) ───────────────
    plan_id = None
    plan = None
    if not args.no_plan:
        console.print("\n[bold cyan]  Optional: attach a meeting plan[/]")
        console.print("[dim]  A plan lets the coach reference sections, traps, and target questions live.[/]")
        plan_id = pick_plan(profile_id=profile["id"])
        if plan_id:
            plan = meeting_plans.get_plan(plan_id)

    system_prompt = render_prompt(template_id, profile, plan=plan)
    current_section_idx = 0  # tracks which agenda section is active (0-based)

    source = args.source or ("system" if args.live else "mic")
    default_speaker = "interviewer" if source == "system" else "you"
    speaker = args.speaker or default_speaker

    print_banner(profile, template_id, args.live,
                 (llm_provider, llm_model), (stt_provider, stt_model))
    if stt_provider == "local":
        preload_local(stt_model)

    # ── Session ──────────────────────────────────────────────────────────
    if args.new_session:
        title = _default_session_title(template_id)
        session_id = sess.create_session(title, template_id, llm_provider, llm_model)
        from sessions import _connect
        with _connect() as conn:
            conn.execute("UPDATE sessions SET profile_id = ?, template_id = ? WHERE id = ?",
                         (profile["id"], template_id, session_id))
        history = []
        console.print(f"[green]  ✓ New session #{session_id}: {title}[/]\n")
    else:
        session_id, history = pick_session(profile["id"], template_id, llm_provider, llm_model)

    # ── Interview loop ───────────────────────────────────────────────────
    turn = len([m for m in history if m["role"] == "user"]) + 1
    current_source = source
    current_speaker = speaker
    def _handle_screen_capture(session_id, profile, template_id, plan,
                                current_section_idx, llm_provider, llm_model, history):
        """Grab a screenshot and hand it to the vision LLM."""
        console.print()
        raw = console.input(
            "[bold]Capture mode:[/] [bold cyan]r[/]=region-select  [bold cyan]f[/]=full-screen  "
            "[bold cyan]w[/]=click-a-window  [dim](Enter=r)[/] ▸ "
        ).strip().lower()
        mode = {"r": "region", "f": "full", "w": "window", "": "region"}.get(raw, "region")
        try:
            path = screen_capture.capture(session_id=session_id, mode=mode)
        except Exception as e:
            console.print(f"[red]  Screenshot failed: {e}[/]")
            return
        console.print(f"[dim]  saved: {path}[/]")

        # Ask user for optional guidance / question about the screenshot
        user_q = console.input(
            "[cyan]  What do you want the coach to do with this?[/] "
            "[dim](Enter for default: analyse + suggest response)[/]\n  ▸ "
        ).strip()
        if not user_q:
            user_q = (
                "Analyse this screenshot. Identify what's on screen (coding question, "
                "diagram, form, etc.). If it's a question or task, give me a clear "
                "answer or approach I can say in the next 30-60 seconds. If it's a "
                "reference diagram, summarise the key points that matter for the "
                "conversation. Keep it tight."
            )

        # Build system prompt from active template + plan (same context the
        # regular turn responses get).
        from templates import render_prompt
        system_prompt = render_prompt(template_id, profile, plan=plan)

        with console.status("[cyan]  Analysing screenshot...[/]", spinner="dots"):
            try:
                reply = respond_with_image(
                    llm_provider, llm_model, path, user_q, system_prompt,
                )
            except Exception as e:
                console.print(f"[red]  Vision LLM error: {e}[/]")
                return

        console.print(Panel(
            Text(reply.strip(), style="white"),
            title=f"[bold bright_cyan]📸 SCREEN ANALYSIS[/]",
            subtitle=f"[dim]{path.name}[/]",
            border_style="cyan", padding=(1, 2),
        ))

        # Also save into session history so future turns can reference it.
        sess.append_message(session_id, "user",
                            f"[SCREENSHOT saved at {path.name}] {user_q}",
                            speaker="unknown")
        sess.append_message(session_id, "assistant", reply)

    def _current_section_str() -> str:
        if not plan or not plan.get("sections"):
            return ""
        sections = plan["sections"]
        if current_section_idx >= len(sections):
            return "  [dim]plan: complete[/]"
        s = sections[current_section_idx]
        return (
            f"  [dim]plan:[/] [bold magenta]§{current_section_idx+1}/{len(sections)}[/] "
            f"[magenta]{s.get('title', '')}[/]"
        )

    while True:
        console.print()
        source_hint = "🎙️ mic (you)" if current_source == "mic" else "👂 system (interviewer)"
        try:
            plan_hint = _current_section_str()
            plan_keys = "  [magenta]p[/]=plan  [magenta]§[/]=next-§  [bright_cyan]b[/]=research" if plan else ""
            user_input = console.input(
                f"[bold cyan][Turn {turn}][/] "
                f"[dim]session #{session_id}  source:[/] {source_hint}{plan_hint}\n"
                f"  [Enter]=go  [bold cyan]y[/]=you  [bold yellow]i[/]=interviewer  "
                f"[bold]l[/]=live  [bold bright_cyan]c[/]=screen  "
                f"[bold bright_white]t[/]=type-text  [bold bright_white]x[/]=extra-context  "
                f"[bold green]n[/]=new-session  "
                f"[bold magenta]r[/]=rename{plan_keys}  [dim]q=quit[/] ▸ "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]  Goodbye.[/]\n")
            break
        if user_input == "q":
            console.print("\n[dim]  Goodbye.[/]\n")
            break
        if user_input == "p" and plan:
            from meeting_plans import render_plan_for_prompt
            console.print(Panel(
                Text(render_plan_for_prompt(plan), style="white"),
                title="[bold magenta]📋 Meeting plan[/]",
                border_style="magenta", padding=(1, 2),
            ))
            continue
        if user_input == "c":
            _handle_screen_capture(
                session_id=session_id, profile=profile, template_id=template_id,
                plan=plan, current_section_idx=current_section_idx,
                llm_provider=llm_provider, llm_model=llm_model, history=history,
            )
            continue
        if user_input == "b" and plan:
            # Refresh briefing on the fly
            import research
            name = console.input("[cyan]  Counterparty name[/]: ").strip()
            if not name:
                continue
            affiliation = console.input("[cyan]  Affiliation (optional)[/]: ").strip()
            with console.status("[cyan]  Researching...[/]", spinner="dots"):
                raw = research.research_counterparty(name, affiliation)
                briefing = research.synthesize_briefing(raw, llm_provider, llm_model)
            meeting_plans.update_plan(
                plan["id"], briefing=briefing,
                raw_research_json=json.dumps(raw.to_dict()),
            )
            plan = meeting_plans.get_plan(plan["id"])
            # Re-render system prompt with new briefing
            from templates import render_prompt as _rp
            system_prompt = _rp(template_id, profile, plan=plan)
            console.print("[green]  ✓ Briefing refreshed and injected.[/]\n")
            continue
        if user_input == "t":
            # Type a transcript directly — for when audio failed OR for
            # pasting text from chat / an email you want the coach to react to.
            console.print(
                "[cyan]  Paste / type what was said[/] "
                "[dim](empty line ends multi-line input)[/]"
            )
            lines = []
            while True:
                try:
                    line = input("  ▸ ")
                except EOFError:
                    break
                if line == "":
                    break
                lines.append(line)
            typed = "\n".join(lines).strip()
            if not typed:
                continue
            # Ask who "said" this so the tag matches semantics
            who = console.input(
                "[cyan]  Whose words are these?[/] "
                "[bold cyan]i[/]=interviewer  [bold yellow]y[/]=you  "
                "[bold white]u[/]=unknown  [dim](Enter=interviewer)[/] ▸ "
            ).strip().lower()
            typed_speaker = {"i": "interviewer", "y": "you", "u": "unknown", "": "interviewer"}.get(who, "interviewer")
            # Route through the same pipeline as an audio turn
            transcript = typed
            current_speaker = typed_speaker
            show_transcript(transcript, current_speaker, profile["name"], turn)
            speaker_tag = {"you": "[USER said]", "interviewer": "[INTERVIEWER said]", "unknown": "[HEARD]"}[current_speaker]
            section_prefix = ""
            if plan and plan.get("sections") and current_section_idx < len(plan["sections"]):
                s = plan["sections"][current_section_idx]
                section_prefix = f"[CURRENT SECTION §{current_section_idx+1}: {s.get('title','')}] "
            tagged = f"{section_prefix}{speaker_tag} {transcript}"
            with console.status("[cyan]  Thinking...[/]", spinner="dots"):
                reply = ""
                routing_info = ""
                try:
                    reply, fs = coach_run_turn(
                        transcript=tagged, speaker=current_speaker,
                        system_prompt=system_prompt, history=history,
                        provider=llm_provider, model=llm_model,
                        plan=plan,
                        briefing_present=bool(plan and (plan.get("briefing") or "").strip()),
                    )
                    tier = fs.get("routing_decision", "default")
                    tt = fs.get("turn_type", "?")
                    match = "matched" if fs.get("matched_answer_text") else "fresh"
                    routing_info = f"[dim]  ⚙  turn={tt} · tier={tier} · {match}[/]"
                except Exception as e:
                    console.print(f"[red]  [Graph error: {e}][/]")
                    continue
            if routing_info:
                console.print(routing_info)
            sess.append_message(session_id, "user", tagged, speaker=current_speaker)
            sess.append_message(session_id, "assistant", reply)
            history.append({"role": "user", "content": tagged})
            history.append({"role": "assistant", "content": reply})
            show_reply(parse_reply(reply), turn)
            turn += 1
            continue
        if user_input == "x":
            # Inject freeform context for the rest of the session.
            console.print(
                "[cyan]  Extra context to remember for the rest of this session[/] "
                "[dim](e.g. 'she just mentioned she was on the Anthropic team' or "
                "'change of plan — he wants to discuss architecture')[/]"
            )
            console.print("[dim]  (empty line ends)[/]")
            lines = []
            while True:
                try:
                    line = input("  ▸ ")
                except EOFError:
                    break
                if line == "":
                    break
                lines.append(line)
            extra = "\n".join(lines).strip()
            if not extra:
                continue
            # Append to system prompt so every future turn sees it.
            addendum = f"\n\n[LIVE CONTEXT UPDATE — added during turn {turn}]\n{extra}\n"
            system_prompt = system_prompt + addendum
            console.print("[green]  ✓ Context injected into the coach's system prompt for this session.[/]\n")
            continue
        if user_input in ("§", "s") and plan and plan.get("sections"):
            if current_section_idx < len(plan["sections"]):
                current_section_idx += 1
                if current_section_idx >= len(plan["sections"]):
                    console.print("[dim]  Plan complete — no more sections.[/]\n")
                else:
                    s = plan["sections"][current_section_idx]
                    console.print(
                        f"[magenta]  → §{current_section_idx+1}: {s.get('title','')}[/]\n"
                    )
            continue
        if user_input == "n":
            title = console.input(
                f"  New session title [dim](Enter for default)[/]: "
            ).strip() or _default_session_title(template_id)
            session_id = sess.create_session(title, template_id, llm_provider, llm_model)
            from sessions import _connect
            with _connect() as conn:
                conn.execute("UPDATE sessions SET profile_id = ?, template_id = ? WHERE id = ?",
                             (profile["id"], template_id, session_id))
            history = []
            turn = 1
            console.print(f"[green]  ✓ New session #{session_id}: {title}[/]\n")
            continue
        if user_input == "r":
            new_title = console.input("  New title: ").strip()
            if new_title:
                sess.rename_session(session_id, new_title)
                console.print(f"[green]  ✓ Renamed to '{new_title}'[/]\n")
            continue
        if user_input == "y":
            current_source, current_speaker = "mic", "you"
            args.live = False
        elif user_input == "i":
            current_source, current_speaker = "system", "interviewer"
            args.live = False
        elif user_input == "l":
            current_source, current_speaker = "system", "interviewer"
            args.live = True

        if args.live:
            audio = record_until_silence(source=current_source, speaker=current_speaker,
                                         silence_duration=args.silence)
        else:
            audio = record_until_keypress(source=current_source, speaker=current_speaker)

        if len(audio) == 0:
            console.print("[yellow]  [No audio captured — try again][/]")
            continue

        with console.status("[cyan]  Transcribing...[/]", spinner="dots"):
            try:
                transcript = stt_transcribe(audio, provider=stt_provider, model=stt_model)
            except Exception as e:
                console.print(f"[red]  [STT error: {e}][/]")
                continue

        if not transcript:
            console.print("[yellow]  [Could not transcribe — nothing heard][/]")
            continue

        show_transcript(transcript, current_speaker, profile["name"], turn)

        speaker_tag = {
            "you": "[USER said]",
            "interviewer": "[INTERVIEWER said]",
            "unknown": "[HEARD]",
        }[current_speaker]

        # If a plan is active, include the current section marker so the LLM
        # can situate its response within the agenda.
        section_prefix = ""
        if plan and plan.get("sections") and current_section_idx < len(plan["sections"]):
            s = plan["sections"][current_section_idx]
            section_prefix = (
                f"[CURRENT SECTION §{current_section_idx+1}: {s.get('title','')}] "
            )
        tagged = f"{section_prefix}{speaker_tag} {transcript}"

        with console.status("[cyan]  Thinking...[/]", spinner="dots"):
            reply = ""
            routing_info = ""
            try:
                if args.no_graph:
                    reply = respond(tagged, history, system_prompt,
                                    provider=llm_provider, model=llm_model)
                else:
                    reply, final_state = coach_run_turn(
                        transcript=tagged,
                        speaker=current_speaker,
                        system_prompt=system_prompt,
                        history=history,
                        provider=llm_provider,
                        model=llm_model,
                        plan=plan,
                        briefing_present=bool(plan and (plan.get("briefing") or "").strip()),
                    )
                    tier = final_state.get("routing_decision", "default")
                    tt = final_state.get("turn_type", "?")
                    match = "matched" if final_state.get("matched_answer_text") else "fresh"
                    routing_info = (
                        f"[dim]  ⚙  turn={tt} · tier={tier} · {match}"
                        f"{' — ' + final_state['routing_reason'] if final_state.get('routing_reason') else ''}[/]"
                    )
                    if final_state.get("error"):
                        console.print(f"[yellow]  graph note: {final_state['error']}[/]")
            except Exception as e:
                console.print(f"[red]  [Graph error: {e}] — falling back to direct call[/]")
                try:
                    reply = respond(tagged, history, system_prompt,
                                    provider=llm_provider, model=llm_model)
                except Exception as e2:
                    console.print(f"[red]  [LLM error: {e2}][/]")
                    continue

        if routing_info:
            console.print(routing_info)

        sess.append_message(session_id, "user", tagged, speaker=current_speaker)
        sess.append_message(session_id, "assistant", reply)

        # Keep in-memory history in sync so the next graph turn sees full context.
        # (When using --no-graph, respond() already mutated history in place;
        # skip in that case to avoid double-append.)
        if not args.no_graph:
            history.append({"role": "user", "content": tagged})
            history.append({"role": "assistant", "content": reply})

        show_reply(parse_reply(reply), turn)
        turn += 1


if __name__ == "__main__":
    main()

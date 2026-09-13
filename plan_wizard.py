"""
Interactive wizard to build a MeetingPlan.

Two paths:
  * `create_plan_wizard()`  — fully interactive, asks every field
  * `create_plan_from_template(name, profile_id)` — preload common shapes

The templates encode structures like the one drafted for the Eric Jackson call
so users can start from a working plan and just fill in specifics.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import meeting_plans

console = Console()


def _multiline(label: str, placeholder: str = "") -> str:
    console.print(f"[cyan]  {label}[/]")
    if placeholder:
        console.print(f"[dim]    e.g. {placeholder}[/]")
    console.print("[dim]    (empty line ends)[/]")
    lines = []
    while True:
        try:
            line = input("    ▸ ")
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def _list_input(label: str, placeholder: str = "") -> list[str]:
    console.print(f"[cyan]  {label}[/]")
    if placeholder:
        console.print(f"[dim]    e.g. {placeholder}[/]")
    console.print("[dim]    (one per line; empty line ends)[/]")
    items = []
    while True:
        try:
            line = input(f"    {len(items)+1}. ").strip()
        except EOFError:
            break
        if not line:
            break
        items.append(line)
    return items


def _sections_input() -> list[dict]:
    console.print("[cyan]  Agenda sections[/] [dim](title, minutes, goal — empty title to finish)[/]")
    sections = []
    while True:
        try:
            title = input(f"    Section {len(sections)+1} title ▸ ").strip()
        except EOFError:
            break
        if not title:
            break
        try:
            minutes_raw = input(f"      minutes ▸ ").strip()
            minutes = int(minutes_raw) if minutes_raw.isdigit() else 5
            goal = input(f"      goal ▸ ").strip()
        except EOFError:
            break
        sections.append({"title": title, "minutes": minutes, "goal": goal})
    return sections


def create_plan_wizard(profile_id: int | None = None) -> int:
    console.print(Panel(
        Text("Meeting plan — set the shape of the conversation so the coach can guide you live.",
             style="bold white"),
        title="[bold bright_cyan]📋 New meeting plan[/]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))

    title = ""
    while not title:
        title = console.input("[cyan]  Plan title[/] [dim](e.g. 'Call with Dr. Eric Jackson — NYU')[/]: ").strip()
    counterparty = console.input("[cyan]  Counterparty[/] [dim](name + role)[/]: ").strip()
    purpose = console.input("[cyan]  Purpose of this conversation[/]:\n    ▸ ").strip()
    duration_raw = console.input("[cyan]  Planned duration in minutes[/] [dim](Enter for 45)[/]: ").strip()
    duration_min = int(duration_raw) if duration_raw.isdigit() else 45

    console.print()
    sections = _sections_input()
    console.print()
    answers_prep = _list_input("Things you should be ready to ANSWER",
                                "Why research and not just personal? / How your AI background fits")
    console.print()
    questions_ask = _list_input("Questions you want to ASK them",
                                 "Are you taking students for 2027? / Who else would you point me to?")
    console.print()
    traps_avoid = _list_input("Traps to avoid",
                              "Don't oversell AI angle / Don't dwell on personal story")
    console.print()
    commitments = _list_input("Concrete commitments to leave with",
                              "Follow-up email in 2 weeks / Reading list from them / Next call date")
    console.print()
    notes = _multiline("Any other notes",
                       "'She emphasises variability in her 2021 paper'")

    pid = meeting_plans.create_plan(
        title=title,
        profile_id=profile_id,
        counterparty=counterparty,
        purpose=purpose,
        duration_min=duration_min,
        sections=sections,
        answers_prep=answers_prep,
        questions_ask=questions_ask,
        traps_avoid=traps_avoid,
        commitments=commitments,
        notes=notes,
    )
    console.print(f"\n[green]  ✓ Plan #{pid} saved.[/]\n")
    return pid


def pick_plan(profile_id: int | None = None) -> int | None:
    """Show a picker. Returns plan_id, or None if user picked 'no plan'."""
    rows = meeting_plans.list_plans(profile_id=profile_id, limit=20)
    if not rows:
        console.print("[dim]  No meeting plans saved.[/]")
        raw = console.input(
            "[bold]Create one now?[/] [green]y[/]=create  [dim]Enter[/]=skip ▸ "
        ).strip().lower()
        if raw == "y":
            return create_plan_wizard(profile_id=profile_id)
        return None

    table = Table(title="Meeting plans", border_style="dim")
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Title", style="white")
    table.add_column("Counterparty", style="yellow")
    table.add_column("Sections", style="green", justify="right")
    table.add_column("Updated", style="dim")
    for i, r in enumerate(rows, 1):
        import json
        n_sections = len(json.loads(r["sections_json"] or "[]"))
        table.add_row(
            str(i), r["title"], r["counterparty"] or "-",
            str(n_sections), r["updated_at"].replace("T", " "),
        )
    console.print(table)

    while True:
        raw = console.input(
            "\n[bold]Pick plan[/]: [cyan]<n>[/]=use  [bold green]n[/]=new  "
            "[bold red]d<n>[/]=delete  [dim]Enter[/]=no plan ▸ "
        ).strip().lower()
        if raw == "":
            return None
        if raw == "n":
            return create_plan_wizard(profile_id=profile_id)
        if raw.startswith("d") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            if 0 <= idx < len(rows):
                meeting_plans.delete_plan(rows[idx]["id"])
                console.print(f"[red]  ✗ Deleted '{rows[idx]['title']}'[/]")
                return pick_plan(profile_id=profile_id)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(rows):
                return rows[idx]["id"]
        console.print("[yellow]  Invalid choice.[/]")

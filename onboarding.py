"""
Onboarding wizard: profile creation, template selection, profile management.

Runs automatically when no profile exists; can be re-run with --onboard.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import profile_store
from templates import list_template_choices

console = Console()


def _multiline_input(prompt: str, placeholder: str = "") -> str:
    """Read multi-line input until an empty line."""
    console.print(f"[cyan]{prompt}[/]")
    if placeholder:
        console.print(f"[dim]  Example: {placeholder}[/]")
    console.print("[dim]  (Blank line ends input, Enter to skip)[/]")
    lines = []
    while True:
        try:
            line = input("  ▸ ")
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def create_profile_wizard() -> int:
    console.print(
        Panel(
            Text("Let's build your profile — this is what tailors every answer.",
                 style="bold white"),
            title="[bold bright_green]👤 New profile[/]",
            border_style="bright_green",
            padding=(1, 2),
        )
    )

    name = ""
    while not name:
        name = console.input("[cyan]  Your name[/]: ").strip()
    pronouns = console.input("[cyan]  Pronouns[/] [dim](she/her, he/him, they/them)[/]: ").strip() or "they/them"

    console.print()
    background = _multiline_input(
        "Your background",
        "AI/software engineer with a BSc in CS from KNUST. Have stuttered since childhood.",
    )
    console.print()
    target_role = console.input(
        "[cyan]  What role or opportunity are you preparing for?[/]\n  ▸ "
    ).strip()
    console.print()
    strengths = _multiline_input(
        "Strengths to lean on (things you want the coach to surface)",
        "Cross-domain thinking; lived experience of stuttering; ML systems.",
    )
    console.print()
    weaknesses = _multiline_input(
        "Weaknesses to defuse (things to preempt without dwelling on)",
        "No formal neuroscience training yet; first-time PhD applicant.",
    )
    console.print()
    extra = _multiline_input(
        "Anything else the coach should know (upcoming calls, key people, quirks)?",
        "Call with Dr. Toyomura late Sep; Dr. Höbler Nov 6.",
    )

    pid = profile_store.create_profile(
        name=name,
        pronouns=pronouns,
        background=background,
        target_role=target_role,
        strengths=strengths,
        weaknesses=weaknesses,
        extra_context=extra,
    )
    profile_store.set_active_profile(pid)
    console.print(f"\n[green]  ✓ Profile #{pid} created and set active.[/]\n")
    return pid


def pick_or_create_profile() -> int:
    """If any profiles exist, let user pick/create. Otherwise run first-time wizard."""
    profiles = profile_store.list_profiles()

    if not profiles:
        console.print(
            Panel(
                Text("First time here? Let's set up your profile.",
                     style="bold white"),
                title="[bold bright_cyan]Welcome[/]",
                border_style="bright_cyan",
                padding=(1, 2),
            )
        )
        return create_profile_wizard()

    table = Table(title="Your profiles", border_style="dim")
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Name", style="white")
    table.add_column("Target", style="yellow")
    table.add_column("Active", style="green")
    for i, p in enumerate(profiles, 1):
        active_mark = "✓" if p["is_active"] else ""
        table.add_row(str(i), p["name"], p["target_role"] or "-", active_mark)
    console.print(table)

    while True:
        raw = console.input(
            "\n[bold]Pick profile[/]: [cyan]<number>[/]  "
            "[bold green]n[/]=new  [bold red]d<number>[/]=delete  "
            "[dim](Enter=keep active)[/] ▸ "
        ).strip().lower()

        active = profile_store.get_active_profile()
        if raw == "" and active:
            return active["id"]
        if raw == "n":
            return create_profile_wizard()
        if raw.startswith("d") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            if 0 <= idx < len(profiles):
                profile_store.delete_profile(profiles[idx]["id"])
                console.print(f"[red]  ✗ Deleted profile '{profiles[idx]['name']}'[/]\n")
                return pick_or_create_profile()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(profiles):
                pid = profiles[idx]["id"]
                profile_store.set_active_profile(pid)
                return pid
        console.print("[yellow]  Invalid choice.[/]")


def pick_template(default: str = "academic-phd") -> str:
    choices = list_template_choices()

    table = Table(title="Interview / conversation templates", border_style="dim")
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Template", style="white")
    table.add_column("ID", style="dim")
    for i, (tid, label) in enumerate(choices, 1):
        marker = "  ← default" if tid == default else ""
        table.add_row(str(i), label + marker, tid)
    console.print(table)

    while True:
        raw = console.input(
            f"\n[bold]Pick template (1-{len(choices)}, Enter for default)[/] ▸ "
        ).strip()
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1][0]
        console.print("[yellow]  Invalid choice.[/]")


def edit_profile_wizard(profile_id: int):
    p = profile_store.get_profile(profile_id)
    if not p:
        console.print("[red]  Profile not found.[/]")
        return

    console.print(f"\n[bold]Editing profile:[/] {p['name']}\n")
    fields = ["name", "pronouns", "background", "target_role",
              "strengths", "weaknesses", "extra_context"]
    updates = {}
    for f in fields:
        current = p[f] or ""
        preview = (current[:60] + "…") if len(current) > 60 else current
        console.print(f"[dim]  {f}: {preview}[/]")
        new = console.input(f"  [cyan]{f}[/] [dim](Enter to keep)[/] ▸ ").strip()
        if new:
            updates[f] = new
    if updates:
        profile_store.update_profile(profile_id, **updates)
        console.print(f"\n[green]  ✓ Updated {len(updates)} field(s).[/]\n")
    else:
        console.print("\n[dim]  No changes.[/]\n")

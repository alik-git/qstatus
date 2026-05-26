"""Opt-in shell reminders for quick-status."""

from __future__ import annotations

from importlib import resources
from typing import Literal

ReminderContext = Literal["interactive", "codex"]

_BASH_CONTEXT_PLACEHOLDER = "__QUICK_STATUS_REMINDERS_CONTEXT__"
_BASH_REMINDERS_RESOURCE = "shell/reminders.bash"


def render_reminders_init(
    shell: str,
    *,
    context: ReminderContext = "interactive",
) -> str:
    """Return opt-in shell integration source for quick-status reminders."""
    if shell != "bash":
        msg = f"unsupported reminders shell: {shell}"
        raise ValueError(msg)
    if context not in ("interactive", "codex"):
        msg = f"unsupported reminders context: {context}"
        raise ValueError(msg)

    source = (
        resources.files(__package__)
        .joinpath(_BASH_REMINDERS_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return source.replace(_BASH_CONTEXT_PLACEHOLDER, context)

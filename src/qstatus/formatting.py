"""Shared terminal formatting primitives for qstatus human output."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qstatus.models import CommandRecord


_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[38;2;224;108;117m"
_GREEN = "\033[38;2;152;195;121m"
_AMBER = "\033[38;2;229;192;123m"
_BLUE = "\033[38;2;97;175;239m"
_PURPLE = "\033[38;2;198;120;221m"
_COMMENT_GREEN = "\033[38;2;161;216;183m"
_VARIABLE = "\033[38;2;223;223;223m"
_MUTED = "\033[38;2;171;178;191m"
_NUMBER = "\033[38;2;209;154;102m"


def label(value: str, color: bool) -> str:
    """Format a section label."""
    return _style(value, color, _BOLD)


def name(value: str, color: bool) -> str:
    """Format a symbolic name such as a branch, repo, or tool."""
    return _style(value, color, _BOLD, _BLUE)


def variable(value: str, color: bool) -> str:
    """Format a user/environment value."""
    return _style(value, color, _VARIABLE)


def muted(value: str, color: bool) -> str:
    """Format a low-emphasis label."""
    return _style(value, color, _MUTED)


def number(value: str, color: bool) -> str:
    """Format a numeric value."""
    return _style(value, color, _NUMBER)


def state(value: str, color: bool) -> str:
    """Format common status words with stable qstatus colors."""
    if value in {
        "clean",
        "synced",
        "success",
        "open",
        "yes",
        "none",
        "0",
        "active",
        "git",
        "ok",
    }:
        return _style(value, color, _GREEN)
    if value in {
        "dirty",
        "ahead",
        "behind",
        "diverged",
        "pending",
        "running",
        "draft",
        "skipped",
        "mixed",
        "unknown",
        "missing",
        "not_found",
        "not-found",
        "neutral",
        "cwd",
        "marker",
    }:
        return _style(value, color, _AMBER)
    if value in {
        "conflicted",
        "failure",
        "closed",
        "unavailable",
        "timeout",
        "no",
        "failed",
        "parse_error",
    }:
        return _style(value, color, _RED)
    if value == "detached":
        return _style(value, color, _PURPLE)
    if value in {"no-upstream", "no_upstream", "not-requested"}:
        return _style(value, color, _COMMENT_GREEN)
    return value


def kv(key: str, value: object, color: bool) -> str:
    """Format a compact key=value pair with numeric value coloring."""
    return f"{key}={number(str(value), color)}"


def home_alias_line(*, color: bool) -> str:
    """Return the optional line that explains home path compaction."""
    home = variable(str(Path.home()), color)
    return f"{label('PATHS', color)}\n  {muted('~', color)}  {home}"


def hybrid_section(
    title: str,
    *,
    path_rows: list[tuple[str, str]],
    scalar_rows: list[tuple[str, str]],
    color: bool,
) -> list[str]:
    """Render a section with path rows first and compact scalar pairs after."""
    lines = [label(title, color)]
    lines.extend(aligned_rows(path_rows, color=color))
    if scalar_rows:
        lines.append(f"  {format_pairs(scalar_rows)}")
    return lines


def aligned_rows(rows: list[tuple[str, str]], *, color: bool) -> list[str]:
    """Render right-aligned keys and left-aligned values."""
    if not rows:
        return []
    key_width = max(len(key) for key, _value in rows)
    return [f"  {muted(key.rjust(key_width), color)}  {value}" for key, value in rows]


def compact_rows(rows: list[tuple[str, str]], *, color: bool) -> list[str]:
    """Render left-aligned key/value rows without table padding."""
    return [f"  {muted(key, color)}  {value}" for key, value in rows]


def notice_lines(title: str, message: str, *, color: bool) -> list[str]:
    """Render a title plus a single indented diagnostic message."""
    return [label(title, color), f"  {variable(message, color)}"]


def hint_lines(rows: list[tuple[str, str]], *, color: bool) -> list[str]:
    """Render command-shaped hints with multiline alignment."""
    if not rows:
        return []
    title = "HINTS"
    title_width = len(title)
    lines: list[str] = []
    for index, (key, value) in enumerate(rows):
        row_label = label(title, color) if index == 0 else " " * title_width
        value_lines = value.splitlines() or [""]
        if len(value_lines) == 1:
            lines.append(f"{row_label} {muted(key, color)}={value_lines[0]}")
            continue
        lines.append(f"{row_label} {muted(key, color)}:")
        lines.extend(f"{' ' * (title_width + 3)}{line}" for line in value_lines)
    return lines


def format_pairs(pairs: list[tuple[str, str]]) -> str:
    """Render compact key=value pairs."""
    return "  ".join(f"{key}={value}" for key, value in pairs)


def path(value: str, color: bool, *, abs_paths: bool) -> str:
    """Format a path, compacting the home directory unless disabled."""
    if abs_paths:
        return variable(value, color)
    return variable(compact_home(value), color)


def path_or_missing(value: str | None, color: bool, *, abs_paths: bool) -> str:
    """Format a path-like optional value."""
    if not value:
        return state("missing", color)
    return path(value, color, abs_paths=abs_paths)


def optional_value(value: str | None, color: bool) -> str:
    """Format an optional scalar value."""
    if not value:
        return state("missing", color)
    return variable(value, color)


def compact_home(value: str) -> str:
    """Replace the current home directory prefix with ~."""
    home = str(Path.home())
    if value == home:
        return "~"
    if value.startswith(f"{home}/"):
        return f"~/{value.removeprefix(f'{home}/')}"
    return value


def format_command_hint(args: list[str], *, abs_paths: bool) -> str:
    """Render a command hint compactly, wrapping only long command lines."""
    compact_args = list(args) if abs_paths else [compact_home(arg) for arg in args]
    if len(args) <= 2:
        return " ".join(compact_args)
    chunks: list[str] = []
    index = 0
    while index < len(compact_args):
        value = compact_args[index]
        if (
            value.startswith("--")
            and index + 1 < len(compact_args)
            and not compact_args[index + 1].startswith("--")
        ):
            chunks.append(f"{value} {compact_args[index + 1]}")
            index += 2
        else:
            chunks.append(value)
            index += 1
    if len(" ".join(chunks)) <= 78:
        return " ".join(chunks)
    return " \\\n  ".join(chunks)


def yes_no(value: bool) -> str:
    """Return yes/no for booleans."""
    return "yes" if value else "no"


def active_name(value: str | None) -> str:
    """Return a shell environment name or none."""
    if not value or value == "none":
        return "none"
    return value


def path_state(value: str | None) -> str:
    """Return active/none for an optional path."""
    return "active" if value else "none"


def command_lines(commands: list[CommandRecord], *, color: bool) -> list[str]:
    """Render command evidence in verbose human output."""
    if not commands:
        return []
    return [
        label("COMMANDS", color),
        *[
            f"  {state(str(command_status(command)), color)}  {' '.join(command.args)}"
            for command in commands
        ],
    ]


def command_status(command: CommandRecord) -> int | str | None:
    """Return a compact status value for one command record."""
    if command.timed_out:
        return "timeout"
    if command.unavailable:
        return "unavailable"
    return command.exit_code


def _style(value: str, color: bool, *codes: str) -> str:
    if not color or not codes:
        return value
    return f"{''.join(codes)}{value}{_RESET}"

"""Human and JSON renderers for quick_status environment snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from quick_status import formatting as fmt

if TYPE_CHECKING:
    from quick_status.models import EnvSnapshot, ProjectEnvironment, ToolFact


def render_env_json(snapshot: EnvSnapshot, *, verbose: bool = False) -> str:
    """Render an environment snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_env_human(
    snapshot: EnvSnapshot,
    *,
    verbose: bool = False,
    color: bool = False,
    abs_paths: bool = False,
    compact: bool = False,
    show_home: bool = False,
    show_tools: bool = False,
    show_hints: bool = False,
) -> str:
    """Render a human-readable environment snapshot."""
    if compact:
        lines = render_env_compact_lines(
            snapshot,
            color=color,
            abs_paths=abs_paths,
            show_home=show_home,
            show_tools=show_tools,
            show_hints=show_hints,
        )
    else:
        lines = render_env_sectioned_lines(
            snapshot,
            color=color,
            abs_paths=abs_paths,
            show_home=show_home,
            show_tools=show_tools,
            show_hints=show_hints,
        )
    if verbose:
        lines.extend(
            render_env_verbose_lines(snapshot, color=color, abs_paths=abs_paths),
        )
    return "\n".join(lines)


def render_env_sectioned_lines(
    snapshot: EnvSnapshot,
    *,
    color: bool = False,
    abs_paths: bool = False,
    show_home: bool = False,
    show_tools: bool = False,
    show_hints: bool = False,
) -> list[str]:
    """Render the default readable environment output."""
    shell = snapshot.shell
    project = snapshot.project
    devpy = snapshot.devpy
    python = snapshot.python_commands
    tools = snapshot.tools
    python3_path_rows, python3_scalar_rows = _python3_rows(
        python["python"],
        python["python3"],
        color=color,
        abs_paths=abs_paths,
    )

    lines = [fmt.home_alias_line(color=color)] if show_home else []
    lines.extend(
        fmt.hybrid_section(
            "SHELL",
            path_rows=[("cwd", fmt.path(shell.cwd, color, abs_paths=abs_paths))],
            scalar_rows=[
                ("kind", fmt.state(shell.kind, color)),
                ("conda", fmt.state(fmt.active_name(shell.conda_default_env), color)),
                ("venv", fmt.state(fmt.path_state(shell.virtual_env), color)),
            ],
            color=color,
        ),
    )
    lines.extend(
        fmt.hybrid_section(
            "PYTHON",
            path_rows=[
                (
                    "runtime",
                    fmt.path(snapshot.runtime.executable, color, abs_paths=abs_paths),
                ),
                (
                    "python",
                    _format_tool_value(
                        python["python"],
                        color=color,
                        abs_paths=abs_paths,
                    ),
                ),
                *python3_path_rows,
            ],
            scalar_rows=[
                *python3_scalar_rows,
                ("version", fmt.number(snapshot.runtime.version, color)),
                ("venv_like", fmt.state(fmt.yes_no(snapshot.runtime.venv_like), color)),
            ],
            color=color,
        ),
    )
    lines.extend(
        fmt.hybrid_section(
            "PROJECT",
            path_rows=[("root", fmt.path(project.root, color, abs_paths=abs_paths))],
            scalar_rows=[
                *_project_name_pairs(project, color=color),
                ("pyproject", fmt.state(project.pyproject_status, color)),
                ("uv.lock", fmt.state(fmt.yes_no(project.uv_lock), color)),
                ("devpy", fmt.state(fmt.yes_no(devpy.present), color)),
                (".venv", fmt.state(fmt.yes_no(project.venv_exists), color)),
            ],
            color=color,
        ),
    )
    if devpy.present:
        lines.extend(
            fmt.hybrid_section(
                "DEVPY",
                path_rows=[
                    (
                        "venv",
                        fmt.path(
                            devpy.venv_path or "missing",
                            color,
                            abs_paths=abs_paths,
                        ),
                    ),
                ],
                scalar_rows=[
                    ("base", fmt.state(devpy.base_conda_env or "missing", color)),
                    ("status", fmt.state(devpy.status, color)),
                    (
                        "venv_python",
                        fmt.state(fmt.yes_no(devpy.venv_python_exists), color),
                    ),
                    ("editables", fmt.number(str(devpy.editable_count), color)),
                ],
                color=color,
            ),
        )
    if show_tools:
        lines.extend(_tool_lines(tools, color=color, abs_paths=abs_paths))
    if show_hints and snapshot.hints:
        lines.extend(_hint_lines(snapshot.hints, color=color, abs_paths=abs_paths))
    return lines


def render_env_compact_lines(
    snapshot: EnvSnapshot,
    *,
    color: bool = False,
    abs_paths: bool = False,
    show_home: bool = False,
    show_tools: bool = False,
    show_hints: bool = False,
) -> list[str]:
    """Render a dense one-line-per-section environment snapshot."""
    shell = snapshot.shell
    project = snapshot.project
    devpy = snapshot.devpy
    python = snapshot.python_commands
    tools = snapshot.tools
    runtime_path = fmt.path(snapshot.runtime.executable, color, abs_paths=abs_paths)
    python_value = _format_tool_value(
        python["python"],
        color=color,
        abs_paths=abs_paths,
    )
    python3_value = _format_compact_python3(
        python["python"],
        python["python3"],
        color=color,
        abs_paths=abs_paths,
    )

    lines = [fmt.home_alias_line(color=color)] if show_home else []
    lines.extend(
        [
            (
                f"{fmt.label('ENV', color)} "
                f"shell={fmt.state(shell.kind, color)} "
                f"conda={fmt.state(fmt.active_name(shell.conda_default_env), color)} "
                f"venv={fmt.state(fmt.path_state(shell.virtual_env), color)} "
                f"cwd={fmt.path(shell.cwd, color, abs_paths=abs_paths)}"
            ),
            (
                f"{fmt.label('PYTHON', color)} "
                f"runtime={runtime_path} "
                f"version={fmt.number(snapshot.runtime.version, color)} "
                f"venv_like={fmt.state(fmt.yes_no(snapshot.runtime.venv_like), color)} "
                f"python={python_value} "
                f"python3={python3_value}"
            ),
            (
                f"{fmt.label('PROJECT', color)} "
                f"root={fmt.path(project.root, color, abs_paths=abs_paths)} "
                f"{_format_compact_project_name(project, color=color)}"
                f"pyproject={fmt.state(project.pyproject_status, color)} "
                f"uv.lock={fmt.state(fmt.yes_no(project.uv_lock), color)} "
                f"devpy={fmt.state(fmt.yes_no(devpy.present), color)} "
                f".venv={fmt.state(fmt.yes_no(project.venv_exists), color)}"
            ),
        ],
    )
    if devpy.present:
        devpy_venv = fmt.path(
            devpy.venv_path or "missing",
            color,
            abs_paths=abs_paths,
        )
        lines.append(
            f"{fmt.label('DEVPY', color)} "
            f"base={fmt.state(devpy.base_conda_env or 'missing', color)} "
            f"venv={devpy_venv} "
            f"status={fmt.state(devpy.status, color)} "
            f"venv_python={fmt.state(fmt.yes_no(devpy.venv_python_exists), color)} "
            f"editables={fmt.number(str(devpy.editable_count), color)}",
        )
    if show_tools:
        lines.append(_compact_tools_line(tools, color=color, abs_paths=abs_paths))
    if show_hints and snapshot.hints:
        lines.extend(_hint_lines(snapshot.hints, color=color, abs_paths=abs_paths))
    return lines


def render_env_verbose_lines(
    snapshot: EnvSnapshot,
    *,
    color: bool = False,
    abs_paths: bool = False,
) -> list[str]:
    """Render detailed environment evidence for debugging."""
    shell = snapshot.shell
    runtime = snapshot.runtime
    project = snapshot.project
    devpy = snapshot.devpy

    lines = [
        *fmt.hybrid_section(
            "RUNTIME_DETAILS",
            path_rows=[
                ("prefix", fmt.path(runtime.prefix, color, abs_paths=abs_paths)),
                (
                    "base_prefix",
                    fmt.path(runtime.base_prefix, color, abs_paths=abs_paths),
                ),
            ],
            scalar_rows=[
                ("implementation", fmt.name(runtime.implementation, color)),
                ("venv_like", fmt.state(fmt.yes_no(runtime.venv_like), color)),
            ],
            color=color,
        ),
        *fmt.hybrid_section(
            "SHELL_ENV",
            path_rows=[
                (
                    "CONDA_PREFIX",
                    fmt.path_or_missing(
                        shell.conda_prefix,
                        color,
                        abs_paths=abs_paths,
                    ),
                ),
                (
                    "VIRTUAL_ENV",
                    fmt.path_or_missing(
                        shell.virtual_env,
                        color,
                        abs_paths=abs_paths,
                    ),
                ),
            ],
            scalar_rows=[
                (
                    "CONDA_DEFAULT_ENV",
                    fmt.optional_value(shell.conda_default_env, color),
                ),
                ("CONDA_SHLVL", fmt.optional_value(shell.conda_shlvl, color)),
            ],
            color=color,
        ),
        *fmt.hybrid_section(
            "PROJECT_FILES",
            path_rows=[],
            scalar_rows=[
                ("root_source", fmt.state(project.root_source, color)),
                ("requires_python", fmt.optional_value(project.requires_python, color)),
                (
                    "requirements.txt",
                    fmt.state(fmt.yes_no(project.requirements_txt), color),
                ),
                (
                    ".python-version",
                    fmt.state(fmt.yes_no(project.python_version_file), color),
                ),
                (
                    "environment.yml",
                    fmt.state(fmt.yes_no(project.environment_yml), color),
                ),
                (
                    "conda-lock.yml",
                    fmt.state(fmt.yes_no(project.conda_lock_yml), color),
                ),
            ],
            color=color,
        ),
    ]
    if project.pyproject_error:
        lines.extend(
            fmt.notice_lines("PYPROJECT_ERROR", project.pyproject_error, color=color),
        )
    if devpy.error:
        lines.extend(fmt.notice_lines("DEVPY_ERROR", devpy.error, color=color))
    if devpy.editable_paths:
        lines.extend(
            [
                fmt.label("DEVPY_EDITABLES", color),
                *[
                    f"  {fmt.path(path, color, abs_paths=abs_paths)}"
                    for path in devpy.editable_paths
                ],
            ],
        )
    lines.append(fmt.label("TOOL_DETAILS", color))
    for name, tool in sorted({**snapshot.python_commands, **snapshot.tools}.items()):
        lines.extend(
            _tool_detail_lines(
                name,
                tool,
                color=color,
                abs_paths=abs_paths,
            ),
        )
    lines.extend(fmt.command_lines(snapshot.commands, color=color))
    return lines


def _tool_lines(
    tools: dict[str, ToolFact], *, color: bool, abs_paths: bool
) -> list[str]:
    return [
        fmt.label("TOOLS", color),
        *fmt.compact_rows(
            [
                (
                    "uv",
                    _format_tool_value(
                        tools["uv"],
                        color=color,
                        abs_paths=abs_paths,
                    ),
                ),
                (
                    "conda",
                    _format_tool_value(
                        tools["conda"],
                        color=color,
                        abs_paths=abs_paths,
                    ),
                ),
                (
                    "devpy",
                    _format_tool_value(
                        tools["devpy"],
                        color=color,
                        abs_paths=abs_paths,
                    ),
                ),
            ],
            color=color,
        ),
    ]


def _tool_detail_lines(
    name: str,
    tool: ToolFact,
    *,
    color: bool,
    abs_paths: bool,
) -> list[str]:
    lines = [
        f"  {fmt.name(name, color)}  status={fmt.state(tool.status, color)}",
        (
            f"    {fmt.muted('path', color)}  "
            f"{fmt.path_or_missing(tool.path, color, abs_paths=abs_paths)}"
        ),
    ]
    if tool.version:
        lines.append(
            f"    {fmt.muted('version', color)}  {fmt.variable(tool.version, color)}",
        )
    if tool.error:
        lines.append(
            f"    {fmt.muted('error', color)}  {fmt.variable(tool.error, color)}"
        )
    return lines


def _format_tool_value(tool: ToolFact, *, color: bool, abs_paths: bool) -> str:
    if not tool.available:
        return fmt.state("missing", color)
    if tool.path:
        return fmt.path(tool.path, color, abs_paths=abs_paths)
    return fmt.state(tool.status, color)


def _compact_tools_line(
    tools: dict[str, ToolFact], *, color: bool, abs_paths: bool
) -> str:
    uv_value = _format_tool_value(tools["uv"], color=color, abs_paths=abs_paths)
    conda_value = _format_tool_value(
        tools["conda"],
        color=color,
        abs_paths=abs_paths,
    )
    devpy_value = _format_tool_value(
        tools["devpy"],
        color=color,
        abs_paths=abs_paths,
    )
    return (
        f"{fmt.label('TOOLS', color)} "
        f"uv={uv_value} "
        f"conda={conda_value} "
        f"devpy={devpy_value}"
    )


def _hint_lines(
    hints: dict[str, list[str]], *, color: bool, abs_paths: bool
) -> list[str]:
    return fmt.hint_lines(
        [
            (
                key,
                fmt.variable(
                    fmt.format_command_hint(value, abs_paths=abs_paths), color
                ),
            )
            for key, value in sorted(hints.items())
        ],
        color=color,
    )


def _project_name_pairs(
    project: ProjectEnvironment,
    *,
    color: bool,
) -> list[tuple[str, str]]:
    root_name = Path(project.root).name
    if not project.pyproject_name or project.pyproject_name == root_name:
        return []
    return [("name", fmt.name(project.pyproject_name, color))]


def _python3_rows(
    python: ToolFact,
    python3: ToolFact,
    *,
    color: bool,
    abs_paths: bool,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    if not python3.available:
        return [], [("python3", fmt.state("missing", color))]
    if not python3.path:
        return [], [("python3", fmt.state(python3.status, color))]
    if python.path and Path(python.path).parent == Path(python3.path).parent:
        return [], [("python3", fmt.state("yes", color))]
    return [("python3", fmt.path(python3.path, color, abs_paths=abs_paths))], []


def _format_compact_python3(
    python: ToolFact,
    python3: ToolFact,
    *,
    color: bool,
    abs_paths: bool,
) -> str:
    if (
        python.path
        and python3.path
        and Path(python.path).parent == Path(python3.path).parent
    ):
        return fmt.state("yes", color)
    return _format_tool_value(python3, color=color, abs_paths=abs_paths)


def _format_compact_project_name(
    project: ProjectEnvironment,
    *,
    color: bool,
) -> str:
    pairs = _project_name_pairs(project, color=color)
    if not pairs:
        return ""
    key, value = pairs[0]
    return f"{key}={value} "

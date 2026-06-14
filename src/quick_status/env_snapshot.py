"""Environment snapshot collection for quick_status."""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quick_status.commands import run_command
from quick_status.models import (
    ENV_SCHEMA_VERSION,
    CommandRecord,
    EnvSnapshot,
    ProjectEnvironment,
    PythonRuntimeInfo,
    ShellState,
    ToolFact,
    VeneerProject,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


PROJECT_MARKERS = (
    "veneer.toml",
    "notuv.toml",
    "devpy.toml",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    ".python-version",
    "environment.yml",
    "conda-lock.yml",
)


def collect_env_snapshot(
    cwd: Path,
    *,
    include_commands: bool = False,
    probe_versions: bool = False,
    env: Mapping[str, str] | None = None,
) -> EnvSnapshot:
    """Collect a read-only Python/worktree environment snapshot.

    The collector treats Python, conda, veneer, and uv as optional facts.
    Missing tools are reported in the snapshot instead of raising, so this
    command remains useful on minimal machines.
    """
    actual_env = os.environ if env is None else env
    resolved_cwd = cwd.expanduser().resolve()
    command_records: list[CommandRecord] = []

    python_commands = {
        name: _command_tool_fact(
            name,
            cwd=resolved_cwd,
            env=actual_env,
            include_commands=include_commands,
            command_records=command_records,
            probe_version=probe_versions,
        )
        for name in ("python", "python3")
    }
    tools = {
        name: _command_tool_fact(
            name,
            cwd=resolved_cwd,
            env=actual_env,
            include_commands=include_commands,
            command_records=command_records,
            probe_version=probe_versions and name != "veneer",
        )
        for name in ("git", "uv", "conda", "veneer", "pip", "pip3")
    }
    project_root, root_source = _project_root(
        resolved_cwd,
        git_tool=tools["git"],
        include_commands=include_commands,
        command_records=command_records,
    )
    project = _project_environment(
        cwd=resolved_cwd,
        root=project_root,
        root_source=root_source,
    )
    veneer = _veneer_project(project_root)
    hints = _execution_hints(veneer=veneer)

    return EnvSnapshot(
        schema_version=ENV_SCHEMA_VERSION,
        shell=_shell_state(resolved_cwd, actual_env),
        runtime=_runtime_info(),
        python_commands=python_commands,
        project=project,
        veneer=veneer,
        tools=tools,
        hints=hints,
        commands=command_records,
    )


def _command_tool_fact(
    name: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    include_commands: bool,
    command_records: list[CommandRecord],
    probe_version: bool = False,
) -> ToolFact:
    path = shutil.which(name, path=env.get("PATH"))
    if path is None:
        return ToolFact(name=name, available=False, status="not_found")
    resolved = str(Path(path).resolve())
    if not probe_version:
        return ToolFact(
            name=name,
            available=True,
            path=path,
            realpath=resolved,
            status="ok",
        )
    result = run_command([resolved, "--version"], cwd=cwd, timeout_s=2.0)
    if include_commands:
        command_records.append(result.evidence())
    version = (result.stdout.strip() or result.stderr.strip()).splitlines()
    if result.timed_out:
        return ToolFact(
            name=name,
            available=True,
            path=path,
            realpath=resolved,
            status="timed_out",
            error="version command timed out",
        )
    if not result.ok:
        return ToolFact(
            name=name,
            available=True,
            path=path,
            realpath=resolved,
            status="failed",
            error=result.stderr.strip() or result.stdout.strip() or "version failed",
        )
    return ToolFact(
        name=name,
        available=True,
        path=path,
        realpath=resolved,
        version=version[0] if version else None,
        status="ok",
    )


def _project_root(
    cwd: Path,
    *,
    git_tool: ToolFact,
    include_commands: bool,
    command_records: list[CommandRecord],
) -> tuple[Path, str]:
    if git_tool.available and git_tool.path:
        result = run_command([git_tool.path, "rev-parse", "--show-toplevel"], cwd=cwd)
        if include_commands:
            command_records.append(result.evidence())
        if result.ok:
            return Path(result.stdout.strip()).resolve(), "git"
    marker_root = _nearest_marker_root(cwd)
    if marker_root is not None:
        return marker_root, "marker"
    return cwd, "cwd"


def _nearest_marker_root(cwd: Path) -> Path | None:
    for candidate in (cwd, *cwd.parents):
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return None


def _project_environment(
    *,
    cwd: Path,
    root: Path,
    root_source: str,
) -> ProjectEnvironment:
    pyproject_path = root / "pyproject.toml"
    pyproject_name: str | None = None
    requires_python: str | None = None
    pyproject_status = "missing"
    pyproject_error: str | None = None
    if pyproject_path.exists():
        try:
            data = _load_toml(pyproject_path)
        except tomllib.TOMLDecodeError as exc:
            pyproject_status = "parse_error"
            pyproject_error = str(exc)
        else:
            project = data.get("project")
            if isinstance(project, dict):
                pyproject_name = _optional_str(project.get("name"))
                requires_python = _optional_str(project.get("requires-python"))
            pyproject_status = "ok"

    venv_path = root / ".venv"
    return ProjectEnvironment(
        cwd=str(cwd),
        root=str(root),
        root_source=root_source,
        name=pyproject_name or root.name,
        pyproject_path=str(pyproject_path) if pyproject_path.exists() else None,
        pyproject_name=pyproject_name,
        requires_python=requires_python,
        pyproject_status=pyproject_status,
        pyproject_error=pyproject_error,
        uv_lock=(root / "uv.lock").exists(),
        requirements_txt=(root / "requirements.txt").exists(),
        python_version_file=(root / ".python-version").exists(),
        environment_yml=(root / "environment.yml").exists(),
        conda_lock_yml=(root / "conda-lock.yml").exists(),
        venv_path=str(venv_path),
        venv_exists=venv_path.exists(),
        venv_python_exists=(venv_path / "bin" / "python").exists(),
    )


def _veneer_project(root: Path) -> VeneerProject:
    # Prefer veneer.toml, then notuv.toml, then devpy.toml for backward compat.
    path: Path | None = None
    for candidate_name in ("veneer.toml", "notuv.toml", "devpy.toml"):
        candidate = root / candidate_name
        if candidate.exists():
            path = candidate
            break
    if path is None:
        return VeneerProject(present=False)
    try:
        data = _load_toml(path)
    except tomllib.TOMLDecodeError as exc:
        return VeneerProject(
            present=True,
            path=str(path),
            status="parse_error",
            error=str(exc),
        )

    python_config = data.get("python")
    editables_config = data.get("editables")
    base_conda_env = None
    venv_name = ".venv"
    if isinstance(python_config, dict):
        base_conda_env = _optional_str(python_config.get("base_conda_env"))
        venv_name = _optional_str(python_config.get("venv")) or ".venv"
    editable_paths: list[str] = []
    install_deps: bool | None = None
    if isinstance(editables_config, dict):
        packages = editables_config.get("packages")
        if isinstance(packages, list):
            editable_paths = [str(item) for item in packages if isinstance(item, str)]
        install_deps_value = editables_config.get("install_deps")
        if isinstance(install_deps_value, bool):
            install_deps = install_deps_value

    venv_path = root / venv_name
    return VeneerProject(
        present=True,
        path=str(path),
        status="ok",
        base_conda_env=base_conda_env,
        venv_path=str(venv_path),
        venv_exists=venv_path.exists(),
        venv_python_exists=(venv_path / "bin" / "python").exists(),
        editable_count=len(editable_paths),
        editable_paths=editable_paths,
        install_deps=install_deps,
    )


def _execution_hints(
    *,
    veneer: VeneerProject,
) -> dict[str, list[str]]:
    if not veneer.present or veneer.status != "ok":
        return {}
    return {"veneer_python": ["veneer", "python"]}


def _shell_state(cwd: Path, env: Mapping[str, str]) -> ShellState:
    conda_default_env = _empty_to_none(env.get("CONDA_DEFAULT_ENV"))
    conda_prefix = _empty_to_none(env.get("CONDA_PREFIX"))
    conda_shlvl = _empty_to_none(env.get("CONDA_SHLVL"))
    virtual_env = _empty_to_none(env.get("VIRTUAL_ENV"))
    conda_active = bool(conda_prefix) or (
        bool(conda_default_env)
        and conda_default_env != "none"
        and conda_shlvl not in {None, "0"}
    )
    venv_active = bool(virtual_env)
    if conda_active and venv_active:
        kind = "conda+venv"
    elif conda_active:
        kind = "conda"
    elif venv_active:
        kind = "venv"
    else:
        kind = "neutral"
    return ShellState(
        cwd=str(cwd),
        kind=kind,
        conda_active=conda_active,
        conda_default_env=conda_default_env,
        conda_prefix=conda_prefix,
        conda_shlvl=conda_shlvl,
        virtual_env=virtual_env,
        venv_active=venv_active,
    )


def _runtime_info() -> PythonRuntimeInfo:
    return PythonRuntimeInfo(
        executable=sys.executable,
        version=platform.python_version(),
        implementation=platform.python_implementation(),
        prefix=sys.prefix,
        base_prefix=sys.base_prefix,
        venv_like=sys.prefix != sys.base_prefix,
    )


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _empty_to_none(value: str | None) -> str | None:
    return value if value else None

"""Tests for quick_status environment snapshots."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

from quick_status.env_snapshot import collect_env_snapshot

if TYPE_CHECKING:
    from pathlib import Path


def test_env_snapshot_reports_missing_python_present_python3(
    tmp_path: Path,
) -> None:
    """Missing optional Python commands should become facts, not errors."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "python3", "Python 3.11.9")
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    snapshot = collect_env_snapshot(
        project,
        env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
    )

    assert snapshot.project.name == "demo"
    assert snapshot.python_commands["python"].status == "not_found"
    assert snapshot.python_commands["python3"].status == "ok"
    assert snapshot.python_commands["python3"].version is None
    assert snapshot.tools["conda"].status == "not_found"
    assert snapshot.tools["devpy"].status == "not_found"


def test_env_snapshot_probes_versions_only_when_requested(tmp_path: Path) -> None:
    """Default env collection stays fast; verbose mode asks tools for versions."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_executable(bin_dir / "python3", "Python 3.11.9")
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    fast_snapshot = collect_env_snapshot(
        project,
        env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
    )
    verbose_snapshot = collect_env_snapshot(
        project,
        probe_versions=True,
        env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
    )

    assert fast_snapshot.python_commands["python3"].status == "ok"
    assert fast_snapshot.python_commands["python3"].version is None
    assert verbose_snapshot.python_commands["python3"].version == "Python 3.11.9"


def test_env_snapshot_parses_devpy_without_devpy_or_conda(tmp_path: Path) -> None:
    """devpy.toml declares project intent even when devpy/conda are missing."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "devpy.toml").write_text(
        "\n".join(
            [
                "[python]",
                'base_conda_env = "mdp_shared"',
                'venv = ".venv"',
                "",
                "[editables]",
                'packages = [".", "external/GMR"]',
                "install_deps = false",
            ],
        ),
    )
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").write_text("")

    snapshot = collect_env_snapshot(
        project,
        env={"PATH": "", "HOME": str(tmp_path)},
    )

    assert snapshot.devpy.present is True
    assert snapshot.devpy.status == "ok"
    assert snapshot.devpy.base_conda_env == "mdp_shared"
    assert snapshot.devpy.venv_python_exists is True
    assert snapshot.devpy.editable_count == 2
    assert snapshot.tools["conda"].status == "not_found"
    assert snapshot.tools["devpy"].status == "not_found"
    assert snapshot.hints == {"devpy_python": ["devpy", "python"]}


def test_env_snapshot_reports_malformed_toml_and_continues(tmp_path: Path) -> None:
    """Malformed project TOML should not prevent collecting other env facts."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project\n")
    (project / "devpy.toml").write_text("[python\n")

    snapshot = collect_env_snapshot(
        project,
        env={"PATH": "", "HOME": str(tmp_path)},
    )

    assert snapshot.project.pyproject_status == "parse_error"
    assert snapshot.project.name == "project"
    assert snapshot.devpy.present is True
    assert snapshot.devpy.status == "parse_error"
    assert snapshot.python_commands["python"].status == "not_found"


def test_env_snapshot_detects_shell_conda_and_venv(tmp_path: Path) -> None:
    """Shell state should keep conda and venv layering explicit."""
    snapshot = collect_env_snapshot(
        tmp_path,
        env={
            "PATH": "",
            "HOME": str(tmp_path),
            "CONDA_DEFAULT_ENV": "mdp_shared",
            "CONDA_PREFIX": str(tmp_path / "conda" / "envs" / "mdp_shared"),
            "CONDA_SHLVL": "1",
            "VIRTUAL_ENV": str(tmp_path / "project" / ".venv"),
        },
    )

    assert snapshot.shell.kind == "conda+venv"
    assert snapshot.shell.conda_active is True
    assert snapshot.shell.venv_active is True


def _fake_executable(path: Path, output: str) -> None:
    path.write_text(f"#!/bin/sh\necho '{output}'\n")
    path.chmod(stat.S_IRWXU)

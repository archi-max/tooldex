"""Tests for the Codex CLI integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tooldex.cli.codex import execute_codex, init_codex_config
from tooldex.core.config import ConfigError


def test_execute_codex_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text(
        "[tooldex]\n"
        "binary = 'codex'\n"
        "args = ['--fast']\n"
        "config_flag = '--config'\n"
        "terminal_mcp = 'tooldex-shell'\n"
        "[tooldex.env]\n"
        "FOO = 'bar'\n"
        "[codex]\n"
        "model = 'gpt-5-codex'\n"
        "approval_policy = 'on-request'\n"
        "[codex.mcp_servers.tooldex-shell]\n"
        "command = 'uv'\n"
        "args = ['run', 'python']\n"
        "[codex.mcp_servers.tooldex-shell.env]\n"
        "PYTHONUNBUFFERED = '1'\n",
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def fake_call(cmd, env):
        captured["cmd"] = cmd
        captured["env"] = env
        return 0

    monkeypatch.setenv("PATH", "")  # ensure call relies on binary string only
    monkeypatch.setenv("TOOLDEX_PRIMARY_PANE", "%42")
    monkeypatch.setattr("subprocess.call", fake_call)

    exit_code = execute_codex(str(config_file), ["--", "--hello"])

    assert exit_code == 0
    assert captured["cmd"][0] == "codex"
    assert "--fast" in captured["cmd"]
    assert captured["cmd"][-1] == "--hello"

    config_entries: dict[str, str] = {}
    for index, token in enumerate(captured["cmd"]):
        if token != "--config":
            continue
        value_index = index + 1
        assert value_index < len(captured["cmd"])
        key, value = captured["cmd"][value_index].split("=", 1)
        config_entries[key] = value

    assert config_entries["model"] == '"gpt-5-codex"'
    assert config_entries["approval_policy"] == '"on-request"'
    assert config_entries["mcp_servers.tooldex-shell.command"] == '"uv"'
    assert config_entries["mcp_servers.tooldex-shell.args"] == '["run", "python"]'
    assert config_entries["mcp_servers.tooldex-shell.env.PYTHONUNBUFFERED"] == '"1"'
    assert (
        config_entries["mcp_servers.tooldex-shell.env.TOOLDEX_PRIMARY_PANE"] == '"%42"'
    )
    assert captured["env"]["FOO"] == "bar"


def test_init_codex_config_writes_template(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "codex.toml"
    monkeypatch.setattr("tooldex.cli.codex.default_user_codex_config_path", lambda: target)

    destination = init_codex_config(None, False)

    assert destination == target
    assert target.exists()
    assert target.read_text(encoding="utf-8").strip().startswith("[tooldex]")


def test_init_codex_config_overwrite_requires_force(tmp_path: Path) -> None:
    target = tmp_path / "codex.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    with pytest.raises(ConfigError):
        init_codex_config(str(target), force=False)

    destination = init_codex_config(str(target), force=True)

    assert destination == target
    assert destination.read_text(encoding="utf-8").strip().startswith("[tooldex]")

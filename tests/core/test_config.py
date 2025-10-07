"""Tests for ToolDex core configuration helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tooldex.core.config import ConfigError, load_codex_config, resolve_codex_config_path


def test_resolve_codex_config_prefers_explicit_path(tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text("[tooldex]\nbinary = 'codex'\n", encoding="utf-8")

    resolved = resolve_codex_config_path(str(config_file))

    assert resolved == config_file


def test_resolve_codex_config_uses_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text("[tooldex]\nbinary = 'codex'\n", encoding="utf-8")

    monkeypatch.delenv("TOOLDEX_CODEX_CONFIG", raising=False)
    monkeypatch.setenv("TOOLDEX_CODEX_CONFIG", str(config_file))

    resolved = resolve_codex_config_path(None)

    assert resolved == config_file


def test_resolve_codex_config_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOOLDEX_CODEX_CONFIG", raising=False)
    monkeypatch.delenv("TOOLDEX_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    resolved = resolve_codex_config_path(None)

    assert resolved.name == "codex.toml"
    assert "configs" in str(resolved.parent)


def test_load_codex_config_valid(tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text(
        "[tooldex]\n"
        "binary = 'codex'\n"
        "args = ['--fast']\n"
        "config_flag = '--config'\n"
        "terminal_mcp = 'tooldex-shell'\n"
        "[tooldex.env]\n"
        "FOO = 'bar'\n"
        "BAR = 123\n"
        "[codex]\n"
        "model = 'gpt-5-codex'\n"
        "approval_policy = 'never'\n"
        "[codex.mcp_servers.tooldex-shell]\n"
        "command = 'uv'\n"
        "args = ['run']\n",
        encoding="utf-8",
    )

    config = load_codex_config(config_file)

    assert config.binary == "codex"
    assert config.args == ["--fast"]
    assert config.config_flag == "--config"
    assert config.env == {"FOO": "bar", "BAR": "123"}
    assert config.terminal_mcp_id == "tooldex-shell"
    assert config.overrides["model"] == "gpt-5-codex"
    assert config.overrides["approval_policy"] == "never"
    assert config.overrides["mcp_servers"]["tooldex-shell"]["command"] == "uv"


def test_load_codex_config_rejects_invalid_args(tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text(
        "[tooldex]\n"
        "binary = 'codex'\n"
        "args = 'not-a-list'\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_codex_config(config_file)


def test_load_codex_config_rejects_invalid_env(tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text(
        "[tooldex]\n"
        "binary = 'codex'\n"
        "[tooldex.env]\n"
        "FOO = { invalid = 'mapping' }\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_codex_config(config_file)


def test_load_codex_config_requires_tooldex_table(tmp_path: Path) -> None:
    config_file = tmp_path / "codex.toml"
    config_file.write_text("model = 'o3'\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_codex_config(config_file)

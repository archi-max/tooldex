"""Configuration helpers for invoking external ToolDex integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import tomllib


class ConfigError(RuntimeError):
    """Raised when configuration loading fails."""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_codex_config_path() -> Path:
    return _project_root() / "configs" / "codex.toml"


def _search_directories() -> Sequence[Path]:
    """Return potential directories that may contain ToolDex configs."""

    candidates: list[Path] = []

    cwd_config = Path.cwd() / ".tooldex"
    candidates.append(cwd_config)

    env_config_dir = os.environ.get("TOOLDEX_CONFIG_DIR")
    if env_config_dir:
        candidates.append(Path(env_config_dir).expanduser())

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        candidates.append(Path(xdg_config_home).expanduser() / "tooldex")
    else:
        candidates.append(Path.home() / ".config" / "tooldex")

    candidates.append(Path.home() / ".tooldex")
    return candidates


def resolve_codex_config_path(explicit_path: str | None) -> Path:
    """Determine which Codex config file should be used."""

    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if not candidate.is_file():
            raise ConfigError(f"Codex config '{candidate}' does not exist.")
        return candidate

    env_path = os.environ.get("TOOLDEX_CODEX_CONFIG")
    if env_path:
        candidate = Path(env_path).expanduser()
        if not candidate.is_file():
            raise ConfigError(f"Environment Codex config '{candidate}' does not exist.")
        return candidate

    for directory in _search_directories():
        candidate = directory / "codex.toml"
        if candidate.is_file():
            return candidate

    default_path = _default_codex_config_path()
    if not default_path.is_file():
        raise ConfigError("Built-in Codex config could not be located.")
    return default_path


@dataclass(slots=True)
class CodexConfig:
    """Structured Codex CLI configuration."""

    binary: str
    args: Sequence[str]
    env: Mapping[str, str]
    config_flag: str | None
    terminal_mcp_id: str | None
    overrides: Mapping[str, Any]


def load_codex_config(path: Path) -> CodexConfig:
    """Load and validate the Codex configuration from TOML."""

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Codex config '{path}' could not be read.") from exc

    tooldex_section = data.get("tooldex")
    if tooldex_section is None:
        raise ConfigError("Codex config must define a [tooldex] table.")

    if not isinstance(tooldex_section, dict):
        raise ConfigError("[tooldex] must be a table.")

    try:
        binary = tooldex_section["binary"]
    except KeyError as exc:
        raise ConfigError("[tooldex] table must define 'binary'.") from exc

    args = tooldex_section.get("args", [])
    if not isinstance(args, list):
        raise ConfigError("[tooldex].args must be a list when provided.")

    config_flag = tooldex_section.get("config_flag", "--config")
    if config_flag is not None and not isinstance(config_flag, str):
        raise ConfigError("[tooldex].config_flag must be a string when provided.")

    env_section = tooldex_section.get("env", {})
    if not isinstance(env_section, dict):
        raise ConfigError("[tooldex].env must be a table when provided.")

    env_mapping: MutableMapping[str, str] = {}
    for key, value in env_section.items():
        if not isinstance(value, (str, int, float, bool)):
            raise ConfigError(f"[tooldex].env value for '{key}' must be scalar.")
        env_mapping[str(key)] = str(value)

    terminal_mcp_id = tooldex_section.get("terminal_mcp")
    if terminal_mcp_id is not None and not isinstance(terminal_mcp_id, str):
        raise ConfigError("[tooldex].terminal_mcp must be a string when provided.")

    codex_section = data.get("codex", {})
    if not isinstance(codex_section, dict):
        raise ConfigError("[codex] must be a table when provided.")

    return CodexConfig(
        binary=str(binary),
        args=[str(arg) for arg in args],
        env=dict(env_mapping),
        config_flag=config_flag,
        terminal_mcp_id=terminal_mcp_id,
        overrides=codex_section,
    )


__all__ = ["CodexConfig", "ConfigError", "load_codex_config", "resolve_codex_config_path"]

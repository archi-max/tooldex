"""Codex CLI integration."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from tooldex.core.config import CodexConfig, ConfigError, load_codex_config, resolve_codex_config_path


def _determine_primary_pane() -> str | None:
    """Return the tmux pane ID for the user's primary shell, if available."""

    return os.environ.get("TOOLDEX_PRIMARY_PANE") or os.environ.get("TMUX_PANE")


def _flatten_overrides(overrides: Mapping[str, Any]) -> Mapping[str, Any]:
    """Flatten a nested mapping into dotted-key overrides."""

    flattened: dict[str, Any] = {}

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                new_prefix = f"{prefix}.{key}" if prefix else str(key)
                _walk(new_prefix, nested_value)
        else:
            flattened[prefix] = value

    for root_key, root_value in overrides.items():
        _walk(str(root_key), root_value)
    return flattened


def _quote_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_toml_value(value: Any) -> str:
    if isinstance(value, str):
        return _quote_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = ", ".join(_format_toml_value(item) for item in value)
        return f"[{items}]"
    if isinstance(value, Mapping):
        pairs = ", ".join(
            f"{_quote_string(str(k))} = {_format_toml_value(v)}" for k, v in value.items()
        )
        return f"{{{pairs}}}"
    raise ConfigError(f"Unsupported TOML value type: {type(value)!r}")


def _build_command(config: CodexConfig, overrides: Mapping[str, Any], extra_args: Sequence[str]) -> list[str]:
    command = [config.binary, *config.args]

    if config.config_flag:
        flattened = _flatten_overrides(overrides)
        for key, value in flattened.items():
            command.extend([config.config_flag, f"{key}={_format_toml_value(value)}"])

    command.extend(extra_args)
    return command


def execute_codex(config_override: str | None, extra_args: Sequence[str]) -> int:
    """Execute the Codex agent binary with ToolDex configuration."""

    config_path = resolve_codex_config_path(config_override)
    config = load_codex_config(config_path)

    forwarded_args = list(extra_args)
    if forwarded_args and forwarded_args[0] == "--":
        forwarded_args = forwarded_args[1:]

    overrides: dict[str, Any] = dict(config.overrides)

    if config.terminal_mcp_id:
        pane_id = _determine_primary_pane()
        if pane_id:
            mcp_servers = overrides.get("mcp_servers")
            if mcp_servers is None:
                mcp_servers = {}
            elif not isinstance(mcp_servers, Mapping):
                raise ConfigError("codex.mcp_servers must be a table when provided.")
            server_config = dict(mcp_servers.get(config.terminal_mcp_id, {}))
            env_config = dict(server_config.get("env", {}))
            env_config["TOOLDEX_PRIMARY_PANE"] = pane_id
            server_config["env"] = env_config
            combined_servers = dict(mcp_servers)
            combined_servers[config.terminal_mcp_id] = server_config
            overrides["mcp_servers"] = combined_servers
        else:
            print(
                "warning: TOOLDEX_PRIMARY_PANE not set; Codex terminal MCP may not attach to tmux.",
                file=sys.stderr,
            )

    command = _build_command(config, overrides, forwarded_args)
    env = os.environ.copy()
    env.update(config.env)

    try:
        exit_code = subprocess.call(command, env=env)
    except FileNotFoundError as exc:
        raise ConfigError(f"Codex binary '{config.binary}' was not found on PATH.") from exc
    if exit_code != 0:
        printable_cmd = shlex.join(command)
        print(f"warning: Codex exited with status {exit_code}. Command: {printable_cmd}", file=sys.stderr)
    return exit_code

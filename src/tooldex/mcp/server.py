"""MCP server exposing workspace shell and file utilities for tooldex.

This server is intended to back the secondary AI-controlled terminal pane. It provides
tools for running shell commands and capturing terminal output while keeping the user in
control of the primary shell.
"""

from __future__ import annotations

import asyncio
import asyncio.subprocess
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from uuid import uuid4

from typing_extensions import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

PRIMARY_PANE = os.environ.get("TOOLDEX_PRIMARY_PANE")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENT_GUIDE_PATH = PROJECT_ROOT / "docs" / "mcp" / "tooldex-shell-agent-guide.md"
DOC_RESOURCE_URI = "doc://tooldex/shell-guide"


class ShellResult(TypedDict):
    """Structured output for a shell command execution."""

    command: str
    target_pane: str
    submitted: bool
    triggered_enter: bool
    note: str


class PaneReadResult(TypedDict):
    """Structured output for tmux pane capture."""

    pane: str
    lines_requested: int
    lines_returned: int
    truncated: bool
    include_colors: bool
    content: list[str]


class PaneSubscriptionResult(TypedDict):
    """Information returned when a pane subscription is created."""

    token: str
    pane: str
    include_colors: bool
    lines_recorded: int
    initial_lines: list[str]
    initial_truncated: bool


class PaneUpdateResult(TypedDict):
    """Incremental update response for a pane subscription."""

    token: str
    pane: str
    new_lines: list[str]
    lines_recorded: int
    truncated: bool
    timed_out: bool


MCP_SERVER = FastMCP("tooldex-shell")


@dataclass
class PaneSubscription:
    pane: str
    include_colors: bool
    lines_recorded: int
    last_snapshot: list[str]
    snapshot_ready: bool


_pane_subscriptions: Dict[str, PaneSubscription] = {}


def _get_primary_tmux_pane() -> str:
    """Return the pane ID for the primary user shell."""
    pane = PRIMARY_PANE or os.environ.get("TMUX_PANE")
    if not pane:
        raise RuntimeError(
            "Primary tmux pane is unknown. Set TOOLDEX_PRIMARY_PANE before launching the MCP server."
        )
    return pane


async def _run_tmux_subprocess(*args: str) -> str:
    """Execute a tmux command and return STDOUT."""
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(
            f"tmux command {' '.join(args)} failed with exit code {process.returncode}: "
            f"{stdout.decode().strip()} {stderr.decode().strip()}"
        )
    return stdout.decode("utf-8")


@MCP_SERVER.tool()
async def run_shell(
    command: str,
    ctx: Context[ServerSession, None],
    *,
    send_enter: bool = True,
) -> ShellResult:
    """Send a command to the primary tmux pane instead of starting a new shell."""
    pane = _get_primary_tmux_pane()
    await ctx.info(f"Dispatching command to pane {pane}: {command!r}")

    await _run_tmux_subprocess("tmux", "send-keys", "-t", pane, command)
    if send_enter:
        await _run_tmux_subprocess("tmux", "send-keys", "-t", pane, "C-m")

    note = "Command dispatched to primary pane. Output will appear in-place."
    if not send_enter:
        note = "Command typed in primary pane without executing Enter."

    return {
        "command": command,
        "target_pane": pane,
        "submitted": True,
        "triggered_enter": send_enter,
        "note": note,
    }

async def _capture_pane_lines(pane: str, lines: int, include_colors: bool) -> tuple[list[str], bool]:
    """Capture the last N lines from a tmux pane."""
    if lines <= 0:
        raise ValueError("lines must be positive.")

    start = f"-{lines + 1}"
    args = ["tmux", "capture-pane", "-t", pane, "-p", "-S", start]
    if include_colors:
        args.append("-e")

    output = await _run_tmux_subprocess(*args)
    captured_lines = output.splitlines()
    truncated = len(captured_lines) > lines
    if truncated:
        captured_lines = captured_lines[-lines:]
    return captured_lines, truncated


async def _get_pane_line_count(pane: str) -> int:
    """Return total lines (history + height) for the given pane."""
    output = await _run_tmux_subprocess(
        "tmux",
        "display-message",
        "-p",
        "-t",
        pane,
        "#{pane_history} #{pane_height}",
    )
    parts = output.strip().split()
    if not parts:
        return 0
    try:
        history = int(parts[0])
        height = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        history = 0
        height = 0
    return history + height


@MCP_SERVER.tool()
async def read_primary_pane(
    ctx: Context[ServerSession, None],
    lines: int = 200,
    include_colors: bool = False,
) -> PaneReadResult:
    """Capture recent output from the primary tmux pane."""
    pane = _get_primary_tmux_pane()
    await ctx.info(f"Capturing last {lines} lines from pane {pane} (colors={include_colors}).")
    content, truncated = await _capture_pane_lines(pane, lines, include_colors)

    return {
        "pane": pane,
        "lines_requested": lines,
        "lines_returned": len(content),
        "truncated": truncated,
        "include_colors": include_colors,
        "content": content,
    }


@MCP_SERVER.tool()
async def subscribe_primary_pane(
    ctx: Context[ServerSession, None],
    include_colors: bool = False,
    initial_lines: int = 0,
) -> PaneSubscriptionResult:
    """Begin tracking incremental updates from the primary pane."""
    pane = _get_primary_tmux_pane()
    total_lines = await _get_pane_line_count(pane)
    requested_lines = max(0, min(initial_lines, total_lines))
    initial_content: list[str] = []
    initial_truncated = False
    if requested_lines > 0:
        initial_content, initial_truncated = await _capture_pane_lines(
            pane, requested_lines, include_colors
        )

    token = uuid4().hex
    _pane_subscriptions[token] = PaneSubscription(
        pane=pane,
        include_colors=include_colors,
        lines_recorded=total_lines,
        last_snapshot=initial_content,
        snapshot_ready=bool(initial_content),
    )

    await ctx.info(
        f"Subscribed to pane {pane} with token {token}; lines_recorded={total_lines}."
    )
    return {
        "token": token,
        "pane": pane,
        "include_colors": include_colors,
        "lines_recorded": total_lines,
        "initial_lines": initial_content,
        "initial_truncated": initial_truncated,
    }


@MCP_SERVER.tool()
async def fetch_primary_pane_updates(
    ctx: Context[ServerSession, None],
    token: str,
    timeout_seconds: float = 1.0,
    max_lines: int = 200,
    poll_interval: float = 0.2,
) -> PaneUpdateResult:
    """Retrieve incremental updates for an active pane subscription."""
    if token not in _pane_subscriptions:
        raise KeyError(f"No active subscription for token {token}.")

    state = _pane_subscriptions[token]
    pane = state.pane
    deadline = time.monotonic() + max(timeout_seconds, 0.0)

    while True:
        total_lines = await _get_pane_line_count(pane)
        diff = total_lines - state.lines_recorded
        snapshot_limit = max(1, max(max_lines, len(state.last_snapshot)))

        if diff > 0:
            capture_count = max(1, min(max_lines, diff))
            new_content, was_truncated = await _capture_pane_lines(
                pane, capture_count, state.include_colors
            )
            state.lines_recorded = total_lines
            # Maintain a rolling snapshot for redraw detection.
            combined_snapshot = state.last_snapshot + new_content
            state.last_snapshot = combined_snapshot[-snapshot_limit:]
            state.snapshot_ready = True
            _pane_subscriptions[token] = state
            truncated = was_truncated or diff > max_lines
            await ctx.debug(
                f"Subscription {token} captured {len(new_content)} new lines (truncated={truncated})."
            )
            return {
                "token": token,
                "pane": pane,
                "new_lines": new_content,
                "lines_recorded": total_lines,
                "truncated": truncated,
                "timed_out": False,
            }

        new_snapshot, snapshot_truncated = await _capture_pane_lines(
            pane, snapshot_limit, state.include_colors
        )

        if not state.snapshot_ready:
            state.last_snapshot = new_snapshot[-snapshot_limit:]
            state.snapshot_ready = True
            state.lines_recorded = total_lines
            _pane_subscriptions[token] = state
        elif new_snapshot != state.last_snapshot:
            state.last_snapshot = new_snapshot[-snapshot_limit:]
            state.lines_recorded = total_lines
            _pane_subscriptions[token] = state
            truncated = snapshot_truncated
            await ctx.debug(
                f"Subscription {token} detected pane redraw; emitting {len(new_snapshot)} lines."
            )
            return {
                "token": token,
                "pane": pane,
                "new_lines": new_snapshot,
                "lines_recorded": total_lines,
                "truncated": truncated,
                "timed_out": False,
            }
        else:
            state.last_snapshot = new_snapshot[-snapshot_limit:]
            state.lines_recorded = total_lines
            _pane_subscriptions[token] = state

        if time.monotonic() >= deadline:
            return {
                "token": token,
                "pane": pane,
                "new_lines": [],
                "lines_recorded": state.lines_recorded,
                "truncated": False,
                "timed_out": True,
            }

        await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))


@MCP_SERVER.tool()
def unsubscribe_primary_pane(token: str) -> bool:
    """Remove a previously created pane subscription."""
    return _pane_subscriptions.pop(token, None) is not None


@MCP_SERVER.resource(DOC_RESOURCE_URI)
def agent_guide() -> str:
    """Return the agent-facing documentation for this MCP server."""
    if not AGENT_GUIDE_PATH.is_file():
        raise FileNotFoundError(
            f"Agent guide not found at {AGENT_GUIDE_PATH}. Ensure documentation is installed."
        )
    return AGENT_GUIDE_PATH.read_text(encoding="utf-8")


def run() -> None:
    """Entry point used by `uv run mcp run` or direct execution."""
    MCP_SERVER.run()


__all__ = [
    "MCP_SERVER",
    "run",
    "run_shell",
    "read_primary_pane",
    "subscribe_primary_pane",
    "fetch_primary_pane_updates",
    "unsubscribe_primary_pane",
    "DOC_RESOURCE_URI",
]

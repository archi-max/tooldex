from __future__ import annotations

import asyncio
from collections import deque

import pytest

from tooldex.mcp import server as mcp_server


class DummyContext:
    """Minimal stub for the FastMCP Context used in tests."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def info(self, message: str) -> None:
        self.messages.append(("info", message))

    async def warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    async def warn(self, message: str) -> None:  # Backwards compatibility alias.
        await self.warning(message)

    async def debug(self, message: str) -> None:
        self.messages.append(("debug", message))

    async def error(self, message: str) -> None:
        self.messages.append(("error", message))


def test_run_shell_executes_command(monkeypatch):
    monkeypatch.setattr(mcp_server, "PRIMARY_PANE", "%1")

    tmux_calls: list[tuple[str, ...]] = []

    async def fake_tmux(*args: str) -> str:
        tmux_calls.append(args)
        return ""

    monkeypatch.setattr(mcp_server, "_run_tmux_subprocess", fake_tmux)

    ctx = DummyContext()
    result = asyncio.run(mcp_server.run_shell("printf 'hello'", ctx))

    assert result["target_pane"] == "%1"
    assert result["submitted"] is True
    assert result["triggered_enter"] is True
    assert "primary pane" in result["note"]
    assert tmux_calls == [
        ("tmux", "send-keys", "-t", "%1", "printf 'hello'"),
        ("tmux", "send-keys", "-t", "%1", "C-m"),
    ]

    info_messages = [message for level, message in ctx.messages if level == "info"]
    assert any(message.startswith("Dispatching command") for message in info_messages)


def test_read_primary_pane(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server, "PRIMARY_PANE", "%42")

    tmux_calls: list[tuple[str, ...]] = []

    async def fake_tmux(*args: str) -> str:
        tmux_calls.append(args)
        return "line1\nline2\nline3"

    monkeypatch.setattr(mcp_server, "_run_tmux_subprocess", fake_tmux)

    ctx = DummyContext()
    result = asyncio.run(mcp_server.read_primary_pane(ctx, lines=2))

    assert result["pane"] == "%42"
    assert result["lines_requested"] == 2
    assert result["lines_returned"] == 2
    assert result["truncated"] is True
    assert result["content"] == ["line2", "line3"]
    assert tmux_calls and tmux_calls[0][0:3] == ("tmux", "capture-pane", "-t")


def test_subscription_updates(monkeypatch):
    monkeypatch.setattr(mcp_server, "PRIMARY_PANE", "%5")

    tmux_calls: list[tuple[str, ...]] = []
    display_values = deque(["3 2", "4 2"])
    capture_values = deque(["line4\nline5\n"])

    async def fake_tmux(*args: str) -> str:
        tmux_calls.append(args)
        if args[1] == "display-message":
            return f"{display_values.popleft()}\n"
        if args[1] == "capture-pane":
            return capture_values.popleft()
        raise AssertionError(f"Unexpected tmux call: {args}")

    async def fake_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(mcp_server, "_run_tmux_subprocess", fake_tmux)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    ctx = DummyContext()
    sub = asyncio.run(mcp_server.subscribe_primary_pane(ctx))
    token = sub["token"]
    assert sub["lines_recorded"] == 5

    update = asyncio.run(
        mcp_server.fetch_primary_pane_updates(
            ctx,
            token=token,
            timeout_seconds=1.0,
            max_lines=5,
        )
    )

    assert update["timed_out"] is False
    assert update["new_lines"] == ["line5"]
    assert update["lines_recorded"] == 6
    assert tmux_calls[0][1] == "display-message"
    assert tmux_calls[-1][1] == "capture-pane"

    assert mcp_server.unsubscribe_primary_pane(token) is True
    assert mcp_server.unsubscribe_primary_pane(token) is False


def test_agent_guide_resource() -> None:
    guide = mcp_server.agent_guide()
    assert guide.startswith("# Tooldex Shell MCP Guide")

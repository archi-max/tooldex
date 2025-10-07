"""Tests for the ToolDex tool wrapper helpers."""

from __future__ import annotations

import subprocess

import pytest

from tooldex import tool_wrapper


def test_parse_args_default_trigger_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(tool_wrapper, "DEFAULT_TRIGGER_KEY", "z", raising=False)
    monkeypatch.setattr(
        tool_wrapper.sys,
        "argv",
        ["tool_wrapper.py", "--", "printf", "hello"],
    )

    args = tool_wrapper.parse_args()

    assert args.trigger_key == "z"


def test_cleanup_utilities_terminates_panes_and_processes(monkeypatch: pytest.MonkeyPatch) -> None:
    killed_panes: list[list[str]] = []

    def fake_check_call(cmd, *_, **__):
        killed_panes.append(cmd)
        return 0

    class DummyProc:
        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

    dummy_proc = DummyProc()

    monkeypatch.setattr(tool_wrapper, "UTILITY_PANES", {"%99"})
    monkeypatch.setattr(tool_wrapper, "UTILITY_PROCS", [dummy_proc])
    monkeypatch.setattr(tool_wrapper, "in_tmux", lambda: True)
    monkeypatch.setattr(subprocess, "check_call", fake_check_call)

    tool_wrapper._cleanup_utilities()

    assert killed_panes == [["tmux", "kill-pane", "-t", "%99"]]
    assert dummy_proc.terminated is True
    assert tool_wrapper.UTILITY_PANES == set()
    assert tool_wrapper.UTILITY_PROCS == []

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


def test_default_utility_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTILITY_CMD", "custom")
    monkeypatch.setattr(tool_wrapper.shutil, "which", lambda _: "/usr/bin/tooldex")
    result = tool_wrapper._default_utility_factory()

    assert result == "custom"


def test_default_utility_prefers_toolexecutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_CMD", raising=False)
    monkeypatch.setattr(tool_wrapper.shutil, "which", lambda cmd: "/usr/bin/tooldex" if cmd == "tooldex" else None)

    result = tool_wrapper._default_utility_factory()

    assert result == "tooldex codex"


def test_default_utility_falls_back_to_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_CMD", raising=False)
    monkeypatch.setattr(tool_wrapper.shutil, "which", lambda _: None)
    monkeypatch.setattr(tool_wrapper.sys, "executable", "/custom/python")

    result = tool_wrapper._default_utility_factory()

    assert result == "/custom/python -m tooldex codex"

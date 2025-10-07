"""Tests for the utility launcher module."""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from tooldex import utility_launcher


class DummyProc:
    def __init__(self, exit_code: int) -> None:
        self._exit_code = exit_code

    def wait(self) -> int:
        return self._exit_code


def test_main_runs_command_without_hold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TOOLDEX_UTILITY_CMD", "run-something")
    monkeypatch.setenv("TOOLDEX_UTILITY_HOLD", "0")
    monkeypatch.setenv("TOOLDEX_UTILITY_LOG", str(tmp_path / "utility.log"))
    monkeypatch.setattr("tooldex.utility_launcher.subprocess.Popen", lambda cmd, shell: DummyProc(0))

    def fail_input() -> None:
        raise AssertionError("input should not be called on success")

    monkeypatch.setattr(builtins, "input", fail_input)

    exit_code = utility_launcher.main()

    assert exit_code == 0


def test_main_holds_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOLDEX_UTILITY_CMD", "run-something")
    monkeypatch.delenv("TOOLDEX_UTILITY_HOLD", raising=False)
    monkeypatch.setattr("tooldex.utility_launcher.subprocess.Popen", lambda cmd, shell: DummyProc(2))

    calls: list[str] = []

    def fake_input(prompt: str | None = None) -> None:
        calls.append("input")
        return None

    monkeypatch.setattr(builtins, "input", fake_input)

    exit_code = utility_launcher.main()

    assert exit_code == 2
    assert calls == ["input"]


def test_main_handles_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOOLDEX_UTILITY_CMD", raising=False)

    exit_code = utility_launcher.main()

    assert exit_code == 2

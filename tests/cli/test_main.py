from __future__ import annotations

from pathlib import Path

import pytest

from tooldex.__main__ import main


def test_main_uses_global_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_execute(config: str | None, extra_args: list[str]) -> int:
        captured["config"] = config
        captured["args"] = extra_args
        return 0

    monkeypatch.setattr("tooldex.__main__.execute_codex", fake_execute)

    config_path = tmp_path / "codex.toml"
    exit_code = main(["--config", str(config_path), "codex"])

    assert exit_code == 0
    assert captured["config"] == str(config_path)
    assert captured["args"] == []


def test_main_prefers_subcommand_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_execute(config: str | None, extra_args: list[str]) -> int:
        captured["config"] = config
        captured["args"] = extra_args
        return 0

    monkeypatch.setattr("tooldex.__main__.execute_codex", fake_execute)

    global_config = tmp_path / "global.toml"
    local_config = tmp_path / "local.toml"
    exit_code = main(
        ["--config", str(global_config), "codex", "--config", str(local_config), "--", "--foo"]
    )

    assert exit_code == 0
    assert captured["config"] == str(local_config)
    assert captured["args"] == ["--foo"]

"""Helper used inside utility panes to execute commands with diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _log_message(log_file: Path | None, message: str) -> None:
    if log_file is None:
        return
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] {message}\n")
    except OSError:
        # If logging fails we still continue so the utility session works.
        pass


def main() -> int:
    command = os.environ.get("TOOLDEX_UTILITY_CMD")
    if not command:
        print("[wrapper] TOOLDEX_UTILITY_CMD was not provided.", file=sys.stderr)
        return 2

    hold_on_success = os.environ.get("TOOLDEX_UTILITY_HOLD", "0").lower() in {"1", "true", "yes"}
    log_path = os.environ.get("TOOLDEX_UTILITY_LOG")
    log_file = Path(log_path).expanduser() if log_path else None

    _log_message(log_file, f"Launching utility command: {command}")
    print(f"[wrapper] Launching utility command: {command}")
    try:
        proc = subprocess.Popen(command, shell=True)
        exit_code = proc.wait()
    except FileNotFoundError as exc:
        print(f"[wrapper] Failed to start utility: {exc}", file=sys.stderr)
        _log_message(log_file, f"Failed to start utility: {exc}")
        exit_code = 127
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[wrapper] Unexpected error running utility: {exc}", file=sys.stderr)
        _log_message(log_file, f"Unexpected error: {exc}")
        exit_code = 1

    print(f"[wrapper] Utility exited with status {exit_code}")
    _log_message(log_file, f"Utility exited with status {exit_code}")

    should_hold = exit_code != 0 or hold_on_success
    if should_hold:
        try:
            print("Press Enter to close the utility pane...")
            input()
        except EOFError:
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

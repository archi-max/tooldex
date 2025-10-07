#!/usr/bin/env python3
"""
Generic PTY wrapper for ANY main command, with a hotkey (and optional output marker)
that pops a utility tool in the TOP tmux pane. Includes a convenience integration
for gdb, but works with anything (lldb, bash, ipython, node, etc.).

Features
- True TTY passthrough via pty: readline/editing, Ctrl-C, resizing work as normal.
- Universal hotkey: Ctrl-] then a trigger key (default: 'u') opens the utility up top.
- Optional marker watch: if the main command prints a marker string, we launch too.
- gdb convenience: auto-inject a `tool` command that prints the marker (can disable).
- If not in tmux, the utility spawns in a separate shell so nothing breaks.

Examples
  # Run gdb (auto-injects the 'tool' gdb command unless disabled)
  python3 tool_wrapper.py -- --args ./a.out

  # Run bash as the main tool, press Ctrl-] then 'u' to open htop on demand
  python3 tool_wrapper.py -- bash -l

  # Any command (e.g., ipython) and a custom utility
  python3 tool_wrapper.py -u "btop" -- ipython

  # Disable gdb injection and disable marker watch; rely only on hotkey
  python3 tool_wrapper.py --no-gdb-inject --no-marker-watch -- gdb --args ./a.out

  # Trigger by output marker: print the marker in your tool (e.g., inside bash)
  #   echo "[[WRAPPER:TOOL]]"    # will pop the utility pane

While running
  • Hotkey:  Ctrl-]  then  <trigger key> (default 'u')
  • In gdb:  type  tool   (unless --no-gdb-inject)

Requirements
- Linux/macOS or WSL. Needs `tmux` for splits (otherwise launches utility in a new shell).
"""

import os
import sys
import pty
import tty
import termios
import select
import signal
import fcntl
import struct
import subprocess
import argparse
import shutil
import shlex

ESCAPE_KEY = b"\x1d"  # Ctrl-]
DEFAULT_UTILITY = os.environ.get("UTILITY_CMD", "htop")
DEFAULT_MARKER = os.environ.get("UTILITY_MARKER", "[[WRAPPER:TOOL]]")

def _applescript_escape(s: str) -> str:
    # AppleScript strings must be double-quoted; escape backslashes and quotes.
    return s.replace("\\", "\\\\").replace('"', '\\"')

def get_winsize(fd):
    try:
        s = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols, _, _ = struct.unpack('HHHH', s)
        return rows, cols
    except Exception:
        return 24, 80


def set_winsize(fd, rows, cols):
    try:
        s = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, s)
    except Exception:
        pass


def in_tmux():
    return bool(os.environ.get("TMUX") and os.environ.get("TMUX_PANE"))


def launch_utility_in_top_pane(cmd, pane=None):
    pane_id = pane or os.environ.get("TMUX_PANE")
    if in_tmux():
        try:
            # -v vertical split (top/bottom). -b puts the new pane ABOVE the current pane
            subprocess.check_call(["tmux", "split-window", "-v", "-b", "-t", pane_id, "--", "bash", "-lc", cmd])
            subprocess.call(["tmux", "select-layout", "-t", pane_id, "even-vertical"])
            os.write(1, b"\r\n[wrapper] Utility launched in top tmux pane.\r\n")
        except Exception as e:
            os.write(1, f"\r\n[wrapper] tmux split failed: {e}\r\n".encode())
        return

    # Not in tmux → try to launch a NEW terminal window/tab
    try:
        # macOS (Terminal.app / iTerm will open a new window/tab)
        if sys.platform == "darwin":
            # Run the user's command under bash -lc to get a proper shell env.
            payload = f'bash -lc "{_applescript_escape(cmd)}"'
            osa = f'tell application "Terminal" to do script "{_applescript_escape(payload)}"\nactivate'
            subprocess.Popen(["osascript", "-e", osa])
            os.write(1, b"\r\n[wrapper] Launched utility in a new macOS Terminal window/tab.\r\n")
            return

        # WSL → use Windows Terminal if available
        if "WSL_DISTRO_NAME" in os.environ:
            # Requires wt.exe on PATH
            subprocess.Popen([
                "powershell.exe", "-NoProfile", "-Command",
                "wt -w 0 nt bash -lc " + shlex.quote(cmd)
            ])
            os.write(1, b"\r\n[wrapper] Launched utility in a new Windows Terminal tab.\r\n")
            return

        # Linux with GUI (X11/Wayland) → try common terminal emulators
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            candidates = [
                ("kitty",              ["kitty", "-e", "bash", "-lc", cmd]),
                ("wezterm",            ["wezterm", "start", "bash", "-lc", cmd]),
                ("alacritty",          ["alacritty", "-e", "bash", "-lc", cmd]),
                ("gnome-terminal",     ["gnome-terminal", "--", "bash", "-lc", cmd]),
                ("kgx",                ["kgx", "--", "bash", "-lc", cmd]),  # GNOME Console
                ("konsole",            ["konsole", "-e", "bash", "-lc", cmd]),
                ("xfce4-terminal",     ["xfce4-terminal", "-e", f"bash -lc {shlex.quote(cmd)}"]),
                ("xterm",              ["xterm", "-e", f"bash -lc {shlex.quote(cmd)}"]),
                ("x-terminal-emulator",["x-terminal-emulator", "-e", "bash", "-lc", cmd]),
            ]
            for name, argv in candidates:
                if shutil.which(name):
                    subprocess.Popen(argv)
                    os.write(1, f"\r\n[wrapper] Launched utility in new {name} window.\r\n".encode())
                    return

        # Fallback: no GUI terminal → run detached so it doesn't steal the TTY
        subprocess.Popen(
            ["bash", "-lc", cmd],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        os.write(1, b"\r\n[wrapper] No GUI terminal found; launched utility detached (no TTY).\r\n")
    except Exception as e:
        os.write(1, f"\r\n[wrapper] Failed to launch utility separately: {e}\r\n".encode())

def is_gdb(cmd_and_args):
    return bool(cmd_and_args) and os.path.basename(cmd_and_args[0]).startswith("gdb")


def inject_gdb_tool_cmd(args_list, marker_str):
    """Return argv that defines a gdb command `tool` which prints marker_str when invoked."""
    injected = [
        "-ex", "define tool",
        "-ex", f"echo {marker_str}\\n",
        "-ex", "end",
    ]
    return ["gdb"] + injected + args_list


def parse_args():
    p = argparse.ArgumentParser(description="Generic PTY wrapper: run ANY command, trigger a top tmux utility via hotkey or marker.")
    p.add_argument("--utility", "-u", default=DEFAULT_UTILITY,
                   help="Command to run for the utility pane (default: env UTILITY_CMD or 'htop').")
    p.add_argument("--trigger-key", default="u",
                   help="Single character to press after Ctrl-] to trigger the utility (default: 'u').")
    p.add_argument("--marker", default=DEFAULT_MARKER,
                   help="Output marker string to watch for (default: env UTILITY_MARKER or '[[WRAPPER:TOOL]]').")
    p.add_argument("--no-marker-watch", action="store_true",
                   help="Disable watching child output for the marker.")
    p.add_argument("--no-gdb-inject", action="store_true",
                   help="If main command is gdb, do NOT inject a 'tool' command.")
    p.add_argument("cmd_and_args", nargs=argparse.REMAINDER,
                   help="Main command and args to run after '--', e.g. -- bash -l OR -- gdb --args ./a.out")
    args = p.parse_args()

    # Remainder normalization: drop leading '--' if present
    cmd = args.cmd_and_args
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        # Default to a login shell if no command supplied
        shell = os.environ.get("SHELL", "bash")
        cmd = [shell, "-l"] if shell.endswith("bash") else [shell]
    args.cmd_and_args = cmd
    return args


def main():
    args = parse_args()

    # Determine child argv, possibly with gdb injection
    if is_gdb(args.cmd_and_args) and not args.no_gdb_inject:
        child_argv = inject_gdb_tool_cmd(args.cmd_and_args[1:], args.marker)
        hotkey_hint = "Hotkey: Ctrl-] then '{}'  |  gdb cmd: 'tool'".format(args.trigger_key)
    else:
        child_argv = args.cmd_and_args
        hotkey_hint = "Hotkey: Ctrl-] then '{}'".format(args.trigger_key)

    # Spawn child in a PTY
    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvp(child_argv[0], child_argv)
        os._exit(1)

    stdin_fd = sys.stdin.fileno()
    old_tattr = termios.tcgetattr(stdin_fd)
    tty.setraw(stdin_fd)

    # Non-blocking master
    fl = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    # Propagate window size
    def on_winch(signum, frame):
        rows, cols = get_winsize(stdin_fd)
        set_winsize(master_fd, rows, cols)
        try:
            os.kill(pid, signal.SIGWINCH)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGWINCH, on_winch)
    on_winch(None, None)

    os.write(1, f"[wrapper] {hotkey_hint}  → opens utility in TOP pane.\r\n".encode())
    if in_tmux():
        os.write(1, b"[wrapper] Tip: you're in tmux; splits will appear here.\r\n")
    else:
        os.write(1, b"[wrapper] Not in tmux; will try to open the utility in a new terminal window.\r\n")

    escape_armed = False
    tkey = (args.trigger_key or "u")[0].encode().lower()
    marker_bytes = args.marker.encode()

    try:
        while True:
            r, _, _ = select.select([stdin_fd, master_fd], [], [])
            if stdin_fd in r:
                try:
                    data = os.read(stdin_fd, 1024)
                except OSError:
                    data = b""
                if not data:
                    try:
                        os.close(master_fd)
                    except Exception:
                        pass
                    break
                out = bytearray()
                for b in data:
                    ch = bytes([b])
                    if escape_armed:
                        escape_armed = False
                        if ch.lower() == tkey:
                            launch_utility_in_top_pane(args.utility)
                            continue
                        else:
                            # pass through the escape and the char since not a match
                            out += ESCAPE_KEY + ch
                            continue
                    if ch == ESCAPE_KEY:
                        escape_armed = True
                        continue
                    out += ch
                if out:
                    os.write(master_fd, bytes(out))

            if master_fd in r:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""
                if not data:
                    break
                os.write(1, data)
                if marker_bytes and not args.no_marker_watch and marker_bytes in data:
                    launch_utility_in_top_pane(args.utility)

    finally:
        try:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tattr)
        except Exception:
            pass
        try:
            os.waitpid(pid, 0)
        except Exception:
            pass


if __name__ == "__main__":
    main()

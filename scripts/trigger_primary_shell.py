#!/usr/bin/env python3
"""
Utility script to manually exercise the tooldex MCP shell tools.

Launch this inside the utility pane created by `tool_wrapper` once
`TOOLDEX_PRIMARY_PANE` is set. It directly calls the same coroutines exposed by
the MCP server so you can verify command injection and pane capture behaviour
without standing up a full MCP client.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, Dict

from tooldex.mcp import server as mcp_server


class ConsoleContext:
    """Minimal async context that mimics FastMCP logging hooks."""

    async def info(self, message: str) -> None:
        print(f"[info] {message}")

    async def warning(self, message: str) -> None:
        print(f"[warning] {message}", file=sys.stderr)

    async def debug(self, message: str) -> None:
        print(f"[debug] {message}")

    async def error(self, message: str) -> None:
        print(f"[error] {message}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exercise tooldex MCP shell helpers.")
    parser.add_argument(
        "command",
        nargs="?",
        help="Command string to send to the primary tmux pane.",
    )
    parser.add_argument(
        "--no-enter",
        action="store_true",
        help="Type the command without pressing Enter (handy for inspection).",
    )
    parser.add_argument(
        "--read",
        nargs="?",
        const=200,
        type=int,
        metavar="LINES",
        help="Capture the last LINES from the primary pane instead of typing a command (default 200).",
    )
    parser.add_argument(
        "--include-colors",
        action="store_true",
        help="Include ANSI colour codes when capturing pane output.",
    )
    parser.add_argument(
        "--subscribe",
        action="store_true",
        help="Create a pane subscription and optionally return initial lines.",
    )
    parser.add_argument(
        "--initial-lines",
        type=int,
        default=0,
        help="When subscribing, include this many recent lines immediately.",
    )
    parser.add_argument(
        "--fetch",
        metavar="TOKEN",
        help="Fetch incremental updates for the given subscription token.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Timeout in seconds when fetching subscription updates.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=200,
        help="Maximum lines to include in each fetch response.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.2,
        help="Polling interval when waiting for subscription updates.",
    )
    parser.add_argument(
        "--unsubscribe",
        metavar="TOKEN",
        help="Remove a primary pane subscription token.",
    )
    return parser.parse_args()


async def trigger(command: str, send_enter: bool) -> Dict[str, Any]:
    ctx = ConsoleContext()
    return await mcp_server.run_shell(
        command=command,
        ctx=ctx,  # type: ignore[arg-type]
        send_enter=send_enter,
    )


async def capture(lines: int, include_colors: bool) -> Dict[str, Any]:
    ctx = ConsoleContext()
    return await mcp_server.read_primary_pane(
        ctx=ctx,  # type: ignore[arg-type]
        lines=lines,
        include_colors=include_colors,
    )


async def subscribe(include_colors: bool, initial_lines: int) -> Dict[str, Any]:
    ctx = ConsoleContext()
    return await mcp_server.subscribe_primary_pane(
        ctx=ctx,  # type: ignore[arg-type]
        include_colors=include_colors,
        initial_lines=initial_lines,
    )


async def fetch(token: str, timeout: float, max_lines: int, poll_interval: float) -> Dict[str, Any]:
    ctx = ConsoleContext()
    return await mcp_server.fetch_primary_pane_updates(
        ctx=ctx,  # type: ignore[arg-type]
        token=token,
        timeout_seconds=timeout,
        max_lines=max_lines,
        poll_interval=poll_interval,
    )


def main() -> None:
    args = parse_args()
    if "TOOLDEX_PRIMARY_PANE" not in os.environ:
        pane_from_env = os.environ.get("TMUX_PANE")
        hint = f" Detected TMUX_PANE={pane_from_env}" if pane_from_env else ""
        raise SystemExit(
            "TOOLDEX_PRIMARY_PANE is not set. Run this inside the utility pane launched by tool_wrapper."
            + hint
        )

    operations = sum(
        int(bool(x))
        for x in [
            args.command,
            args.read is not None,
            args.subscribe,
            args.fetch,
            args.unsubscribe,
        ]
    )
    if operations != 1:
        raise SystemExit("Select exactly one operation: command, --read, --subscribe, --fetch, or --unsubscribe.")

    if args.read is not None:
        result = asyncio.run(capture(args.read, args.include_colors))
        print("read_primary_pane returned:")
    elif args.subscribe:
        result = asyncio.run(subscribe(args.include_colors, args.initial_lines))
        print("subscribe_primary_pane returned:")
    elif args.fetch:
        result = asyncio.run(
            fetch(args.fetch, args.timeout, args.max_lines, args.poll_interval)
        )
        print("fetch_primary_pane_updates returned:")
    elif args.unsubscribe:
        success = mcp_server.unsubscribe_primary_pane(args.unsubscribe)
        print("unsubscribe_primary_pane returned:")
        print(f"  success: {success}")
        return
    else:
        result = asyncio.run(trigger(args.command, not args.no_enter))
        print("run_shell returned:")

    for key, value in result.items():
        if key == "content" and isinstance(value, list):
            print("  content:")
            for line in value:
                print(f"    {line}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

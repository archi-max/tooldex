from __future__ import annotations

import argparse
import sys
from typing import Sequence

from tooldex.cli import execute_codex
from tooldex.core.config import ConfigError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tooldex", description="ToolDex command-line interface.")
    subparsers = parser.add_subparsers(dest="command")

    codex_parser = subparsers.add_parser(
        "codex",
        help="Execute the Codex agent CLI using ToolDex configuration.",
    )
    codex_parser.add_argument(
        "-c",
        "--config",
        dest="config",
        help="Path to a Codex config file. Defaults to tool or user configuration if omitted.",
    )
    codex_parser.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to the Codex binary. Use '--' to separate them from ToolDex options.",
    )
    codex_parser.set_defaults(handler=_handle_codex)

    return parser


def _handle_codex(args: argparse.Namespace) -> int:
    return execute_codex(args.config, args.codex_args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    parsed_args = parser.parse_args(argv)

    handler = getattr(parsed_args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        return handler(parsed_args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

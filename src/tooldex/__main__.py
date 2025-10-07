from __future__ import annotations

import argparse
import sys
from typing import Sequence

from tooldex.cli import execute_codex, init_codex_config
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
    codex_parser.set_defaults(handler=_handle_codex_run, codex_args=[], codex_command=None)

    codex_subparsers = codex_parser.add_subparsers(dest="codex_command")

    init_parser = codex_subparsers.add_parser(
        "init-config",
        help="Copy the bundled Codex config to a writable location for customization.",
    )
    init_parser.add_argument(
        "-p",
        "--path",
        dest="path",
        help="Destination for the generated config (default: ~/.tooldex/codex.toml).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination if it already exists.",
    )
    init_parser.set_defaults(handler=_handle_codex_init)

    return parser


def _handle_codex_run(args: argparse.Namespace) -> int:
    return execute_codex(args.config, args.codex_args)


def _handle_codex_init(args: argparse.Namespace) -> int:
    destination = init_codex_config(args.path, args.force)
    print(f"Wrote Codex config to {destination}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    parsed_args, extras = parser.parse_known_args(argv)

    if getattr(parsed_args, "command", None) == "codex" and getattr(parsed_args, "codex_command", None) is None:
        parsed_args.codex_args = extras
        extras = []

    if extras:
        parser.error(f"unrecognized arguments: {' '.join(extras)}")

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

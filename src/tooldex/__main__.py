from __future__ import annotations

import argparse
import sys
from typing import Sequence

from tooldex.cli import execute_codex, init_codex_config
from tooldex.core.config import ConfigError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tooldex", 
        description="ToolDex command-line interface.",
        epilog="Common commands:\n"
               "  tooldex codex              # Run Codex agent with ToolDex configuration\n"
               "  tooldex codex init-config  # Initialize a custom configuration file\n"
               "  tooldex init               # Shortcut for 'tooldex codex init-config'\n"
               "\n"
               "For detailed help on any command:\n"
               "  tooldex <command> -h       # e.g., 'tooldex codex -h'\n"
               "  tooldex codex init-config -h  # Help for config initialization",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    parser.add_argument(
        "-C",
        "--config",
        dest="global_config",
        help="Path to a Codex config file applied to commands that support it.",
    )

    # Add 'init' as a top-level shortcut command for easier discovery
    init_shortcut_parser = subparsers.add_parser(
        "init",
        help="Initialize a custom Codex configuration file (shortcut for 'codex init-config').",
        description="Initialize a custom Codex configuration file for modification.\n"
                    "This is a shortcut for 'tooldex codex init-config'.\n\n"
                    "The configuration file allows you to customize:\n"
                    "  • MCP server configurations\n"
                    "  • Approval policies\n"
                    "  • Environment variables\n"
                    "  • Binary paths and arguments\n\n"
                    "Default location: ~/.tooldex/codex.toml\n\n"
                    "Example usage:\n"
                    "  tooldex init                      # Create config at default location\n"
                    "  tooldex init -p ./my-config.toml  # Create at custom location\n"
                    "  tooldex init --force              # Overwrite existing config",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    init_shortcut_parser.add_argument(
        "-p",
        "--path",
        dest="path",
        help="Custom destination path for the config file (default: ~/.tooldex/codex.toml).",
    )
    init_shortcut_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination file if it already exists.",
    )
    init_shortcut_parser.set_defaults(handler=_handle_codex_init)

    codex_parser = subparsers.add_parser(
        "codex",
        help="Execute the Codex agent CLI or manage its configuration.",
        description="Execute the Codex agent CLI with ToolDex configuration.\n\n"
                    "Configuration Search Order:\n"
                    "  1. Explicit path (--config flag)\n"
                    "  2. TOOLDEX_CODEX_CONFIG environment variable\n"
                    "  3. ./.tooldex/codex.toml (current directory)\n"
                    "  4. $TOOLDEX_CONFIG_DIR/codex.toml\n"
                    "  5. $XDG_CONFIG_HOME/tooldex/codex.toml or ~/.config/tooldex/codex.toml\n"
                    "  6. ~/.tooldex/codex.toml\n"
                    "  7. Built-in default configuration\n\n"
                    "Use 'tooldex codex init-config' to create a custom configuration file.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    codex_parser.add_argument(
        "-c",
        "--config",
        dest="config",
        help="Path to a Codex config file. Defaults to tool or user configuration if omitted.",
    )
    codex_parser.set_defaults(handler=_handle_codex_run, codex_args=[], codex_command=None)

    codex_subparsers = codex_parser.add_subparsers(
        dest="codex_command",
        help="Codex subcommands (use 'tooldex codex <subcommand> -h' for help)"
    )

    init_parser = codex_subparsers.add_parser(
        "init-config",
        help="Initialize a custom Codex configuration file.",
        description="Copy the bundled Codex configuration template to a user-writable location.\n"
                    "This allows you to customize ToolDex settings, MCP server configurations,\n"
                    "environment variables, and other options.\n\n"
                    "Default location: ~/.tooldex/codex.toml\n\n"
                    "Example usage:\n"
                    "  tooldex codex init-config                      # Create config at default location\n"
                    "  tooldex codex init-config -p ./my-config.toml  # Create at custom location\n"
                    "  tooldex codex init-config --force              # Overwrite existing config\n\n"
                    "Shortcut: You can also use 'tooldex init' instead of 'tooldex codex init-config'",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    init_parser.add_argument(
        "-p",
        "--path",
        dest="path",
        help="Custom destination path for the config file (default: ~/.tooldex/codex.toml).",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination file if it already exists.",
    )
    init_parser.set_defaults(handler=_handle_codex_init)

    return parser


def _handle_codex_run(args: argparse.Namespace) -> int:
    config_path = getattr(args, "config", None)
    if config_path is None:
        config_path = getattr(args, "global_config", None)
    return execute_codex(config_path, args.codex_args)


def _handle_codex_init(args: argparse.Namespace) -> int:
    destination = init_codex_config(args.path, args.force)
    print(f"✓ Successfully created Codex configuration at: {destination}")
    print(f"\nYou can now customize this configuration file to:")
    print("  • Set custom MCP server configurations")
    print("  • Adjust approval policies")
    print("  • Configure environment variables")
    print("  • Modify binary paths and arguments")
    print(f"\nTo use this config, run: tooldex codex --config {destination}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arg_list = list(argv) if argv is not None else sys.argv[1:]

    passthrough: list[str] = []
    if "--" in arg_list:
        sentinel_index = arg_list.index("--")
        passthrough = arg_list[sentinel_index + 1 :]
        arg_list = arg_list[:sentinel_index]

    parser = _build_parser()
    parsed_args, extras = parser.parse_known_args(arg_list)
    extras.extend(passthrough)

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

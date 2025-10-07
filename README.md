# tooldex

tooldex is a terminal-first pair-programming companion that stays out of your way until you need it. Instead of replacing your shell, it listens for a hotkey, freezes the active tmux pane, and hands control to a purpose-built AI agent that can inspect context via MCP and suggest the next command, debug step, or explanation. When the exchange finishes, control snaps straight back to your running session—no reflowed buffers or confusing hand-offs.

## Key Ideas
- **Bring-your-own CLI**: Run your usual tools (gdb, git, nvims) while tooldex augments them with targeted agent prompts.
- **Ephemeral assistance**: AI agents activate only on demand, perform a scoped action, and then relinquish control.
- **tmux-native UX**: A secondary pane streams agent output while your main pane is temporarily locked, keeping history intact.
- **MCP integration**: Agents interface with the terminal via the Model Context Protocol, allowing precise read/write access without full autonomy.

## Getting Started
1. `uv sync --group dev` – install runtime and development dependencies into `.venv`.
2. `uv run tooldex` – launch the CLI scaffold. (Upcoming: interactive session manager.)
3. Ensure `tmux` is installed and running; tooldex will hook into the active session.

## Usage Flow
1. Start tooldex inside an existing tmux session (`tmux attach` or `tmux new -s work`).
2. Press the configured hotkey (defaults forthcoming) to trigger agent mode.
3. Watch the right-hand pane for conversation, confirm or edit the proposed command, then let the agent apply it through MCP.
4. Exit agent mode to resume your normal terminal buffer untouched.

## Architecture Snapshot
- `src/tooldex/agents/` – agent definitions and orchestration.
- `src/tooldex/core/` – session management, MCP bridges, prompt templates.
- `src/tooldex/tmux/` – tmux control helpers and key-binding utilities.
- `tests/` – pytest suite mirroring the source layout.

## Roadmap
1. Implement tmux pane manager and keybinding configuration.
2. Connect MCP command execution layer with auditing safeguards.
3. Add specialized agents for debugging (`gdb`), repo hygiene (`git`), and environment setup.
4. Ship a minimal prompt library and long-running session state cache.

## Contributing
See `AGENTS.md` for repository standards, commit conventions, and security guidance. We welcome targeted improvements—from new agent scripts to better tmux workflows—that respect the “assist, don’t replace” philosophy.

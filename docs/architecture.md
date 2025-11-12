# Tooldex Architecture Overview

Tooldex is a modular system that connects an AI agent (Codex) with your terminal through the Model Context Protocol (MCP). This document explains how the components work together.

## Components

### 1. **tooldex** (Main CLI)
The main command-line interface that:
- Manages configuration files
- Launches the Codex AI agent with proper settings
- Injects environment variables for tmux pane control
- Provides configuration initialization tools

**Command**: `tooldex`

### 2. **tooldex-mcp** (MCP Server)
A Model Context Protocol server that:
- Provides tools for the AI to interact with tmux panes
- Runs as a subprocess launched by Codex
- Exposes shell control functions to the AI agent
- Maintains connection to your active tmux session

**Command**: `tooldex-mcp` (launched automatically by Codex)

### 3. **Codex** (AI Agent)
An external AI agent that:
- Receives configuration from tooldex
- Starts the MCP server (tooldex-mcp) as defined in config
- Uses MCP tools to read and control your terminal
- Provides the AI-powered assistance interface

**Command**: `codex` (launched by tooldex)

## How They Connect

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   User       │────>│   tooldex    │────>│    Codex     │
│              │     │    (CLI)     │     │  (AI Agent)  │
└──────────────┘     └──────────────┘     └──────────────┘
                             │                      │
                             │                      │ Launches
                     Passes config                  ▼
                     & environment          ┌──────────────┐
                                           │ tooldex-mcp   │
                                           │ (MCP Server)  │
                                           └──────────────┘
                                                    │
                                                    │ Controls
                                                    ▼
                                           ┌──────────────┐
                                           │  tmux pane   │
                                           └──────────────┘
```

### Connection Flow

1. **User runs `tooldex codex`**
   - Tooldex reads configuration from `codex.toml`
   - Locates the Codex binary specified in config
   - Sets up environment variables including `TOOLDEX_PRIMARY_PANE`

2. **Tooldex launches Codex**
   - Passes configuration overrides via `--config` flags
   - Includes MCP server configuration for `tooldex-shell`
   - Provides environment variables for tmux integration

3. **Codex starts the MCP server**
   - Reads the `[codex.mcp_servers.tooldex-shell]` configuration
   - Executes `tooldex-mcp` command as a subprocess
   - Establishes MCP protocol communication

4. **MCP server connects to tmux**
   - Uses `TOOLDEX_PRIMARY_PANE` to identify your active pane
   - Provides tools: `run_shell`, `read_primary_pane`, etc.
   - Enables AI to read and control your terminal

## Configuration Structure

The `codex.toml` file ties everything together:

```toml
[tooldex]
binary = "codex"                    # Path to Codex AI agent
terminal_mcp = "tooldex-shell"      # MCP server name for tmux control

[codex]
approval_policy = "on-request"      # AI action approval settings

[codex.mcp_servers.tooldex-shell]
command = "tooldex-mcp"             # MCP server executable
args = []                            # Additional arguments
env.TOOLDEX_PRIMARY_PANE = "..."    # Injected at runtime
```

## MCP Server Tools

The `tooldex-mcp` server provides these tools to the AI:

### Shell Control
- **`run_shell`**: Send commands to your tmux pane
- **`read_primary_pane`**: Capture recent terminal output
- **`subscribe_primary_pane`**: Track incremental updates
- **`fetch_primary_pane_updates`**: Get new output since last check
- **`unsubscribe_primary_pane`**: Stop tracking updates

### Resource Access
- **`doc://tooldex/shell-guide`**: Agent documentation for using the tools

## Environment Variables

Key environment variables used by the system:

- **`TOOLDEX_PRIMARY_PANE`**: Identifies your active tmux pane
- **`TMUX_PANE`**: Fallback for pane identification
- **`TOOLDEX_CODEX_CONFIG`**: Override config file location
- **`TOOLDEX_CONFIG_DIR`**: Custom config directory
- **`XDG_CONFIG_HOME`**: Standard config location

## Configuration Search Order

When looking for `codex.toml`, tooldex searches:

1. Explicit path (`--config` flag)
2. `TOOLDEX_CODEX_CONFIG` environment variable
3. `./.tooldex/codex.toml` (current directory)
4. `$TOOLDEX_CONFIG_DIR/codex.toml`
5. `$XDG_CONFIG_HOME/tooldex/codex.toml` or `~/.config/tooldex/codex.toml`
6. `~/.tooldex/codex.toml` (default user location)
7. Built-in default configuration

## Security Considerations

- The AI agent only has access to tmux panes explicitly configured
- Commands require approval based on `approval_policy` setting
- MCP server runs with your user permissions
- Terminal history remains intact after AI interaction

## Getting Started

1. **Initialize configuration**:
   ```bash
   tooldex init  # or: tooldex codex init-config
   ```

2. **Customize settings** in `~/.tooldex/codex.toml`

3. **Run in tmux session**:
   ```bash
   tmux new -s work
   tooldex codex
   ```

4. The AI agent will connect to your tmux pane and be ready to assist!

## Troubleshooting

### "Primary tmux pane is unknown"
- Ensure you're running inside a tmux session
- Check that `TMUX_PANE` environment variable is set
- Verify tmux is installed and accessible

### MCP server connection fails
- Check that `tooldex-mcp` is installed (part of tooldex package)
- Verify the `command` in config points to correct executable
- Review startup timeout settings in configuration

### Configuration not found
- Run `tooldex init` to create default configuration
- Check file exists at `~/.tooldex/codex.toml`
- Use `--config` flag to specify custom location

## Related Documentation

- [MCP Server Guide](mcp/tooldex-shell-agent-guide.md) - Detailed MCP server documentation
- [Codex Integration](integrations/codex.md) - Codex-specific configuration
- [Local Planning](local-planning.md) - Development planning notes

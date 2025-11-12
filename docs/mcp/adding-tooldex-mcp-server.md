# Adding the Tooldex MCP Server

This guide explains how to configure the `tooldex-shell` MCP server for use with various MCP clients like Claude Desktop, Cline, and other tools that support the Model Context Protocol.

## Overview

The **tooldex-shell** MCP server provides AI agents with direct access to your terminal through tmux, enabling them to:
- Execute commands in your active shell
- Read terminal output
- Stream command output in real-time
- Maintain shell session state

## Prerequisites

1. **Install tooldex:**
   ```bash
   uv sync --group dev
   ```
   This makes the `tooldex-mcp` command available.

2. **Ensure tmux is running:**
   The MCP server requires an active tmux session to function.

## Configuration for Different MCP Clients

### Claude Desktop

Edit your Claude Desktop configuration file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

Add the following to the `mcpServers` section:

```json
{
  "mcpServers": {
    "tooldex-shell": {
      "command": "tooldex-mcp",
      "args": []
    }
  }
}
```

**If using uv to run tooldex:**

```json
{
  "mcpServers": {
    "tooldex-shell": {
      "command": "uv",
      "args": ["run", "tooldex-mcp"]
    }
  }
}
```

### Cline (VSCode Extension)

In Cline's MCP settings, add a new server:

**Server Name:** `tooldex-shell`

**Command:** `tooldex-mcp`

**Args:** (leave empty)

Or in JSON format:
```json
{
  "tooldex-shell": {
    "command": "tooldex-mcp",
    "args": []
  }
}
```

### Other MCP Clients

For any MCP-compatible client, use this configuration pattern:

```json
{
  "command": "tooldex-mcp",
  "args": []
}
```

## Environment Variables

### TOOLDEX_PRIMARY_PANE

**Important:** This environment variable controls which tmux pane the MCP server will interact with.

**When to set it:**
- ✅ **Set it** if you are launching the MCP server from within a specific tmux pane that you want the AI to control
- ✅ Use the tmux pane ID format (e.g., `%1`, `%2`, etc.)

**When NOT to set it:**
- ❌ **Leave it empty** when launching from outside tmux
- ❌ **Leave it empty** to let tooldex automatically detect the primary pane when launched inside a tmux terminal

**Auto-detection behavior:**
When `TOOLDEX_PRIMARY_PANE` is not set and the MCP server is launched from within tmux, it will automatically detect and use the current pane as the primary pane.

### Example Configurations

**Option 1: Auto-detect (recommended for most users)**
```json
{
  "mcpServers": {
    "tooldex-shell": {
      "command": "tooldex-mcp",
      "args": []
    }
  }
}
```

**Option 2: Specific pane (advanced)**
```json
{
  "mcpServers": {
    "tooldex-shell": {
      "command": "tooldex-mcp",
      "args": [],
      "env": {
        "TOOLDEX_PRIMARY_PANE": "%1",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

## Verifying the Installation

After adding the configuration:

1. **Restart your MCP client** (Claude Desktop, VSCode with Cline, etc.)

2. **Check available tools** - The following tools should be available:
   - `run_shell` - Execute commands in the terminal
   - `read_primary_pane` - Capture terminal output
   - `subscribe_primary_pane` - Create streaming subscription
   - `fetch_primary_pane_updates` - Poll for new output
   - `unsubscribe_primary_pane` - Clean up subscription

3. **Test basic functionality:**
   Ask the AI to run a simple command like:
   ```
   Can you run 'echo hello' in my terminal?
   ```

## Troubleshooting

### "MCP server not found" error
- Verify `tooldex-mcp` is in your PATH: `which tooldex-mcp`
- If using `uv`, ensure the project is synced: `uv sync --group dev`
- Try using the full path to `tooldex-mcp` in your configuration

### "Cannot connect to tmux" error
- Ensure tmux is running: `tmux ls`
- Start a new tmux session: `tmux new -s work`
- Verify the `TOOLDEX_PRIMARY_PANE` value matches an active pane (if set)

### Commands not executing
- Check that the pane ID in `TOOLDEX_PRIMARY_PANE` is correct (if set)
- Verify the pane is still active: `tmux list-panes -a`
- Try removing `TOOLDEX_PRIMARY_PANE` to use auto-detection

### "Permission denied" errors
- The MCP server runs with your user permissions
- Ensure your user has permission to execute the requested commands
- Check that tmux socket has correct permissions

## Advanced Configuration

### Timeouts

For Codex integration, you can customize timeouts in your `codex.toml`:

```toml
[codex.mcp_servers.tooldex-shell]
command = "tooldex-mcp"
args = []
startup_timeout_sec = 20
tool_timeout_sec = 60
```

### Multiple Panes

To control multiple tmux panes, you would need to run separate MCP server instances with different `TOOLDEX_PRIMARY_PANE` values and different server names:

```json
{
  "mcpServers": {
    "tooldex-shell-pane1": {
      "command": "tooldex-mcp",
      "env": {
        "TOOLDEX_PRIMARY_PANE": "%1"
      }
    },
    "tooldex-shell-pane2": {
      "command": "tooldex-mcp",
      "env": {
        "TOOLDEX_PRIMARY_PANE": "%2"
      }
    }
  }
}
```

## Security Considerations

- The MCP server runs with **your user privileges** and has **full access to your terminal**
- Commands are executed directly in your shell session
- Always review commands before allowing the AI to execute them
- Consider using approval policies in your MCP client to review dangerous operations
- The server respects your shell's security settings and permissions

## Further Reading

- [Tooldex Shell Agent Guide](tooldex-shell-agent-guide.md) - Complete reference for available tools
- [Codex Integration](../integrations/codex.md) - Codex-specific configuration details
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/docs) - Official MCP specification

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the configuration examples
3. Verify tmux is running and accessible
4. Check the MCP client logs for error details
5. Open an issue on the tooldex GitHub repository

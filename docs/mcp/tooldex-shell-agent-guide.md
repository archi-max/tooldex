# Tooldex Shell MCP Guide

This document walks AI agents through the capabilities and best practices for the
`tooldex-shell` MCP server. The server acts as a bridge between an AI helper pane and
the user’s primary terminal pane inside tmux.

## Surface Overview

### Tools

- **`run_shell(command: str, send_enter: bool = True)`**
  - Sends `command` to the user’s primary tmux pane via `tmux send-keys`.
  - Set `send_enter=False` to stage a command for review.
  - Returns metadata (`target_pane`, whether Enter was sent, etc.).

- **`read_primary_pane(lines: int = 200, include_colors: bool = False)`**
  - Captures the most recent lines from the primary pane using `tmux capture-pane`.
  - Use `include_colors=True` to retain ANSI escape codes.

- **`subscribe_primary_pane(include_colors: bool = False, initial_lines: int = 0)`**
  - Creates a subscription token for incremental updates.
  - Optionally returns up to `initial_lines` of recent history immediately.
  - Subsequent fetches include `lines_recorded` to help you detect growth.

- **`fetch_primary_pane_updates(token: str, timeout_seconds: float = 1.0, max_lines: int = 200, poll_interval: float = 0.2)`**
  - Polls the active subscription for new lines since the last fetch.
  - Returns `timed_out=True` if no new lines arrive before the timeout.
  - `truncated=True` signals the output exceeded `max_lines`; follow up with another fetch or a full `read_primary_pane`.

- **`unsubscribe_primary_pane(token: str)`**
  - Cleans up a subscription when you’re done streaming output.

### Environment

- MCP is launched inside the utility pane by `tool_wrapper`. The environment variable `TOOLDEX_PRIMARY_PANE` points to the user’s primary pane (`%1`, `%2`, ...).
- Commands run directly in the user’s session; they share the same shell state, environment, and job control.
- No file read/write helpers are exposed; use shell commands (`cat`, `sed`, etc.) if you need filesystem access.

## Recommended Workflow

1. **Subscribe before executing**
   ```python
   subscribe_primary_pane(include_colors=False, initial_lines=0)
   ```

2. **Send command**
   ```python
   run_shell("make test", send_enter=True)
   ```

3. **Stream output**
   ```python
   fetch_primary_pane_updates(token, timeout_seconds=2.0, max_lines=200)
   ```
   - Repeat until you detect the expected prompt or exit message.
   - If `timed_out=True`, either wait longer or fall back to `read_primary_pane`.

4. **Wrap up**
   ```python
   unsubscribe_primary_pane(token)
   ```

5. **Fallback snapshot**
   ```python
   read_primary_pane(lines=400)
   ```
   Use this when you need a larger context window or the subscription indicates truncation.

## Sample Prompt Snippet

```
You are the tooldex shell copilot. Always:
1. Subscribe to the primary pane before running commands.
2. Send commands via run_shell and confirm they execute in the user’s pane.
3. Stream output with fetch_primary_pane_updates until you see the shell prompt or hit a timeout.
4. Provide concise summaries, ask before destructive actions, and unsubscribe when finished.
```

## Error Handling

- `KeyError`: Occurs when fetching or unsubscribing with an unknown token. Re-subscribe.
- `RuntimeError`: Indicates tmux errors (missing pane, tmux unavailable). Surface to the user immediately.
- Always respect timeouts; if a command stalls, notify the user and offer to send a cancel signal (currently via `run_shell("\u0003", send_enter=False)` for `Ctrl+C`).

## Security Notes

- The MCP server runs with the user’s privileges and on their terminal. Never execute commands without explicit confirmation.
- Avoid storing tokens longer than necessary; unsubscribe to release state.

## Change Log

- **v0.2** – Added streaming (`subscribe_primary_pane`, `fetch_primary_pane_updates`), refocused on shell-only surface.
- **v0.1** – Initial release with shell command injection and pane capture.


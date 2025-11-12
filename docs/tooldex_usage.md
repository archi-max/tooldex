# Tooldex Usage Guide

A concise, hands-on introduction to getting productive with **Tooldex**—a tmux-native AI copilot that lets you drive *any* CLI tool through a Model Context Protocol (MCP) layer, **without** having to spin up one MCP server per tool.

---

## 1  Why Tooldex?

| Traditional Pattern | Tooldex Approach |
|---------------------|------------------|
| Build a dedicated MCP server for each CLI (e.g. *git-server*, *pytest-server*). | **One universal shell bridge.** Tooldex injects an AI agent into your existing tmux session and mediates all commands through a single shell-level MCP surface. |
| Each server must track its own state and lifecycle. | Session state is the *user’s shell itself*—Tooldex simply reads/writes that state. |
| Complex to orchestrate when you need a pipeline of heterogeneous tools. | You already orchestrate pipelines at the shell prompt; Tooldex just assists, then steps aside. |

**Key takeaway:** *If it runs in a terminal, Tooldex can drive it*. No extra server code required.

---

## 2  Installation & Quick Start

```bash
# 1. Create virtualenv & install dev + runtime deps
uv sync --group dev

# 2. Launch the Tooldex CLI scaffold
uv run tooldex                # upcoming: interactive session manager
```

Prerequisites:

* `tmux ≥ 3.2`
* Python 3.11+
* A running tmux session (`tmux new -s work` or `tmux attach`)

---

## 3  Anatomy of a Tooldex Session

```
┌──────────────────────────┐
│        tmux pane %1      │◄─── Your primary shell (bash, zsh…)
│ $ _                      │
├──────────────────────────┤
│    Tooldex agent pane    │◄─── Temporary, auto-created
│  (conversation + logs)   │
└──────────────────────────┘
```

1. **Trigger**: Hit the Tooldex hotkey (configurable; default TBD).
2. **Freeze & Fork**: The current pane (`$TOOLDEX_PRIMARY_PANE`) is locked. A new pane appears on the right.
3. **Conversational Loop**:  
   * Agent subscribes to the primary pane (`subscribe_primary_pane`).  
   * Presents you with suggestions or explanations.  
   * On approval, executes commands via `run_shell(...)`.  
4. **Resume**: Agent exits; panes merge; your shell prompt re-enables—history intact.

---

## 4  Using MCP via Tooldex

Tooldex exposes a **Shell MCP** with a minimal, powerful API (see `docs/mcp/tooldex-shell-agent-guide.md`):

* `run_shell(cmd, send_enter=True)` – inject/execute any shell command.
* `read_primary_pane(lines=200)` – capture recent output.
* `subscribe_primary_pane()` / `fetch_primary_pane_updates()` – stream live output.
* `unsubscribe_primary_pane()` – clean up.

Because these functions operate ***on the shell itself***:

* No per-tool wrappers are needed; the shell already multiplexes every command.
* Agents can drive `git`, `pytest`, `cargo`, `docker`… anything available in `$PATH`.

---

## 5  Harnessing tmux for Persistence

Why Tooldex chose **tmux** as its execution layer:

1. **Persistent Sessions** – Disconnect, close your laptop, reconnect later: your panes (and thus Tooldex’s context) survive.
2. **Pane Isolation** – The agent operates in its own pane, never polluting your main shell display.
3. **Native Multiplexing** – Multiple Tooldex instances can coexist, each targeting a different primary pane (useful for mono-repos or prod vs. staging panes).
4. **Rich Control Surface** – `tmux send-keys`, `capture-pane`, scrollback, and key-bindings give Tooldex precise yet safe control without root privileges.
5. **Portable** – tmux is ubiquitous on macOS, Linux, and remote servers.

---

## 6  Running Multiple Concurrent Tooldex Agents

Because each activation uses:

* A **unique agent pane** and
* The `TOOLDEX_PRIMARY_PANE` env var to locate its target,

you can:

1. Open several panes (e.g. `tmux split-window`).
2. Trigger Tooldex in each pane independently.
3. Each agent maintains its own MCP subscription token & stream.
4. They **do not** interfere; all share the same Python virtualenv but run separate agent processes.

Pro tip: name your panes (`tmux rename-pane`) so Tooldex agents can surface friendlier identifiers in summaries.

---

## 7  Best Practices

* **Stage before firing** – Pass `send_enter=False` to `run_shell` when you want a human-in-the-loop review.
* **Stream logs for long-running tasks** – Use `subscribe_primary_pane` + `fetch_primary_pane_updates` for *make* or *pytest -vv* runs.
* **Graceful aborts** – Send `\u0003` (Ctrl-C) via `run_shell("\u0003", send_enter=False)` then `run_shell("", send_enter=True)` if a command stalls.
* **Limit scrollback** – Capture only necessary lines to keep agent context efficient.

---

## 8  FAQ

**Q: Can Tooldex replace my existing AI coding plugin?**  
A: Tooldex focuses on *terminal workflows*. It complements editors; it doesn’t replace them.

**Q: Does it work outside tmux?**  
A: Not yet. tmux is essential for non-intrusive pane management and persistence.

**Q: How do I customise the activation hotkey?**  
A: Edit `~/.config/tooldex/config.toml` (upcoming) or pass `--hotkey` to `tooldex`.

**Q: What about security?**  
A: Agents only execute commands you explicitly approve. They run with your user permissions—no hidden privilege escalation.

---

## 9  Further Reading

* `README.md` – High-level philosophy & roadmap  
* `docs/mcp/tooldex-shell-agent-guide.md` – Full Shell MCP reference  
* `docs/architecture.md` – Deep dive into internal modules  
* `AGENTS.md` – Contributing new agents  

---

### Happy Hacking!

Tooldex aims to keep your hands on the keyboard, your eyes on the terminal, and your AI partner exactly where you want it: *right beside you, not in your way*.

# Repository Guidelines

## Project Structure & Module Organization
Keep runtime code inside `src/` with one folder per capability or integration, and reserve `agents/` for concrete agent implementations. Shared utilities stay under `src/core`, while configuration defaults belong in `configs/`. Tests mirror the source tree in `tests/`, and long-form documentation sits in `docs/`. A typical addition should look like:
```text
src/
  agents/
    your_agent/
      __init__.py
      planner.py
  core/
    routing.py
tests/
  agents/
    test_your_agent.py
docs/
  your-agent.md
scripts/
  sync_tools.sh
```
Each agent folder must expose a `registry.py` (or `registry.ts` if TypeScript code is introduced) so new components can be auto-discovered.

## Build, Test, and Development Commands
- `uv sync` – install Python dependencies specified in `pyproject.toml`.
- `uv run python -m tooldex.cli --help` – verify the main entry point still boots.
- `uv run pytest` – execute the full test suite; always ensure it passes before pushing.
- `uv run ruff check src tests` – enforce linting, import hygiene, and quick static checks.
- `uv run ruff format src tests` – auto-format code; run after structural edits.

## Coding Style & Naming Conventions
Use Python 3.11+ type hints, 4-space indentation, and `snake_case` for functions, `PascalCase` for classes, and uppercase for module-level constants. Public agent IDs follow the pattern `agent_<purpose>_<provider>` (for example `agent_research_bing`). Keep modules small (<300 lines) and add docstrings for planner entry points explaining the expected input payload.

## Testing Guidelines
Author pytest modules that mirror the package path; name test files `test_<module>.py` and individual tests `test_<behavior>`. Favor fixture-based setup over global state. Add regression tests for every bug fix and maintain >85% coverage for new code; use `--cov=src --cov-report=term-missing` locally to confirm.

## Commit & Pull Request Guidelines
Follow Conventional Commits (`feat:`, `fix:`, `chore:`, etc.) so downstream release tooling can infer semantic version bumps. Group related changes into a single commit and provide concise bodies describing context and follow-up ideas. Pull requests must include: a one-paragraph summary, testing evidence (command output or checklist), linked issues in closing syntax, and screenshots or logs for UI-facing or interactive flows.

## Security & Configuration Tips
Never commit secrets; store credentials in `.env.local` and reference them via `os.getenv`. When introducing new external tools, document required scopes in `docs/integrations/<tool>.md` and add a redacted `.env.example`. Rotate API keys after demos or public sharing.

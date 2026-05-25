# AGENTS.md

**Author**: Byron Williams <byron@williamscpa.com>

This file is the entry point for AI coding agents (Codex, Devin, and similar
tools) working in this repository.

## Start here

Read `CLAUDE.md` at the project root before doing any work. It contains all
project-specific conventions: architecture, code patterns, command reference,
CI gates, and exception hierarchy.

Global standards (RAD tagging, git workflow, security policy, package
selection, supervisor patterns) live in `~/.claude/CLAUDE.md` and are
inherited by this project.

## Key conventions

- Package manager: UV (not pip or Poetry)
- Linter/formatter: Ruff (88 chars)
- Type checker: BasedPyright strict mode
- Backend: FastAPI + SQLAlchemy 2.0 async
- Frontend: HTMX 2 + Jinja2 + Tailwind CSS (standalone CLI, no Node)
- Tests must pass at 80% line coverage before any commit is merged

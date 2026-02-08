# AGENTS.md

Guidance for coding agents and contributors in this repository.

## Purpose

This repository is a **template** for modern Python packages using:

- `uv` for environments and dependencies
- `prek` for hook orchestration
- `ruff` for linting/formatting
- `ty` for type checking
- `pytest` + `pytest-asyncio` for tests
- `loq` for file line limits

## Common commands

```bash
uv sync --group dev
uv run prek run --all-files
uv run pytest
uv build
```

## Quality checks

Use `prek` as the source of truth for static checks. It runs:

- `ruff-check`
- `ruff-format`
- `loq check`
- `ty check`

## Versioning and releases

Versioning is dynamic via `hatch-vcs` from Git tags.

- Create and push a tag like `0.1.0`
- Publish workflow builds and publishes from tag pushes

Tag format should be `MAJOR.MINOR.PATCH` (no `v` prefix).

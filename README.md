# py-template

A personal Python project template using:

- `uv` for dependency/env management
- `ruff` for linting + formatting
- `ty` for type checking
- `prek` for pre-commit-style hooks
- `loq` for file line-limit enforcement (`loq.toml`)
- `pytest` + `pytest-asyncio` for testing
- GitHub Actions for static analysis, tests, and publish

## Quick start

```bash
uv sync --group dev
uv run prek install
uv run prek run --all-files
uv run pytest
```

## Workflows

- **Static analysis**: `.github/workflows/static-analysis.yml`
- **Tests matrix**: `.github/workflows/tests.yml`
- **Publish to PyPI**: `.github/workflows/publish.yml`

## Publishing setup

1. Create a PyPI project with your package name.
2. Configure **Trusted Publishing** for this GitHub repo in PyPI.
3. Create a GitHub Release to trigger publishing.

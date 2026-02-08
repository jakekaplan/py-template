# py-template

A personal Python project template using:

- `uv` for dependency/env management
- `ruff` for linting + formatting
- `ty` for type checking
- `prek` for pre-commit-style hooks
- `loq` for file line-limit enforcement (`loq.toml`)
- `pytest` + `pytest-asyncio` for testing
- GitHub Actions for static analysis, tests, and publish


## Using this template

Replace `py-template` with your package name across the repo before doing anything else.

1. Rename package identifiers everywhere:
   - distribution name: `py-template`
   - import/package name: `py_template` (including `src/` path and test imports)

2. Update `pyproject.toml` metadata:
   - `name`, `description`, `authors`, `urls`, Python range

3. Re-lock and verify:
   - `uv sync --group dev && uv lock`
   - `uv run prek run --all-files && uv run pytest`

## Workflows

- **Static analysis**: `.github/workflows/static-analysis.yml`
- **Tests matrix**: `.github/workflows/tests.yml`
- **Publish to PyPI**: `.github/workflows/publish.yml`

## Publishing setup

1. Create a PyPI project with your package name.
2. Configure **Trusted Publishing** for this GitHub repo in PyPI.
3. Push a version tag (for example `0.1.0`) to trigger publishing.

## Versioning

This template uses dynamic versioning via `hatch-vcs`.

- Package version is derived from Git tags.
- Use tags like `MAJOR.MINOR.PATCH` (no `v` prefix).

# Claude Code Instructions

<!-- standard:start -->
## Code Style

- All public functions, methods, classes, and modules **must** have a docstring
- Use imperative mood: "Return the result." not "Returns the result."
- One-line docstrings for simple functions; multi-line with summary + details for complex ones
- Follow the Google docstring convention (D211, D212 selected via ruff)

## Linting

- Ruff enforces a comprehensive rule set -- run `uv run ruff check .` before committing
- Pyright runs in strict mode -- run `uv run pyright src tests` before committing
- All violations must be fixed, not ignored. Exceptions are the repo-owned `ignore` and `per-file-ignores` lists in `pyproject.toml`, which belong to this repo; the series sync never edits them

## Testing

- TDD workflow: Red-Green-Refactor
- Coverage is enforced by pytest-cov; the floor in `pyproject.toml` is repo-owned
- Test classes and methods also require docstrings
- Use named constants instead of magic values (PLR2004)
- Run `uv run pytest` before committing

## Commits

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`
- All changes go via PR from a feature branch (main is protected); merge when CI is green

## Dependencies

- Package manager: uv
- Run `uv sync --all-extras` after modifying dependencies
- `uv.lock` is committed; CI and pre-commit audit it with pip-audit through `uvx`, so pip-audit is not a project dependency
- Sibling projects, where used, are pinned release tags in `[tool.uv.sources]` (git + tag); never use `path` sources

## Releasing

- A release is a `vX.Y.Z` tag on main after the PR is merged
- Docs-only and tooling-only changes do not get a release tag
- Docs are built with `mkdocs build --strict` and deployed to GitHub Pages by the docs workflow
<!-- standard:end -->

This repo is the series home: `series.yml` lists the 17 projects, `src/series` loads it.

## series.yml

- Order is learning order; `builds_on` may only name projects listed earlier

## Project notes

- Docstrings are kid-friendly as well as Google-style
- Coverage must stay at or above 90%
- Always use `uv run` (system python3 is too old)

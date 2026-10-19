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
- Property-based tests (Hypothesis) live in `tests/test_properties.py` and `tests/test_model.py`; the shared profiles are in the root `conftest.py` (owned by `series sync`). Run `uv run pytest --hypothesis-profile=thorough` before a release.

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

This repo is the series home: `series.yml` lists the projects, `src/series` loads it.

## series.yml

- Order is learning order; `builds_on` may only name projects listed earlier

## Maintaining the series

- Full runbook: "Maintaining the series" in `README.md`
- `uv run series hub` regenerates this repo's `docs/index.md`, `docs/property-testing.md`, `docs/robots.txt` (every sitemap), README series/docs blocks, CLAUDE.md standard block and mkdocs series nav from `series.yml`; `tests/test_hub.py` fails when any of them drift, so re-run it after every `series.yml` or template edit
- Add a project: copy a repo, then fix its mkdocs `site_name`/`site_url`/`repo_url`/`repo_name` (the sync doesn't own them); add it to `series.yml` (with its `property` one-liner) and to `HOME_GROUPS` in `src/series/sync.py` (an ungrouped project is an error); enable Pages with `gh api -X POST repos/robcox2910/<repo>/pages -f build_type=workflow`; `series sync --repo <repo>`; full `series sync`; `series hub`
- `series sync` and `series sync --check` need a fresh, empty `SERIES_SCRATCH` each run (an existing clone is refused); `--check` exits 0 clean, 1 drift (a stale `uv.lock` counts), 2 a repo failed; when a sync changes a repo's `pyproject.toml` it runs `uv lock` there and commits the lock
- `v1` policy: test a workflow change by pointing one project PR's caller at the branch commit SHA before moving `v1`; consider immutable `v1.0.x` tags alongside; a breaking change gets `v2`, a template change and one sync
- `uv run series about` sets each repo's GitHub description, website and topics from `series.yml`; the sync also owns `site_description` in every `mkdocs.yml`, the `plugins` key (inside the theme block) and `overrides/main.html` (GoatCounter, from `GOATCOUNTER_CODE` in `src/series/config.py`)
- This repo's site deploys via `.github/workflows/site.yml` (which calls the local `docs.yml`), so "the docs workflow" in the standard above means `site.yml` here; the hub keeps its own `ci.yml`/`site.yml` and never gets the `@v1` caller files

## Project notes

- Docstrings are kid-friendly as well as Google-style
- Coverage must stay at or above 90%
- Always use `uv run` (system python3 is too old)

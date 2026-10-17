# Claude Code Instructions

This repo is the series home: `series.yml` lists the 17 projects, `src/series` loads it.

## Code Style

- All public functions, methods, classes, and modules **must** have a docstring (Google convention, imperative mood, kid-friendly)
- Ruff and strict pyright must be clean: `uv run ruff check .`, `uv run pyright`

## Testing

- TDD workflow: Red-Green-Refactor; coverage must stay at or above 90%
- Test classes and methods require docstrings; use named constants (PLR2004)
- Always use `uv run` (system python3 is too old)

## Commits

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`

## series.yml

- Order is learning order; `builds_on` may only name projects listed earlier

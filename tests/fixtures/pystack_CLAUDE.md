# Claude Code Instructions

## Code Style

- All public functions, methods, classes, and modules **must** have a docstring
- Use imperative mood: "Return the result." not "Returns the result."
- One-line docstrings for simple functions; multi-line with summary + details for complex ones
- Follow the Google docstring convention (D211, D212 selected via ruff)

## Linting

- Ruff enforces a comprehensive rule set -- run `uv run ruff check .` before committing
- Pyright in strict mode -- run `uv run pyright src tests` before committing
- All violations must be fixed, not ignored (except D203/D213 incompatible pair)

## Testing

- TDD workflow: Red-Green-Refactor
- Minimum 80% coverage enforced by pytest-cov
- Test classes and methods also require docstrings
- Use named constants instead of magic values (PLR2004)
- Run `uv run pytest` before committing

## Commits

- Use conventional commits (enforced by commitizen): `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`
- All changes go via PR from a feature branch (main is protected)

## Dependencies

- Package manager: uv
- Sibling projects are pinned release tags in `[tool.uv.sources]` (git + tag); `uv.lock` records the commit
- Upgrade a sibling: edit its tag, run `uv lock --upgrade-package <name>`, open a PR
- Try an unreleased sibling change: `uv pip install -e ../<folder>`, then run with `uv run --no-sync ...`; a plain `uv run` or `uv sync` restores the pin
- Never use `path` sources -- `tests/test_dependency_pins.py` enforces this
- Run `uv sync --all-extras` after modifying dependencies

## Plugins

- Plugin state lives on the plugin instance, never in module-level variables (`tests/test_plugin_persistence.py` enforces this for the storage plugins)
- Pebble functions are plugin methods decorated with `@pebble_method`; build the `StdlibModule` from bound methods
- Persist with `load_state(folder)` / `save_state(folder)`; `folder` is `<db_path>/<pebble_module_name()>/`; write nothing if the plugin has no state; let the library's `PersistenceError` propagate from `load_state`
- Run Pebble only through its public API (`from pebble import ...`); never write to `pebble.stdlib.STDLIB_MODULES`

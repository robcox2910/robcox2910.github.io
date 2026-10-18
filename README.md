# Series home

The home page and shared standards for the "from scratch in Python" series by
[Rob Cox](https://github.com/robcox2910). The list of projects lives in `series.yml`.

```bash
uv sync
uv run pytest
uv run series hub   # regenerate this repo's pages from series.yml
```

## Maintaining the series

`series.yml` is the single source of truth, and `templates/` holds the shared
standard. `series sync` writes them into every project (LICENSE, workflows,
pre-commit config, the README series and docs blocks, the CLAUDE.md standard
and the mkdocs theme and series nav). `series hub` does the same for this repo:
the home page (`docs/index.md`), the property-testing page
(`docs/property-testing.md`), the README blocks, the CLAUDE.md standard and the
mkdocs series nav. Never edit a marked block by hand; edit the source and
re-run.

### Add a project

1. Start the new repo as a copy of an existing project. Then fix its
   `mkdocs.yml` `site_name`, `site_url`, `repo_url` and `repo_name` by hand: the
   sync owns only the theme and series-nav blocks in that file, not those keys.
2. Add the project to `series.yml` (learning order; `builds_on` may only name
   earlier projects; `property` is the one-line rule its
   `docs/property-testing.md` walks through) and put its repo in one of the
   `HOME_GROUPS` in `src/series/sync.py`. `series hub` stops with an error until you do.
3. Turn on GitHub Pages with workflow builds:
   `gh api -X POST repos/robcox2910/<repo>/pages -f build_type=workflow`.
4. Sync the new repo, then every other repo (so their tables and navs list
   it), and merge each PR on green CI:
   `SERIES_SCRATCH=$(mktemp -d) uv run series sync --repo <repo>`, then
   `SERIES_SCRATCH=$(mktemp -d) uv run series sync`.
5. Regenerate the hub with `uv run series hub` and commit the result. The
   hub's tests fail while `docs/index.md`, `docs/property-testing.md`, the
   README blocks, the CLAUDE.md standard or the mkdocs series nav differ from what `series.yml` renders.

To change the standard or the series list, edit `templates/` or `series.yml`,
then run step 4's full sync and step 5.

### Check for drift

`SERIES_SCRATCH=$(mktemp -d) uv run series sync --check` clones every project
and lists what would change. It exits 0 when all are clean, 1 on drift and 2
when a repo failed (each failure is named, and the other repos still run). Use
a fresh, empty `SERIES_SCRATCH` for every run: an existing clone is refused,
never reused. `uv run series hub --check` does the same for this repo.

### The `v1` workflows

Projects call `python-ci.yml@v1` and `docs.yml@v1` from this repo, and `v1` is
a moving tag, so a change reaches every project at once.

- Test a workflow change before moving `v1`: push it on a branch, point one
  project's caller at that commit
  (`uses: robcox2910/robcox2910.github.io/.github/workflows/python-ci.yml@<sha>`)
  in a throwaway PR, and check its CI is green. Then move the tag:
  `git tag -fa v1 -m v1 <sha> && git push -f origin v1`.
- Consider tagging an immutable `v1.0.x` alongside each move, so a bad move
  can be undone by pointing `v1` back at the previous one.
- A breaking change (a new required input, or removed behaviour) gets a new
  `v2` tag, a template change to `@v2`, and one sync.
- This repo calls its own workflows locally (`ci.yml`, and `site.yml` for the
  home page) and never gets the `@v1` caller files.

<!-- series:start -->
## Related Projects

This project is one of a series that builds real systems "from scratch in Python" to teach how they work. See the [series home](https://robcox2910.github.io/) for the full story.

| Project | What it teaches | Repository | Docs |
| --- | --- | --- | --- |
| PyOS | Operating systems | [py-os](https://github.com/robcox2910/py-os) | [Docs](https://robcox2910.github.io/py-os/) |
| Pebble | Compilers and programming languages | [pebble-lang](https://github.com/robcox2910/pebble-lang) | [Docs](https://robcox2910.github.io/pebble-lang/) |
| PyDB | Relational databases | [pydb](https://github.com/robcox2910/pydb) | [Docs](https://robcox2910.github.io/pydb/) |
| PyKV | Key-value stores | [pykv](https://github.com/robcox2910/pykv) | [Docs](https://robcox2910.github.io/pykv/) |
| PyDocDB | Document databases | [pydoc-db](https://github.com/robcox2910/pydoc-db) | [Docs](https://robcox2910.github.io/pydoc-db/) |
| PyGraphDB | Graph databases | [pygraphdb](https://github.com/robcox2910/pygraphdb) | [Docs](https://robcox2910.github.io/pygraphdb/) |
| PyTSDB | Time-series databases | [pytsdb](https://github.com/robcox2910/pytsdb) | [Docs](https://robcox2910.github.io/pytsdb/) |
| PyVecDB | Vector databases | [pyvecdb](https://github.com/robcox2910/pyvecdb) | [Docs](https://robcox2910.github.io/pyvecdb/) |
| PyColDB | Column-family databases | [pycoldb](https://github.com/robcox2910/pycoldb) | [Docs](https://robcox2910.github.io/pycoldb/) |
| PyCrypt | Cryptography | [pycrypt](https://github.com/robcox2910/pycrypt) | [Docs](https://robcox2910.github.io/pycrypt/) |
| PyNet | Computer networking | [pynet](https://github.com/robcox2910/pynet) | [Docs](https://robcox2910.github.io/pynet/) |
| PyWeb | HTTP web servers | [pyweb](https://github.com/robcox2910/pyweb) | [Docs](https://robcox2910.github.io/pyweb/) |
| PyGit | Version control | [pygit](https://github.com/robcox2910/pygit) | [Docs](https://robcox2910.github.io/pygit/) |
| PySearch | Search engines | [pysearch](https://github.com/robcox2910/pysearch) | [Docs](https://robcox2910.github.io/pysearch/) |
| PyMQ | Message queues | [pymq](https://github.com/robcox2910/pymq) | [Docs](https://robcox2910.github.io/pymq/) |
| PyLLM | Language models (the brain) | [pyllm](https://github.com/robcox2910/pyllm) | [Docs](https://robcox2910.github.io/pyllm/) |
| PyStack | Full-stack integration | [pystack](https://github.com/robcox2910/pystack) | [Docs](https://robcox2910.github.io/pystack/) |
<!-- series:end -->

<!-- docs:start -->
## Documentation

Full docs (with kid-friendly explanations of every idea): https://robcox2910.github.io/
<!-- docs:end -->

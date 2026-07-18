# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mkdocs-clickup` is a MkDocs plugin to publish documentation to [ClickUp Pages](https://clickup.com/features/docs). It started as a fork of [pawamoy/mkdocs-llmstxt](https://github.com/pawamoy/mkdocs-llmstxt) (a plugin that generates an `/llms.txt` file), reusing its HTML→Markdown conversion pipeline as a foundation — the llms.txt-specific behavior itself has been stripped out (bootstrap phase, see `git log`).

**Current state: bootstrap skeleton.** The plugin converts each page's HTML to Markdown and stores it (`on_page_content`), but does not yet publish anything to ClickUp — that requires the ClickUp API research spike (see README.md's "ClickUp API research" section) followed by an OpenSpec-driven implementation change (see `openspec/`). Don't assume ClickUp integration exists yet; check `src/mkdocs_clickup/_internal/plugin.py` for what's actually implemented.

The project is scaffolded from the [copier-uv](https://github.com/pawamoy/copier-uv) template (see `.copier-answers.yml`); "Template upgrade" commits are automated re-applications of that template and shouldn't be hand-edited piecemeal.

The `LICENSE` carries two copyright holders: Timothée Mazzucotelli (original `mkdocs-llmstxt` author, whose code is still partly reused) and Hector Espert (this fork's maintainer).

## Commands

Tasks run through `scripts/make` (a `duty`-based Python task runner defined in `duties.py`): `python scripts/make <task>`. There is no Makefile — with `direnv allow`'d, `.envrc` puts `scripts/` on `PATH`, so `make <task>` works directly as a shorthand; without direnv, always use the `python scripts/make <task>` form (this is what CI uses).

- `python scripts/make setup` — install dependencies via `uv sync` (first-time setup)
- `python scripts/make test` — run the full test suite (pytest, parallelized with `pytest-xdist`, coverage on)
- `python scripts/make check` — run everything CI checks: quality (ruff), types (mypy), docs build, and API compatibility
- `python scripts/make check-quality` — ruff lint only (`config/ruff.toml`)
- `python scripts/make check-types` — mypy only (`config/mypy.ini`)
- `python scripts/make check-docs` — build the docs strictly (fails on warnings)
- `python scripts/make check-api` — check for breaking API changes via `griffe check`
- `python scripts/make format` — auto-fix + format code with ruff
- `python scripts/make docs` — serve docs locally at `127.0.0.1:8000`
- `python scripts/make coverage` — combine and report coverage (text + HTML)
- `python scripts/make run <cmd>` / `python scripts/make multirun <cmd>` — run an arbitrary command in the project env (multirun = across all supported Python versions)

Run a single test file or test directly with pytest (bypassing the `make test` wrapper when you need finer control):

```bash
uv run pytest tests/test_link_conversion.py -k test_relative_links_are_made_absolute -c config/pytest.ini
```

`config/pytest.ini` sets `testpaths = tests` and enables coverage by default; `-c config/pytest.ini` is required since the config lives outside the repo root.

## Architecture

The plugin's entire logic lives under `src/mkdocs_clickup/_internal/` (the public surface is just what `__init__.py` re-exports — `_internal` signals "not part of the public API" per the project's typing conventions):

- **`plugin.py`** — `MkdocsClickUpPlugin`, the MkDocs plugin class. Currently only hooks `on_config` (captures the global MkDocs config, resolves `base_url`, falls back to `site_url`) and `on_page_content` (converts every page's rendered HTML to Markdown via `_generate_page_markdown` and stores it in `self._md_pages`, unconditionally for now — see the `TODO(clickup-spike)` comment). There is deliberately no `on_post_build` yet — that's where ClickUp API calls will go once designed.
- **`config.py`** — `_PluginConfig`, the `mkdocs.yml`-facing schema — currently just `autoclean`, `preprocess`, `base_url` (generic knobs kept from the original plugin; ClickUp-specific config like auth tokens/workspace IDs doesn't exist yet)
- **`preprocess.py`** — HTML cleanup pipeline: `autoclean()` strips MkDocs/mkdocstrings-generated cruft (images, permalinks, emoji, tab labels, mkdocstrings labels/descriptions, code-block line numbers) before Markdown conversion; `_preprocess()` dynamically loads a user-supplied Python module (via `preprocess:` config option) and calls its `preprocess(soup, output)` function for site-specific HTML tweaks
- **`debug.py`** / **`logger.py`** — supporting utilities

Key design point: HTML → Markdown conversion (`_generate_page_markdown` in `plugin.py`) always runs `autoclean` (unless disabled) → optional user `preprocess` → link absolutization (`_convert_to_absolute_links`, resolves relative hrefs against the page's position in the site and rewrites directory-style links to point at `index.md`) → `markdownify` → `mdformat` (with the `tables` extension). This order matters: user preprocessing sees already-cleaned HTML but still-relative links. The link-absolutization step is flagged for redesign once the ClickUp API spike clarifies whether ClickUp addresses pages by URL or by internal page ID.

Tests (`tests/`) build real MkDocs sites in a `tmp_path` via the `mkdocs_conf`/`plugin` fixtures in `conftest.py` (parametrized indirectly with `config`/`pages` dicts), then run `mkdocs.commands.build.build()` and assert on the generated output files — this is an integration-style test setup, not unit tests against internal functions in isolation. There is currently no end-to-end integration test (the old `test_plugin.py` was llms.txt-specific and was removed); `test_link_conversion.py` and `test_api.py` are the surviving tests.

## Conventions

- Commit messages follow the Angular/Karma convention: `<type>[(scope)]: Subject` — types are `build`, `chore`, `ci`, `deps`, `docs`, `feat`, `fix`, `perf`, `refactor`, `style`, `tests`. Subject: no trailing period, proper casing, valid Markdown. Any trailers (issue/PR refs) go at the end of the body as full URLs, no blank line between them, and don't rely on GitHub's `#123` autolink shorthand.
- The changelog (`CHANGELOG.md`) is generated by `git-changelog` from commit messages — don't hand-edit entries for merged work.
- Versioning is derived from Git tags at build time (`scripts/get_version.py`), falling back to the latest `CHANGELOG.md` heading if SCM tags are absent/too low — there's no hardcoded version string to bump in source.
- `ruff` config bans relative imports and requires Google-style docstrings; per-path ignores in `config/ruff.toml` relax docstring/print-statement rules for `scripts/`, `tests/`, and CLI/debug modules.
- Use an `Assisted-By` trailer instead of `Co-Authored-By` on commits made with AI assistance.
- New capabilities (like the ClickUp publishing behavior itself) are meant to go through the OpenSpec workflow (`.claude/skills/openspec-*`, `openspec/`) — propose → specs/design → tasks → apply — rather than being implemented ad hoc. Pure mechanical/cleanup work (like this bootstrap phase) doesn't need it.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

This is `mkdocs-llmstxt` (fork of [pawamoy/mkdocs-llmstxt](https://github.com/pawamoy/mkdocs-llmstxt), published at repo `hectorespert/mkdocs-clickup`) — a MkDocs plugin that generates an `/llms.txt` file (per the [llms.txt spec](https://llmstxt.org/)) plus a Markdown version of every documented page, so LLMs can consume site content directly instead of scraping rendered HTML.

The project is scaffolded from the [copier-uv](https://github.com/pawamoy/copier-uv) template (see `.copier-answers.yml`); "Template upgrade" commits are automated re-applications of that template and shouldn't be hand-edited piecemeal.

> The upstream project is in maintenance mode (see README warning) — the maintainer is focused elsewhere and open to transferring ownership.

## Commands

This repo uses `make` as a thin wrapper: with `direnv allow`'d, `make <task>` forwards to `scripts/make <task>` (a `duty`-based Python task runner defined in `duties.py`). Without direnv, run `python scripts/make <task>` directly, or invoke the underlying tools yourself.

- `make setup` — install dependencies via `uv sync` (first-time setup)
- `make test` — run the full test suite (pytest, parallelized with `pytest-xdist`, coverage on)
- `make check` — run everything CI checks: quality (ruff), types (mypy), docs build, and API compatibility
- `make check-quality` — ruff lint only (`config/ruff.toml`)
- `make check-types` — mypy only (`config/mypy.ini`)
- `make check-docs` — build the docs strictly (fails on warnings)
- `make check-api` — check for breaking API changes via `griffe check`
- `make format` — auto-fix + format code with ruff
- `make docs` — serve docs locally at `127.0.0.1:8000`
- `make coverage` — combine and report coverage (text + HTML)
- `make run <cmd>` / `make multirun <cmd>` — run an arbitrary command in the project env (multirun = across all supported Python versions)

Run a single test file or test directly with pytest (bypassing the `make test` wrapper when you need finer control):

```bash
uv run pytest tests/test_plugin.py -k test_plugin -c config/pytest.ini
```

`config/pytest.ini` sets `testpaths = tests` and enables coverage by default; `-c config/pytest.ini` is required since the config lives outside the repo root.

## Architecture

The plugin's entire logic lives under `src/mkdocs_llmstxt/_internal/` (the public surface is just what `__init__.py` re-exports — `_internal` signals "not part of the public API" per the project's typing conventions):

- **`plugin.py`** — `MkdocsLLMsTxtPlugin`, the MkDocs plugin class, hooking into three MkDocs build events:
  - `on_config` — captures the global MkDocs config and resolves `base_url` (falls back to `site_url`)
  - `on_files` — expands each configured section's file list (glob patterns via `fnmatch`) against the actual page URIs
  - `on_page_content` — for every page that matches a configured section, converts its rendered HTML to Markdown and stashes it (nothing is written yet — this fires per-page, before the site is fully built)
  - `on_post_build` — after all pages are converted, writes the per-page `.md` files, assembles `llms.txt` (and optionally `llms-full.txt` with full page content inlined) from the stashed pages
- **`config.py`** — `_PluginConfig`, the `mkdocs.yml`-facing schema (`sections`, `base_url`, `autoclean`, `preprocess`, `markdown_description`, `full_output`)
- **`preprocess.py`** — HTML cleanup pipeline: `autoclean()` strips MkDocs/mkdocstrings-generated cruft (images, permalinks, emoji, tab labels, mkdocstrings labels/descriptions, code-block line numbers) before Markdown conversion; `_preprocess()` dynamically loads a user-supplied Python module (via `preprocess:` config option) and calls its `preprocess(soup, output)` function for site-specific HTML tweaks
- **`debug.py`** / **`logger.py`** — supporting utilities

Key design point: HTML → Markdown conversion (`_generate_page_markdown` in `plugin.py`) always runs `autoclean` (unless disabled) → optional user `preprocess` → link absolutization (`_convert_to_absolute_links`, resolves relative hrefs against the page's position in the site and rewrites directory-style links to point at `index.md`) → `markdownify` → `mdformat` (with the `tables` extension). This order matters: user preprocessing sees already-cleaned HTML but still-relative links.

Tests (`tests/`) build real MkDocs sites in a `tmp_path` via the `mkdocs_conf`/`plugin` fixtures in `conftest.py` (parametrized indirectly with `config`/`pages` dicts), then run `mkdocs.commands.build.build()` and assert on the generated output files — this is an integration-style test setup, not unit tests against internal functions in isolation.

## Conventions

- Commit messages follow the Angular/Karma convention: `<type>[(scope)]: Subject` — types are `build`, `chore`, `ci`, `deps`, `docs`, `feat`, `fix`, `perf`, `refactor`, `style`, `tests`. Subject: no trailing period, proper casing, valid Markdown. Any trailers (issue/PR refs) go at the end of the body as full URLs, no blank line between them, and don't rely on GitHub's `#123` autolink shorthand.
- The changelog (`CHANGELOG.md`) is generated by `git-changelog` from commit messages — don't hand-edit entries for merged work.
- Versioning is derived from Git tags at build time (`scripts/get_version.py`), falling back to the latest `CHANGELOG.md` heading if SCM tags are absent/too low — there's no hardcoded version string to bump in source.
- `ruff` config bans relative imports and requires Google-style docstrings; per-path ignores in `config/ruff.toml` relax docstring/print-statement rules for `scripts/`, `tests/`, and CLI/debug modules.

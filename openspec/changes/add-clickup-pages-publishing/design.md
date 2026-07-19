## Context

`MkdocsClickUpPlugin` (`src/mkdocs_clickup/_internal/plugin.py`) currently only implements `on_config` (validates `site_url`, resolves `base_url`) and `on_page_content` (converts each page's HTML to Markdown via `_generate_page_markdown`, storing the result in `self._md_pages: dict[str, str]` keyed by `page.file.src_uri`). There is no network I/O anywhere in the plugin today, and no HTTP client dependency exists in `pyproject.toml`.

The ClickUp API research (README.md, "ClickUp API research" section) already answered the load-bearing unknowns for this change:
- Content format: `POST .../docs/{doc_id}/pages` accepts plain Markdown (`content_format: "text/md"`) directly — no second conversion stage needed.
- Auth: personal token, sent as `Authorization: {token}` (no `Bearer` prefix — that form is OAuth2-specific).
- Endpoint: `POST https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages`.
- Rate limits: 100–10,000 req/min depending on plan tier; 429 on excess.

This change implements the smallest possible slice that actually calls that endpoint, deferring hierarchy, page selection, idempotency, and rate-limit handling to later changes (see proposal.md and specs/clickup-pages-publishing/spec.md for exactly what's in and out of scope).

## Goals / Non-Goals

**Goals:**
- Every page MkDocs converts gets created as a ClickUp Page in a pre-configured Doc.
- Config validation follows the existing `on_config` pattern (fail fast with a clear error).
- The token never appears in `mkdocs.yml` or anywhere it could be committed to version control.

**Non-Goals (explicitly deferred to future changes):**
- Page selection/filtering.
- Nested page hierarchy (`parent_page_id`).
- Idempotency / update-in-place / persisted `mkdocs page → clickup page_id` mapping.
- Rate-limit backoff/retry.
- OAuth2 support.
- Batching multiple page-creates into fewer HTTP calls (no such endpoint exists per the research).

## Decisions

**HTTP client: use `httpx`.** The project has no HTTP client dependency yet. `httpx` is chosen over `requests` because it has first-class typing (matches this project's `mypy`-strict conventions) and both sync and async APIs if a future change wants to parallelize page creation; sync usage is all this change needs. Add `httpx>=0.27` to `pyproject.toml`'s `dependencies` (not a dev-only dependency — it's needed at plugin runtime).

**Token via `CLICKUP_API_TOKEN` env var, read in `on_config`.** Read with `os.environ.get("CLICKUP_API_TOKEN")` inside `on_config`, alongside the existing `site_url` check, and store on `self._clickup_token`. Raise the same kind of `ValueError` as the existing `site_url` check if unset — keeps a single, consistent "fail fast on missing setup" pattern rather than introducing a different error-handling style for this one setting.

**New required config fields `workspace_id` and `doc_id` on `_PluginConfig`.** Both are plain strings (ClickUp's own API docs type `workspace_id` as a path parameter but don't guarantee a numeric-looking string is safe to treat as an int — treat both as opaque strings to avoid a class of encoding bugs). Neither has a default; `mkconf.Type(str)` (no `mkconf.Optional`) so MkDocs' own config validation reports a clear error if either is missing, consistent with how `sections` used to be required in the old llms.txt config.

**`_md_pages` changes shape: `dict[str, str]` → `dict[str, tuple[str, str]]` (title, markdown).** `on_page_content` currently discards `page.title`, but the ClickUp create-page request needs a `name`. Store `(page.title or page.file.src_uri, page_md)` per page — reusing the same "fall back to `src_uri` if the page has no title" behavior the plugin's llms.txt-era predecessor used for its own page titles ([`_MDPageInfo.title`](git history) before it was stripped during bootstrap).

**Publishing happens in a new `on_post_build` hook, not inline in `on_page_content`.** Network calls belong after all pages are converted, not interleaved with page rendering — matches the shape of the original (pre-bootstrap) plugin, which also did all of its output-writing in `on_post_build` after `on_page_content` finished stashing converted pages. This also means a single config/token validation failure surfaces before any page conversion work is wasted (since `on_config` runs first and raises immediately), and all HTTP calls happen in one clearly-delimited phase that's easy to reason about and test.

**Fail-fast on the first publish error, using MkDocs' own `PluginError`.** On any non-2xx response (or a `httpx` network-level exception) while creating a page, raise `mkdocs.exceptions.PluginError` with the page's `src_uri` and the response body/status (or the underlying exception) in the message, aborting the rest of `on_post_build` immediately. Simpler than partial-success bookkeeping, and `PluginError` is what MkDocs itself expects plugins to raise for user-facing build failures (`preprocess.py`'s `_preprocess` already uses the same exception for its own error path, so this stays consistent with the codebase's existing convention).

**HTTP client instantiated once per build, in `on_post_build`, not stored as instance state.** A short-lived `httpx.Client()` as a context manager for the duration of `on_post_build` is enough for the flat, small number of requests this version makes — no connection-pool lifetime concerns worth solving now.

## Risks / Trade-offs

- **[Risk] Every build creates duplicate ClickUp Pages** (by design, per proposal.md) → **Mitigation**: none in this change; explicitly documented as a known v1 limitation in the proposal and spec, with a future "update instead of duplicate" change already anticipated (would need a persisted `page_id` mapping or a pre-publish "fetch existing pages, match by name" step).
- **[Risk] No rate-limit handling — a large doc site could hit HTTP 429 mid-build** → **Mitigation**: none in this change (explicitly a non-goal); the fail-fast behavior at least makes a 429 visible immediately as a build failure rather than a silent partial publish. A future change should add backoff respecting `X-RateLimit-Reset`.
- **[Risk] Fixed env var name (`CLICKUP_API_TOKEN`) means only one ClickUp target per machine/CI job** → **Mitigation**: acceptable for v1; if multi-target publishing is ever needed, that's a config-vs-env-var trade-off for a future change to revisit, not a blocker here.
- **[Risk] `httpx` is a new runtime dependency** → **Mitigation**: it's a widely-used, actively maintained, fully-typed library; low risk relative to the alternative of hand-rolling HTTP with `urllib`.

## Migration Plan

This is a new capability with no prior behavior to migrate away from (the old llms.txt-publishing behavior was already removed during the bootstrap phase). Rollout is: implement, add tests, update README's "Usage" section with the new required config (`workspace_id`, `doc_id`, `CLICKUP_API_TOKEN`) once implemented. No rollback concerns beyond reverting the change, since nothing in this version persists state that would need cleanup (no mapping file, no created-Doc bookkeeping — the Doc itself is user-provided and untouched by rollback).

## Open Questions

- Exact `httpx` timeout/retry-on-connection-error defaults haven't been decided — default to `httpx`'s own defaults for this version unless implementation turns up a concrete reason not to.
- Whether `workspace_id`/`doc_id` validation in `on_config` should also verify they're non-empty strings (vs. just "key present") — leaving this to implementation judgment during `tasks.md` execution rather than over-specifying here.

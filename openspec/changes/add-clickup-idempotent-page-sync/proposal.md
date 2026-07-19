## Why

v1 always creates a new ClickUp Page for every MkDocs page on every build, an accepted-but-real limitation: a site published repeatedly (e.g. on every CI run) accumulates duplicate pages in the target Doc indefinitely, with no way to clean them up. This change replaces "always create" with an idempotent publish: match against pages already in the Doc and update them in place, and archive pages whose source no longer exists.

## What Changes

- **BREAKING**: `on_post_build` no longer creates a new ClickUp Page unconditionally. It first fetches existing pages in the Doc (`GET .../docs/{doc_id}/pages`) and matches them against the current build's pages.
- Each published page now carries an identity key in ClickUp's `sub_title` field (the MkDocs `src_uri`), used for matching across builds instead of the page title (`name`), which MkDocs does not guarantee to be unique.
- A page whose `sub_title` matches an existing ClickUp page is updated in place (`PUT`, same `page_id`, stable URL) instead of creating a duplicate.
- A page with no match is created (`POST`) exactly as in v1, now also setting `sub_title`.
- An existing ClickUp page whose `sub_title` no longer matches any current MkDocs page (its source file was renamed or deleted) is archived via `PUT { archived: true }` — a best-effort, non-fatal operation: `archived` is not part of ClickUp's documented Edit Page schema, so a failure to archive is logged and does not fail the build.
- Publish failures for create/update (not archival) continue to abort the build, as in v1.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `clickup-pages-publishing`:
  - "Always create, never update" is replaced by match-then-create-or-update, keyed on a `sub_title`-encoded `src_uri`.
  - "Publish failures abort the build" is narrowed: it still applies to create/update failures, but orphan-archival failures are explicitly excluded (logged, non-fatal).
  - New requirement: orphaned ClickUp pages (no matching current MkDocs page) are archived best-effort.

## Impact

- `src/mkdocs_clickup/_internal/plugin.py`: `on_post_build` gains a fetch-and-match step before the create/update loop, and an archival step for orphans.
- `openspec/specs/clickup-pages-publishing/spec.md`: requirements updated per above.
- Tests: `tests/test_plugin.py` needs new fixtures/mocks for `GET .../pages` and the match/update/archive branches, replacing assertions that assumed every build always creates.
- No new configuration options and no new environment variables — this changes `on_post_build` behavior only.
- Out of scope (deferred, unchanged from v1): rate-limit backoff/retry on HTTP 429, page selection/filtering, nested page hierarchy, OAuth2.

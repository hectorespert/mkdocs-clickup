## Context

v1's `on_post_build` (see `src/mkdocs_clickup/_internal/plugin.py`) POSTs a new ClickUp Page for every entry in `self._md_pages` on every build, with no awareness of what was published previously. This was an accepted v1 limitation, verified manually against a real ClickUp workspace to actually duplicate pages across repeated builds. This change was explored empirically against that same live workspace (`workspace_id=90121909276`, `doc_id=2kxuyd0w-512`) before being written up; the findings below are settled facts, not assumptions.

ClickUp's public Docs/Pages API (v3) exposes:
- `POST .../docs/{doc_id}/pages` — create
- `PUT .../docs/{doc_id}/pages/{page_id}` — update (`name`, `sub_title`, `content`, `content_edit_mode`, `content_format` — the only fields in the official schema, per `developer.clickup.com/reference/editpagepublic`)
- `GET .../docs/{doc_id}/pages` — list, returning full page objects (`id`, `name`, `sub_title`, `content`, `archived`, `deleted`, etc.) for every page in the Doc, no pagination param beyond `max_page_depth`

## Goals / Non-Goals

**Goals:**
- Publishing the same MkDocs page across multiple builds updates one ClickUp page in place instead of creating duplicates.
- A MkDocs page whose source is renamed or removed no longer leaves a permanently-visible orphan page in the Doc.
- Matching is reliable even when multiple MkDocs pages share the same title.

**Non-Goals:**
- Rate-limit backoff/retry on HTTP 429 (deferred from v1, stays deferred).
- Page selection/filtering, nested page hierarchy, OAuth2 (deferred from v1, stays deferred).
- Guaranteeing correct behavior at very large page counts — the `GET .../pages` call's payload size/latency at scale (hundreds+ pages, since it returns full `content` per page) was not tested and is noted as a known limitation, not solved here.

## Decisions

### Match key: `sub_title`, not `name`

Matching an existing ClickUp page to a current MkDocs page needs a stable, unique key. `name` (the page title) was rejected: MkDocs does not guarantee page titles are unique (e.g. two different `index.md` files both titled "Overview"), so title-based matching can pick the wrong page. `src_uri` (the MkDocs source path, already the unique key of `self._md_pages`) is unique by construction, so it is stored verbatim in ClickUp's `sub_title` field and used as the match key instead.

Verified live: `sub_title` round-trips completely unmodified — no markdown re-parsing, no escaping of `/` or `_` (tested with `"api/index.md"` and `"guide/advanced_config.md"`). This is unlike `content`, which IS re-parsed by ClickUp on ingestion (an HTML comment marker embedded in content was merged into the following line and had a bare filename auto-linkified) — ruling out an embedded-content-marker approach as unreliable.

**Alternative considered**: persist a `src_uri → page_id` mapping file (in-repo or CI-state). Rejected as unnecessary extra state to keep in sync when `sub_title` gives the same guarantee for free, using only fields ClickUp already returns from `GET .../pages`.

### One list call per build, not a lookup per page

`GET .../docs/{doc_id}/pages` returns every existing page (with `sub_title`) in a single call, so the match set can be built once per build and looked up in memory, instead of one `GET` per page.

### Orphan handling: best-effort archive via undocumented `archived` field

A ClickUp page whose `sub_title` matches no current MkDocs `src_uri` is orphaned (its source was renamed or deleted). `PUT` with `archived: true` removes it from subsequent `GET .../pages` listings — verified live — but `archived` is **not** part of ClickUp's documented Edit Page schema (only `name`, `sub_title`, `content`, `content_edit_mode`, `content_format` are documented). Because ClickUp could change or remove this undocumented behavior without notice, archival failures are logged as a warning and do **not** raise `PluginError` — an orphan that fails to archive simply stays visible (the same outcome as v1's status quo), rather than failing the whole build over a best-effort cleanup step.

**Alternative considered**: raise `PluginError` on archive failure, same as create/update failures. Rejected — an undocumented field failing silently server-side (not necessarily returning a clear error) shouldn't be able to break unrelated, successful publishes.

**Alternative considered**: don't attempt archival at all, leave orphans as a permanent known limitation (status quo). Rejected — the live verification showed it works today and meaningfully improves on v1's accumulation problem; declining to use it leaves value on the table for no correctness benefit, given the fallback is already safe.

### Create/update failures still abort the build

Unchanged from v1: a failed `PUT`/`POST` for a page's actual content still raises `PluginError` and aborts the build. Only the orphan-archival step gets the non-fatal fallback.

## Risks / Trade-offs

- **[Risk] `archived` is undocumented and could stop working or change behavior without notice** → Mitigation: treated as best-effort with a logged warning, never fatal; a code comment at the call site explains why.
- **[Risk] `GET .../pages` returns full `content` for every page — payload size/latency untested at scale** → Mitigation: none implemented in this change; noted as a known limitation for large sites, not solved here.
- **[Risk] A MkDocs page whose title changes but whose `src_uri` doesn't still matches and updates correctly** → this is actually a fix over v1/the title-matching alternative, not a new risk — noted here for completeness.
- **[Trade-off] A MkDocs page whose `src_uri` changes (file moved/renamed) is treated as delete-old + create-new, not update** → its old ClickUp page becomes an orphan (best-effort archived) and a new page is created with a new `page_id`/URL. This is accepted: `src_uri` is the only reliable identity signal available, and there's no way to distinguish "renamed file" from "deleted file, unrelated new file" without out-of-band state (rejected above).

## Migration Plan

No data migration. Existing ClickUp pages created by v1 builds have no `sub_title` set (empty/absent), so they will never match on the first idempotent build and will be treated as orphans — best-effort archived if `archived` still works, otherwise left visible, same as they are today. This is a one-time transition cost when a site upgrades from v1 behavior to this change, not an ongoing issue.

## Open Questions

- None blocking. The one open item (payload size/latency of `GET .../pages` at large page counts) is accepted as an untested, unsolved limitation rather than a blocking question.

## Context

The plugin's `on_post_build` (see `openspec/specs/clickup-pages-publishing/spec.md`) currently publishes every MkDocs page as a flat ClickUp Page: it never sets `parent_page_id`, and `_fetch_existing_pages` treats `GET .../docs/{doc_id}/pages` as returning a flat list. MkDocs, meanwhile, already builds a `nav` tree of `Section`/`Page`/`Link` nodes (`mkdocs.structure.nav`) before any page is rendered — `get_navigation(files, config)` runs before the per-page `on_page_content` loop in `mkdocs.commands.build.build`, so `page.parent` (a `Section` or `None`) is available whenever `on_page_content` fires.

Facts below were verified empirically against a real ClickUp workspace during exploration (not re-derived from documentation, which doesn't cover any of this):

- `GET .../docs/{doc_id}/pages` returns a **nested tree**: the top-level array holds only root pages (`parent_page_id: null`); every page carries its own children under a `pages` key, recursively. A page with a parent never appears in the top-level array. Full depth is returned by default — `max_page_depth` is not required.
- `PUT` accepts `parent_page_id` and takes effect immediately (verified via a follow-up `GET`), including setting it to `null` to un-parent a page back to the root. This field is undocumented (ClickUp's published Edit Page schema lists only `name`, `sub_title`, `content`, `content_edit_mode`, `content_format`) but behaves reliably, the same undocumented-but-working pattern already accepted for `archived` in the idempotent-sync change.
- MkDocs' `Section` is a pure grouping node — it never has its own `src_uri`/content. This holds for both manual `nav:` config and MkDocs' auto-generated nav (`nest_paths`/`dirname_to_title`), so "a `Section` IS a page" is never a safe assumption.

## Goals / Non-Goals

**Goals:**
- Mirror the MkDocs `nav` hierarchy in ClickUp using `parent_page_id`, as the default (non-configurable) publish behavior.
- Keep the existing idempotent match/update/archive machinery (`sub_title`-keyed) working for nested pages, which requires fixing the flat-list assumption in `_fetch_existing_pages`.
- Allow a page's computed parent to change across builds (Section gains/loses its index page, nav is restructured) via a plain `PUT`, without archive+recreate.

**Non-Goals:**
- Configurable opt-in/opt-out of nesting (flat publish was a proof-of-concept behavior, not a contract to preserve).
- Controlling sibling order in ClickUp (`order_index` is not part of any documented create/update field; ClickUp's own insertion order applies).
- Deciding the final content of placeholder anchor pages beyond empty — deferred to a future change once real usage shows what's useful there.
- Rate-limit backoff, page selection/filtering, OAuth2 — already-deferred non-goals from prior changes, unaffected by this one.

## Decisions

### Anchor resolution: real index page, else synthetic placeholder

For each `Section` encountered in the nav tree:
- If one of its direct children is a `Page` whose `src_uri` ends in `index.md` or `README.md`, that page is the anchor — its ClickUp `page_id` is used as `parent_page_id` for the Section's other members.
- Otherwise, a synthetic placeholder ClickUp Page is created/updated as the anchor, with empty `content` and `sub_title` derived from the Section's title breadcrumb (e.g. `"__section__:Guide/Random Topics"`, joining ancestor `Section.title`s down to this one).

**Rejected alternative**: always create a placeholder page per `Section`, ignoring any real index page. Rejected because it needlessly duplicates content that already has a natural home (the index page itself), and would surprise users who already follow the common "folder + `index.md`" convention.

**Rejected alternative**: derive the placeholder's synthetic identity from the directory path instead of the title breadcrumb. Rejected because manual `nav:` config can group pages from unrelated directories under one `Section` with no common path prefix (e.g. `Overview: [intro.md, about.md]`), so a path-based key isn't always definable. A `Section`'s `title` is the one thing that's always present, in both manual and MkDocs' own auto-generated nav.

**Consequence**: a placeholder's synthetic `sub_title` is only as stable as the `Section`'s title breadcrumb. Renaming or moving a `Section` orphans its old placeholder (archived) and creates a new one — the same accepted trade-off already documented for renamed MkDocs source files in the idempotent-sync change.

### Anchor's own parent

The anchor page of a `Section` is not parented to itself. Its `parent_page_id` is resolved from the *Section's own parent* (`Section.parent`), not from the Section it anchors — otherwise an anchor page would attempt to be its own parent. A top-level `Section` (no `Section.parent`) yields `parent_page_id: null` for its anchor, same as any other root-level page.

### Fetch must recursively flatten the tree

`_fetch_existing_pages` currently returns `list(response.json())` — only root pages under the current flat-publish behavior, where nothing has a parent yet. As soon as any page has `parent_page_id` set, it stops appearing in the top-level array and becomes invisible to the existing `sub_title`-keyed matching, silently defeating idempotency for every nested page (they'd be recreated on every build instead of matched). The fetch is changed to walk each page's `pages` key recursively and return every page (root and nested) as a single flat list, exactly as before from the matching logic's point of view.

### Re-parenting is a normal update, not archive+recreate

Because `PUT` accepts `parent_page_id` (verified live), a matched page whose computed parent differs from its previously-stored parent is simply updated in place with the new `parent_page_id`, alongside its existing `name`/`content`/`sub_title` update. No new mechanism is needed beyond passing the currently-resolved `parent_page_id` on every `PUT`, matched or not.

**Rejected alternative**: treat any parent change as equivalent to a rename (archive old page, create new one). Rejected once the live `PUT` test confirmed re-parenting works — this would have been unnecessary data loss (losing the page's ClickUp URL/history for no reason).

### Publish ordering: parent before child

The current publish loop iterates `self._md_pages` (a plain `dict`) in arbitrary/insertion order, which is safe today only because no page ever references another. Once anchors exist, a page's create/update request needs its resolved anchor's ClickUp `page_id` already known — either from a prior `GET` match or from having just been created earlier in the same build. `on_page_content` is extended to also capture each page's `Section` parent reference (`page.parent`), and `on_post_build` processes the tree depth-first (anchors and placeholders resolved and published before the pages/placeholders that depend on them), instead of the current flat iteration.

## Risks / Trade-offs

- **[Risk] Placeholder pages with no real content clutter the Doc's page list.** → Mitigation: none needed structurally (they're valid navigational scaffolding, same purpose a `Section` serves in MkDocs' own sidebar); revisit if user feedback shows otherwise. Content stays empty for now (explicit non-goal above).
- **[Risk] Renaming/moving a `Section` orphans its placeholder and creates a new one, losing its ClickUp page history.** → Mitigation: none beyond the existing best-effort archive behavior; documented as a known consequence, consistent with how source-file renames are already handled.
- **[Risk] `parent_page_id` is undocumented, like `archived`.** → Mitigation: same non-fatal posture is not applicable here (unlike `archived`, a failed re-parent on an otherwise-successful page publish would leave content updated but structure stale) — a `parent_page_id` failure is treated as a normal publish failure (raises `PluginError`, aborts the build), not a silent fallback, since there's no safe "leave it flat" degradation that wouldn't itself be a structural surprise.
- **[Trade-off] Sibling order in ClickUp may not match `nav:` order.** → Accepted as a known limitation; no documented API control over `order_index`.

## Migration Plan

No user action required. On the first build after upgrading, any MkDocs site with a non-trivial `nav` hierarchy will have its previously-flat Doc restructured: existing pages get `parent_page_id` set (via the same `sub_title` match already in place, so they update in place rather than duplicate), and new placeholder pages appear for `Section`s without a natural index page. A flat site (no nested `nav`, the common case for small docs) is unaffected — no `Section` means no anchors, same flat output as before.

## Open Questions

None blocking. Placeholder content is deliberately deferred (see Non-Goals).

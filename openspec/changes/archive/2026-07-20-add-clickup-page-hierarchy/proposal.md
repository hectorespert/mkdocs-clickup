## Why

The plugin currently publishes every MkDocs page as a flat ClickUp Page directly under the Doc, discarding the entire `nav` hierarchy MkDocs already computed. This was accepted as a known limitation while the idempotent create/update behavior was being built; that flat publish was a proof of concept, not a contract to preserve. Users browsing the published Doc get a single unstructured list of pages instead of the same structure they navigate in the MkDocs site.

## What Changes

- Pages are nested in ClickUp via `parent_page_id`, mirroring the MkDocs `nav` tree instead of always publishing flat. **BREAKING**: this is the new default behavior, with no opt-in/opt-out configuration — an existing flat Doc will be restructured (pages re-parented, placeholder pages introduced) on the next publish.
- Each `nav` `Section` (a grouping node with no MkDocs page of its own) resolves to an "anchor" used as the `parent_page_id` for its members:
  - If one of the Section's direct children is an `index.md`/`README.md` page, that real page is the anchor.
  - Otherwise, a synthetic placeholder ClickUp Page (empty content, matched across builds by a synthetic `sub_title` derived from the Section's title breadcrumb) is created/updated to act as the anchor.
- `_fetch_existing_pages` is corrected to recursively flatten ClickUp's `GET .../pages` response, which returns a nested tree (each page's children under its own `pages` key) rather than a flat list. Without this fix, any page with a `parent_page_id` would be invisible to the existing `sub_title`-based matching, silently breaking idempotency for nested pages.
- Pages are published in parent-before-child order so a page's resolved anchor already has a ClickUp `page_id` by the time it's created or updated.
- When a page's computed parent changes across builds (e.g. a Section gains or loses its `index.md`), the existing matched page is re-parented via a normal `PUT` with the newly computed `parent_page_id` — no archive/recreate needed.

## Capabilities

### New Capabilities

(none — this extends the existing publishing capability rather than introducing a new one)

### Modified Capabilities

- `clickup-pages-publishing`: replaces the "Flat page creation" requirement (pages SHALL NOT set `parent_page_id`) with nested placement derived from MkDocs `nav`; extends "Existing pages are fetched before publishing" to require a full recursive fetch of the nested page tree, not just top-level pages.

## Impact

- `src/mkdocs_clickup/_internal/plugin.py`: `on_page_content` must additionally capture each page's `nav` parent (`Section`); `on_post_build` gains anchor resolution (real index page or synthetic placeholder), parent-before-child publish ordering, and a corrected recursive tree-flattening fetch.
- `tests/test_plugin.py`: `FakeClickUp` must model the nested-tree `GET` response shape and support `parent_page_id` on create/update.
- `README.md`: the "Pages are flat" known limitation is removed and replaced with a description of the nesting/placeholder behavior.
- `openspec/specs/clickup-pages-publishing/spec.md`: delta spec for the modified requirements above.

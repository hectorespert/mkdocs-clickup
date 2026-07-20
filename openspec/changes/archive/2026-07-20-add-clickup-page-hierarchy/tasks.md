## 1. Capture navigation data per page

- [x] 1.1 Extend `on_page_content` to also capture each page's `nav` parent (`page.parent`, a `Section` or `None`) alongside `(title, markdown)` in `_md_pages`
- [x] 1.2 Add a helper to detect a `Section`'s "index" child: a direct child `Page` whose `src_uri` ends in `index.md` or `README.md`

## 2. Anchor resolution

- [x] 2.1 Implement `anchor(Section)` resolution with per-build memoization: real index-child page if one exists, else a placeholder
- [x] 2.2 Implement synthetic `sub_title` generation for placeholders from the section's title breadcrumb (ancestor titles + own title), using a prefix that cannot collide with a real `src_uri`
- [x] 2.3 Resolve an anchor's own `parent_page_id` from its `Section`'s parent (`Section.parent`), not from the section it anchors, to avoid self-reference

## 3. Fix the existing-pages fetch

- [x] 3.1 Rewrite `_fetch_existing_pages` to recursively flatten the nested `pages` tree returned by `GET .../docs/{doc_id}/pages` (each page's children live under its own `pages` key) into a single flat list, so nested pages are included in the `sub_title` match set exactly like root pages

## 4. Publish ordering and parenting

- [x] 4.1 Rework `on_post_build` to publish anchors (real index pages and placeholders) before the pages/placeholders that depend on them, instead of iterating `_md_pages` in arbitrary order
- [x] 4.2 Include the resolved `parent_page_id` in every create/update request body, so a matched page is re-parented via `PUT` when its computed parent has changed
- [x] 4.3 Include placeholder synthetic `sub_title`s in the current-build identifier set used by the orphan sweep, so a still-needed placeholder is never archived as an orphan right after being created
- [x] 4.4 Confirm a placeholder that's no longer needed (its section gained a real index page, or the section itself disappeared) is archived by the existing best-effort orphan-archival path with no special-casing required

## 5. Tests

- [x] 5.1 Extend `FakeClickUp` to model the nested-tree `GET` response shape (children under a `pages` key, only root pages at the top level) and to accept `parent_page_id` on create/update
- [x] 5.2 Test: a page under a `nav` section with a real `index.md` sibling is published with `parent_page_id` set to that sibling's id, and no placeholder is created
- [x] 5.3 Test: a page under a `nav` section with no index page is published with `parent_page_id` set to a placeholder's id, and the placeholder is created with empty content
- [x] 5.4 Test: the same section's placeholder is matched and updated (not duplicated) across two builds
- [x] 5.5 Test: `_fetch_existing_pages` recursively includes pages nested at multiple depths in its returned list
- [x] 5.6 Test: when a section gains a real index page across builds, previously-placeholder-anchored siblings are re-parented via `PUT` to the new index page, and the old placeholder is archived as an orphan
- [x] 5.7 Test: a top-level page with no enclosing section is still published without a `parent_page_id` (flat sites remain unaffected)
- [x] 5.8 Test: a failed re-parenting `PUT` raises `PluginError` and aborts the build (not treated as best-effort)

## 6. Docs

- [x] 6.1 Update `README.md`: remove the "Pages are flat" known limitation, document the nav-mirroring/placeholder-anchor behavior, and note that sibling order in ClickUp may not match `nav:` order

## 7. Manual verification (real workspace)

- [x] 7.1 Build a throwaway MkDocs site with a nested `nav` (one section with an `index.md`, one section without) and publish; confirm the hierarchy appears correctly in the ClickUp UI, including a placeholder for the index-less section
- [x] 7.2 Add an `index.md` to the previously placeholder-anchored section and rebuild; confirm siblings are re-parented to it and the old placeholder is archived
- [x] 7.3 Remove a nested subsection and rebuild; confirm its pages are archived as orphans same as root-level pages

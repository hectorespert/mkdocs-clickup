## 1. Fetch and match

- [x] 1.1 In `on_post_build`, after validating config/token, fetch existing pages via `GET /api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages`
- [x] 1.2 Build a `sub_title -> page_id` lookup from the fetched pages
- [x] 1.3 For each page in `self._md_pages` (keyed by `src_uri`), resolve whether it has a matching existing `page_id` via the lookup

## 2. Create, update, and archive

- [x] 2.1 When a match exists, `PUT` the existing page: `name` = current title, `sub_title` = `src_uri` (unchanged), `content` = current markdown, `content_format: text/md`
- [x] 2.2 When no match exists, `POST` a new page with the same fields, including `sub_title` = `src_uri`
- [x] 2.3 After processing all current pages, compute orphans: existing pages whose `sub_title` is not among the current build's `src_uri` set
- [x] 2.4 For each orphan, attempt `PUT { archived: true }`; add a code comment noting `archived` is not in ClickUp's documented Edit Page schema (verified empirically, not officially supported)
- [x] 2.5 Wrap the archive attempt so any failure (HTTP error or otherwise) is caught, logged as a warning identifying the orphaned page, and does not raise `PluginError`
- [x] 2.6 Confirm create/update failures (the existing `httpx.HTTPStatusError`/`httpx.HTTPError` handling) are unchanged and still raise `PluginError`, aborting the build

## 3. Tests

- [x] 3.1 Add a mock/fixture for `GET .../docs/{doc_id}/pages` returning a configurable list of existing pages
- [x] 3.2 Test: a current page whose `src_uri` matches an existing page's `sub_title` results in a `PUT` to that page's ID, not a `POST`
- [x] 3.3 Test: a current page with no matching `sub_title` results in a `POST` with `sub_title` set to its `src_uri`
- [x] 3.4 Test: an existing page whose `sub_title` matches no current `src_uri` triggers an archive `PUT` with `archived: true`
- [x] 3.5 Test: an archive `PUT` failure logs a warning and does not raise `PluginError` / does not abort the build
- [x] 3.6 Test: a create or update failure still raises `PluginError` and aborts the build (existing behavior, confirm unchanged)
- [x] 3.7 Replace/rewrite the existing `test_duplicate_pages_on_rebuild` test: two builds of the same page should now result in one `PUT` to the same page on the second build, not two separate pages
- [x] 3.8 Test: two current pages with the same title but different `src_uri` are matched/updated independently, without one clobbering the other

## 4. Docs

- [x] 4.1 Update README.md's "Known limitations" section: remove "every publish always creates new pages"; describe the new match-by-`sub_title`, update-in-place, and best-effort-archive-orphans behavior
- [x] 4.2 Note in README.md that a renamed MkDocs source file is treated as delete-old (archived) + create-new (new `page_id`/URL), and that `archived` is an undocumented ClickUp API behavior relied on best-effort

## 5. Manual verification (real workspace)

- [ ] 5.1 Run `PUBLISH_TO_CLICKUP=1 mkdocs build` twice against a real ClickUp Doc and confirm the second run updates the same ClickUp pages (same `page_id`/URL) instead of creating duplicates
- [ ] 5.2 Remove or rename a page's source file, rebuild, and confirm the old ClickUp page is archived (disappears from the Doc's page list) and, if renamed, a new page appears
- [ ] 5.3 Confirm two pages published with identical titles update independently across builds without cross-matching

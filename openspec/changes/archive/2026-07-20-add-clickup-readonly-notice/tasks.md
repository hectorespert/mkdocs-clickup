## 1. Capture the edit URL

- [x] 1.1 In `on_page_content`, capture `page.edit_url` and store it with the page data in `_md_pages` (extend the stored tuple to include the edit URL).
- [x] 1.2 Update the `_md_pages` type annotation and every place that unpacks it (e.g. `_build_publish_units`, the failure test's manual `_md_pages` assignment).

## 2. Render and prepend the notice

- [x] 2.1 Add a `_notice(edit_url)` helper that returns the fixed blockquote notice (⚠️ + bold lead + overwrite warning), including an `[Edit the source](<edit_url>)` link when `edit_url` is truthy and omitting the link otherwise.
- [x] 2.2 In `_build_publish_units`, prepend the notice to each unit's content: real pages use their captured `edit_url`; placeholder anchors get the linkless notice (and are therefore no longer empty).

## 3. Tests

- [x] 3.1 Test: a published page's content begins with the notice, followed by its own Markdown.
- [x] 3.2 Test: the "Edit the source" link is present when the site has `repo_url`/`edit_uri` (edit URL available).
- [x] 3.3 Test: the notice has no link when there is no edit URL (no repo config) and for a section placeholder anchor.
- [x] 3.4 Test: the notice appears exactly once after two builds (no accumulation).

## 4. Docs & quality gates

- [x] 4.1 Update `README.md`: document the do-not-edit notice, and recommend setting the ClickUp Doc to view-only sharing (manual admin action) for hard prevention, noting the API offers no lock.
- [x] 4.2 Run `python scripts/make check-quality`, `check-types`, `check-docs`, and `test`; fix any findings.

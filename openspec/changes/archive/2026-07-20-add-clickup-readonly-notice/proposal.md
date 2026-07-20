## Why

This project follows doc-as-code: the MkDocs source in the repo is the single source of truth, and ClickUp is meant to be a read-only mirror. But ClickUp Pages are editable by anyone with access, so a well-meaning edit in ClickUp silently drifts from the code and is overwritten on the next publish. A live spike this session confirmed ClickUp's v3 API offers **no** working lock/read-only/permission primitive (the `protected` field isn't settable via Edit Page; `locked`/`read_only`/etc. are ignored; `/sharing` and `/permissions` return 404), so the plugin cannot prevent edits at the platform level. The realistic, plugin-enforceable answer is a visible notice on every page telling people not to edit there.

## What Changes

- Prepend a fixed **do-not-edit notice** to the content of **every** published page, including section placeholder anchors.
- The notice is a Markdown blockquote (⚠️ + bold lead) explaining the page is auto-generated from code and that ClickUp edits are overwritten on the next publish.
- When the page has an edit URL, the notice includes an **"Edit the source"** link to the source file on the repo host (via MkDocs' `page.edit_url`); when there is none (no `repo_url`/`edit_uri`, or a placeholder with no `src_uri`), the notice is emitted without the link (graceful degradation).
- Section **placeholder** anchors, previously empty, now carry the linkless notice.
- The notice is **not configurable** (fixed default; a knob can be added later).
- Because the plugin fully overwrites page content on every publish, the notice is regenerated each build and never accumulates.
- Document the notice in the README, and recommend setting the ClickUp Doc to **view-only sharing** (a manual admin action) for hard prevention, since the API offers no lock.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `clickup-pages-publishing`: add a requirement that every published page (and placeholder) carries a do-not-edit notice, linking to the source when an edit URL is available.

## Impact

- `src/mkdocs_clickup/_internal/plugin.py`: capture `page.edit_url` in `on_page_content` and store it with the page data (`_md_pages`); render and prepend the notice to each publish unit's content in `_build_publish_units`; a small notice helper.
- `tests/test_plugin.py`: notice is prepended; "Edit the source" link present when an edit URL exists and absent otherwise (placeholder / no repo config); notice does not accumulate across rebuilds.
- `README.md`: document the notice and the view-only-sharing recommendation.
- Spec delta on `clickup-pages-publishing`.

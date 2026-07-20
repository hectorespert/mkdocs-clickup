## Context

The plugin publishes MkDocs page content to ClickUp Pages (`_build_publish_units` / `_publish_units` in `src/mkdocs_clickup/_internal/plugin.py`). The project's intent is doc-as-code: the repo is the source of truth and ClickUp is a read-only mirror. Nothing today stops a reader from editing a page in ClickUp; such edits drift from the code and are overwritten on the next publish.

A live spike this session (workspace `90121909276` / doc `2kxuyd0w-532`) established what ClickUp's v3 API does and doesn't allow:
- No settable lock/read-only primitive. `PUT {"protected": true}` returns 200 but re-GET still shows `protected: false`; `locked`/`read_only`/`is_locked`/`editable`/`template` are silently ignored (same "accepts unknown fields" behavior as `archived`/`parent_page_id`, but with no effect).
- `/docs/{id}/sharing` and `/permissions` return 404; the Doc object only exposes `public` (a public-link toggle), not access control.
- Therefore platform-level prevention is not reachable from the plugin.
- A separately useful finding (out of scope here): pages expose `edited_by`/`authors`/`date_edited`, which could power drift *detection* later.

It was also verified live that a Markdown blockquote with a ⚠️ emoji, bold text, and an **absolute** link round-trips through ClickUp's ingestion byte-identical (unlike relative links, which ClickUp drops).

## Goals / Non-Goals

**Goals:**
- Put a clear, visible "do not edit here — edit the source" notice on every published page and placeholder.
- Link the notice to the actual source file when possible, reinforcing where edits belong.
- Keep it simple and idempotent; no new configuration surface.

**Non-Goals:**
- Preventing edits at the ClickUp platform level (the API can't; view-only sharing is a manual admin action, documented only).
- Making the notice configurable or disable-able.
- Drift detection via `edited_by`/`authors` (possible future change).
- Setting ClickUp's `protected` flag or any programmatic sharing/permissions (proven non-functional).
- Sibling ordering via `order_index` (separate thread).

## Decisions

**1. A fixed notice prepended to every page's content.** A Markdown blockquote leading with ⚠️ and a bold "Auto-generated from code — do not edit here.", explaining that ClickUp edits are overwritten on the next publish, followed by a blank line and then the page's own generated Markdown. Alternatives considered: a config-driven/customizable notice (rejected for now — minimalist default, a knob can be added later); appending instead of prepending (rejected — the warning must be seen first).

**2. Link to source via MkDocs' `page.edit_url`.** MkDocs already computes `page.edit_url` from `repo_url` + `edit_uri` + the page's `src_uri`. The plugin captures it in `on_page_content` (alongside the existing title/markdown/section) and, when present, renders an `[Edit the source](<edit_url>)` link in the notice. When absent — no `repo_url`/`edit_uri` configured, or a section placeholder which has no `src_uri` — the notice is emitted without the link. Alternative considered: recomputing the URL ourselves from config (rejected — `page.edit_url` is the canonical, already-correct value).

**3. Placeholders get the linkless notice.** Section placeholder anchors are currently empty; giving them the notice both serves the doc-as-code intent and makes them non-empty (a small side improvement). They have no `src_uri`, so no edit link.

**4. Not configurable.** One fixed default notice, no `mkdocs.yml` option. Keeps the change small and the behavior predictable; a customization/disable knob is a later change if demand appears.

**5. Idempotency comes for free.** The plugin overwrites each page's `content` in full on every publish, so the notice is regenerated each build and never stacks up. No dedup logic needed.

## Risks / Trade-offs

- **A notice is only a social deterrent, not enforcement** → Mitigated by documenting the manual view-only-sharing recommendation for teams that need hard prevention; the API simply offers nothing stronger.
- **ClickUp could change how it renders blockquotes/links** → Low risk; verified live today, and the notice degrades to plain text even if styling changes.
- **The notice slightly inflates every page's content** → Acceptable; it is a few lines and it is the point of the change.
- **`page.edit_url` may be `None`** when the site has no repo config → Handled explicitly (linkless notice), and covered by tests.

## Migration Plan

Purely additive to published content; no config, schema, or matching changes. On the next publish every page (which is overwritten anyway) gains the notice. Rollback is reverting the `plugin.py` change.

## Open Questions

None — the approach, format, link source, configurability, and placeholder behavior were all settled during exploration, and the ClickUp-ingestion and lock-API questions were answered by live spikes.

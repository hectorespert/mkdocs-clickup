## Context

**Current behavior (confirmed by reading the code):**

- `autoclean()` (`preprocess.py:55-75`, `_to_remove`) unconditionally deletes
  every `<img>` and `<svg>` element (and any `<a>` wrapping one) before HTML
  is converted to Markdown. `autoclean` defaults to `True`
  (`config.py:12`), so with default config **every image in the docs
  disappears from the published ClickUp page, silently, with no warning**.
- That single boolean also controls unrelated cruft removal (permalinks,
  Twemoji, tab labels, mkdocstrings labels/descriptions) — bundling "strip
  binary media" with "strip textual noise" under one flag is itself a design
  smell independent of the images question.
- There is currently **no href/src absolutization** anywhere in
  `mkdocs-clickup`. It existed once, in the `mkdocs-llmstxt` ancestor
  (`52e0318`, "Resolve relative links to absolute ones"), and was deliberately
  stripped during the bootstrap rename (`01b9e6d`) as part of reducing the
  plugin to a minimal skeleton — never reintroduced during the actual
  ClickUp-publishing feature work (`ac39bcc`…`c5dcd48`). Even when it
  existed, `_convert_to_absolute_links` only ever rewrote `<a href>` — it
  never touched `<img src>`. So keeping images past `autoclean` today would
  just produce a Markdown `![alt](relative/path.png)` that resolves against
  nothing once pasted into ClickUp's `content` field.

**ClickUp API research (this change's contribution):**

- Official page `developer.clickup.com/docs/docsimportexportlimitations`
  states, verbatim: **"Attachments: Yes, but sizing is not retained"** for
  Docs import/export — confirming images are supported through the same
  `content`/`content_format` mechanism already used for Create/Edit Page.
- There is **no dedicated attachment/upload endpoint for Docs or Pages**. The
  v3 Attachments API (`GET/POST
  .../workspaces/{id}/{entity_type}/{entity_id}/attachments`) only accepts
  `entity_type` values `attachments` (tasks) and `custom_fields` (File-type
  Custom Field) — confirmed via the "Get Attachments" reference page and
  independently via ClickUp community/feedback reports ("no endpoint exists
  to add attachments to a doc via API"). So the only way to get an image into
  a Doc through the API is a Markdown image reference inside `content`
  itself — no binary/multipart transport involved.
- Attachment URLs on ClickUp's own CDN are publicly accessible by default
  (unguessable random path, no login required) unless the workspace enables
  "Private Attachment Links" (off by default) — noted for completeness, not
  load-bearing for the recommended design.

**Live verification performed:** created a real test page
(`workspace 90121909276` / `doc 2kxuyd0w-532` / page `2kxuyd0w-1892`,
`sub_title: __probe_data_uri__`) containing two images: a `data:image/png;base64,...`
URI and a normal remote URL (`github.githubassets.com/.../octocat.png`).
Findings:
- Both round-trip identically through `content_format=text/md` (preserved
  verbatim) and `content_format=text/plain` (both collapse to blank —
  consistent with both being recognized as the same kind of embedded-image
  block, not broken/unparsed text).
- User visually confirmed in the ClickUp UI that **both images render
  correctly** on the page.
- The test page was archived afterward (`archived: true`); content was
  preserved through the archive/unarchive cycle.

## Goals / Non-Goals

**Goals:**
- Establish, with evidence (API + a live visual check, not just docs), which
  approaches to embedding images in a published ClickUp page actually work.
- Compare alternatives on their real trade-offs so a future implementation
  change can pick one without re-researching.

**Non-Goals:**
- Implementing anything in `mkdocs-clickup` yet.
- Solving ClickUp's own product-level limitations (e.g. lost image sizing on
  import) — out of our control.
- Deciding the exact shape of the future `autoclean` config split — flagged
  as a requirement, not designed here.

## Decisions

**Alternatives considered, for resolving an `<img>`'s `src` into something
ClickUp can actually render:**

| Alternative | Mechanism | Main risk | Status |
|---|---|---|---|
| **A. Absolute URL to the deployed site** (`site_url`/`base_url` + relative path) | Revive `<a href>`-style absolutization, extended to `img[src]` (which even the old ancestor logic never covered) | ClickUp fetches at import time → image must already be live at that URL, so `gh-deploy` must run *before* `PUBLISH_TO_CLICKUP` build | **Recommended primary.** Matches the mechanism ClickUp's own docs describe; reuses config that already exists (`site_url`). |
| **B. Raw URL from the source git host** (`raw.githubusercontent.com/...`) | Derive from `repo_url` + branch, akin to existing `edit_url` derivation | Public-repo only; raw-URL shape differs per git host (GitHub/GitLab/Bitbucket) — more bespoke than A | Documented fallback for sites not publicly deployed; not designed in detail here. |
| **C. Piggyback ClickUp's task-attachment API as an image host** | Upload to a throwaway task/Custom Field via the v3 Attachments API, reference the resulting CDN URL in the Doc | Creates orphaned tasks/attachments to clean up; abuses an API for an undocumented purpose; one extra HTTP round-trip per image | **Rejected.** Alternative A already gets the same result without the side effects. |
| **D. Inline `data:` URI** | Base64-encode the image directly into the Markdown `![alt](data:...)` | `content` payload size grows ~33%; interacts with the still-unconfirmed per-page content size limit (README open item) | **Confirmed viable** — live-tested (API + visual). Removes the deploy-ordering risk entirely (no fetch, no dependency on `gh-deploy` timing) at the cost of payload size. |
| **E. Plain-text fallback link** (`📎 [view image](url)`) | No embedding at all, just a link | Materially worse reading experience | Fallback for when A/D can't resolve a URL (e.g. `site_url` unset and no repo host known), not the default. |

**Data URI (D) is no longer a hedge — it's an equally valid primary option to
A**, now that both are confirmed to render identically. The real choice
between A and D is an operational trade-off (build/deploy ordering vs.
payload size), not a "does it work" question.

**Decision: go with D (inline `data:` URI) as the primary approach.** No
dependency on `gh-deploy`/`publish-clickup` ordering, no dependency on the
site being publicly reachable, no new absolutization logic needed for
`img[src]` — a self-contained transform inside `_generate_page_markdown`.
Trade-off accepted: `content` payload size grows per image (~33% over the
image's binary size); see the size-limit risk below, still unresolved.

**Decision: no new `autoclean` config split is needed.** `<img>` removal
simply stops happening in `_to_remove()` (`preprocess.py`), unconditionally —
it was never something that needed to be configurable, it just needed to stop
being wrong. `autoclean` keeps controlling everything else it always did
(permalinks, tab labels, mkdocstrings cruft) unchanged.

**Decision: inline `<svg>` gets the same fate as `<img>`, except for
decorative icons — reusing an existing distinction instead of inventing a
heuristic.** This project's own `mkdocs.yml` renders emoji *and*
`:material-*:`-style icon shortcodes as inline `<svg class="twemoji">` (via
`pymdownx.emoji` with the `to_svg` generator) — and `_to_remove()` already
has a class-based check, `"twemoji" in classes`, independent of the blanket
`tag.name in {"img", "svg"}` check. Separately, `on_page_content`'s `html`
argument is only the page's rendered Markdown content — MkDocs theme chrome
(nav arrows, footer prev/next, edit/copy buttons) is added later by the theme
template and never reaches this pipeline at all. Combined, this means the
*only* inline `<svg>` that would ever reach `_to_remove()` as a decorative,
non-content element is one carrying the `twemoji` class. So: drop the
blanket `tag.name in {"img", "svg"}` rule entirely, keep the `twemoji` class
check as-is. A content SVG (e.g. a hand-authored or tool-generated diagram)
survives untouched; a decorative emoji/icon glyph is still removed, with no
new detection logic. Embedding follows the same shape as a local `<img>`:
serialize the tag's own markup and encode it as
`data:image/svg+xml;base64,...` instead of reading bytes from disk.

## Risks / Trade-offs

- **[Risk] `autoclean`'s image-stripping is bundled with unrelated cruft
  removal** → any fix needs to split that boolean before either A or D can be
  implemented, regardless of which is chosen.
- **[Risk] Alternative A's deploy-ordering dependency** → mitigated by
  documenting the required order (site deploy before ClickUp publish) or by
  preferring D when this ordering can't be guaranteed.
- **[Risk] Alternative D's payload growth, and the content size limit is
  genuinely unknown** → not documented anywhere in ClickUp's developer docs
  (checked the Create/Edit Page reference and the Docs import/export
  limitations page — neither mentions a size or character cap). An empirical
  test would need to write increasingly large payloads to a real Doc to find
  the threshold; the user declined running that against the production
  workspace (`90121909276`/`2kxuyd0w-532`) used so far. **Still open** — must
  be resolved (ideally against a disposable/sandbox workspace, not
  production) before committing to D for image-heavy pages, e.g. API
  reference pages with many screenshots.
- **[Risk] Credential hygiene during this research]** → the live test used a
  real personal token pasted directly into chat; the user was advised to
  rotate it in ClickUp (Settings → Apps → API Token). Not a design risk for
  the plugin itself, but worth noting: any future live-token testing should
  prefer exporting the token directly into the shell rather than pasting it
  into a conversation.

## Migration Plan

N/A — no code or config migration; this change is documentation-only.

## Post-implementation finding: content SVGs are rasterized to PNG, not embedded as SVG

After implementing and publishing real content (the project's own docs,
including a hand-authored inline SVG and a Mermaid-rendered SVG) to the
production ClickUp Doc, two live-verified problems surfaced with embedding
SVG directly, neither anticipated by the original research:

1. **A real bug**: `BeautifulSoup`'s `html.parser` lowercases attribute names
   on parse (confirmed directly: `<svg viewBox="...">` round-trips through
   `str(tag)` as `<svg viewbox="...">`). SVG attribute names are
   case-sensitive (unlike HTML), so this silently corrupted `viewBox`,
   `markerWidth`, `refX`, etc. in every content SVG the original
   `_resolve_images` embedded (it built the `data:` URI from `str(svg_tag)`,
   i.e. from the soup, after case had already been lost at parse time).
2. **A ClickUp-side limitation**: even with correct markup, ClickUp failed to
   render a large (~20KB), `<style>`-heavy SVG - specifically Mermaid's own
   output (fonts, `@keyframes` animations, mermaid.js's generated CSS
   classes) - live-verified in the real Doc (showed as literal unrendered
   Markdown text, not an image).

Both were caught by publishing the plugin's own real documentation (not just
synthetic test fixtures) and having a human visually inspect the result in
ClickUp - the API-only round-trip tests from the original research (which
only ever used PNG data URIs) would not have caught either issue.

**Resolution**: stopped embedding SVG at all. Content SVGs are now rasterized
to PNG via `resvg_py.svg_to_bytes()`, operating on the *raw HTML string*
before any BeautifulSoup parsing happens - this sidesteps the case-mangling
bug entirely (resvg receives pristine, unmodified markup) and sidesteps
ClickUp's SVG rendering limitation (the embedded artifact is a PNG, a format
already proven reliable across every prior live test). `resvg_py` moved from
"transitively pulled in by the optional `mermaid` extra" to a **required base
dependency** of `mkdocs-clickup`, since content-SVG support belongs to the
core capability, not the optional Mermaid one.

## Open Questions

- ~~Default to A, D, or a hybrid?~~ Resolved: D chosen as the primary
  approach (see Decisions).
- ~~Should the `autoclean` split be its own preliminary change?~~ Resolved:
  no split needed - `<img>`/content-`<svg>` removal was simply dropped from
  `_to_remove()` unconditionally.
- **Still unresolved:** `content`'s maximum size/length. Needs an empirical
  check against a disposable/sandbox ClickUp workspace (not production)
  before shipping D for image-heavy pages.

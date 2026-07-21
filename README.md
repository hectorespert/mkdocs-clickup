# mkdocs-clickup

[![ci](https://github.com/hectorespert/mkdocs-clickup/workflows/ci/badge.svg)](https://github.com/hectorespert/mkdocs-clickup/actions?query=workflow%3Aci)
[![documentation](https://img.shields.io/badge/docs-mkdocs-708FCC.svg?style=flat)](https://hectorespert.github.io/mkdocs-clickup/)
[![pypi version](https://img.shields.io/pypi/v/mkdocs-clickup.svg)](https://pypi.org/project/mkdocs-clickup/)

MkDocs plugin to publish documentation to [ClickUp Pages](https://clickup.com/features/docs).

This project is a fork of [mkdocs-llmstxt](https://github.com/pawamoy/mkdocs-llmstxt) by Timothée Mazzucotelli, reusing its HTML-to-Markdown conversion pipeline as a foundation.

## Installation

```bash
pip install mkdocs-clickup
```

## Usage

Enable the plugin in `mkdocs.yml`, pointing it at an existing ClickUp Workspace and Doc:

```yaml title="mkdocs.yml"
plugins:
- clickup:
    workspace_id: "9010000000"
    doc_id: "abc123"
```

Publishing is opt-in per invocation, via the `PUBLISH_TO_CLICKUP` environment variable, and requires a `CLICKUP_API_TOKEN`:

```bash
PUBLISH_TO_CLICKUP=1 CLICKUP_API_TOKEN=pk_... mkdocs build
```

Without `PUBLISH_TO_CLICKUP` set, the plugin does nothing — `mkdocs build`, `mkdocs serve`, and `mkdocs gh-deploy` all fire the same build hooks internally, and publishing unconditionally would create ClickUp pages on every local save during development. `mkdocs gh-deploy` also runs through this gate, so `PUBLISH_TO_CLICKUP=1 mkdocs gh-deploy` publishes to ClickUp in addition to deploying to GitHub Pages.

### Known limitations

- **Publishing is idempotent, keyed by page path.** Before creating or updating any page, the plugin fetches the Doc's existing pages and matches them against the current build's pages using ClickUp's `sub_title` field, which holds the MkDocs page's source path (not the page title, which MkDocs doesn't guarantee to be unique). A match is updated in place (same ClickUp page, same URL); no match is created. A previously-published page whose source file was renamed or deleted (no current match) is archived — removed from the Doc's page listing — on a best-effort basis: `archived` is not part of ClickUp's documented Edit Page API, so if archiving fails or stops working, the plugin logs a warning and continues rather than failing the build; the page simply stays visible. A renamed source file is treated as delete-old (archived) + create-new, so it gets a new ClickUp page and URL rather than keeping the old one.
- **Transient API errors are retried.** ClickUp's v3 API can intermittently time out or return `5xx`/`429` under the plugin's per-page request burst. The plugin uses an explicit 30s request timeout and retries transient failures (timeouts, connection errors, and `429`/`500`/`502`/`503`/`504` responses) up to 5 times with exponential backoff and jitter, honoring `Retry-After` on rate limits. A create (`POST`) whose response is lost but which ClickUp may already have committed is reconciled by re-matching on `sub_title` before retrying, so retries never create duplicate pages. A failure that survives all 5 attempts still fails the build.
- **Published pages carry a "do not edit" notice.** The docs are generated from the source repo (the source of truth) and every page's content is overwritten on each publish, so each ClickUp page — and each section placeholder — is prefixed with a short notice telling readers not to edit it in ClickUp, with an "Edit the source" link to the file on your repo host when `repo_url`/`edit_uri` are set. ClickUp's API exposes no way to lock a page or make it read-only (verified against a real workspace: `protected` isn't settable, and there are no sharing/permission endpoints), so the notice is a deterrent, not enforcement. For hard prevention, share the ClickUp Doc as **view-only** with your workspace from the ClickUp UI (a manual admin action) — that leaves only the publishing token able to write, while everyone else sees a faithful mirror of the code.
- **Pages mirror the MkDocs navigation hierarchy.** Each `nav` section is anchored by a real page (its direct `index.md`/`README.md` child, if it has one) or, if it has none, by an empty placeholder page created just to hold that spot in the tree — both cases use ClickUp's `parent_page_id` (undocumented in ClickUp's public API reference, like `archived`, but verified to work reliably, including re-parenting an existing page when its position in the hierarchy changes between builds). This is the default behavior; there's no configuration to keep pages flat. A flat site (no nested `nav` sections) publishes exactly as before. Sibling order within ClickUp may not match your `nav:` order — there's no documented API control over it.
- **Links are published as-authored.** Relative links between pages are not rewritten in any way; they are not resolved against ClickUp's own addressing model. Confirmed against a real ClickUp workspace: ClickUp itself parses submitted Markdown into its own document model on ingestion, and a relative link pointing at a target it can't resolve (e.g. `other.md`) is normalized away, keeping only the link's text — this is ClickUp's own behavior, not something the plugin does.
- **Every page MkDocs builds is published** — there's no page-selection or filtering configuration yet.
- **Images are embedded inline, not linked.** Local `<img>` sources are read from disk and embedded as `data:` URIs directly in the published Markdown — no dependency on the site being deployed or `site_url` being set. Already-absolute/remote image URLs are published unchanged. Decorative icons (emoji and `:material-*:`-style shortcodes) are still stripped, same as before; a broken local image reference fails the build rather than publishing silently-missing content.
- **Content SVGs are rasterized to PNG, not embedded as SVG.** An inline `<svg>` diagram is rasterized locally (via `resvg`) and embedded as a `data:image/png` URI. This isn't a stylistic choice: live-verified against a real ClickUp workspace, an SVG survives round-tripping through the plugin's HTML parser with case-sensitive attributes silently corrupted (`viewBox` → `viewbox`), and separately, ClickUp itself was found to fail rendering a large, `<style>`-heavy SVG even when well-formed. PNG sidesteps both.
- **Mermaid diagrams are rendered locally, as an opt-in extra.** A `` ```mermaid `` fenced code block (as produced by mkdocs-material's diagram support) is rendered to a PNG image at build time (same reasoning as above — Mermaid's own SVG output failed to render in ClickUp) and embedded the same way as any other content image — ClickUp does not render Mermaid source submitted through its Page API, even though its own editor can render Mermaid pasted manually. This requires the `mermaid` extra:

  ```bash
  pip install "mkdocs-clickup[mermaid]"
  ```

  Without it installed, or if a specific diagram's syntax can't be rendered, that block is published as a plain fenced code block instead — a renderer limitation, not a build failure.

## Releasing

Releases are cut **locally**, driven by the `duty`-based task runner (`python scripts/make <task>`). There is no version string to bump in source: the package version is derived at build time from Git tags (`scripts/get_version.py`), falling back to the latest `CHANGELOG.md` heading. Cutting a release therefore comes down to updating the changelog, then creating and pushing a tag.

**Prerequisites**

- A clean working tree on `main` with push access to the repository.
- PyPI credentials available to `twine` (e.g. an API token in `~/.pypirc`, or `TWINE_USERNAME=__token__` / `TWINE_PASSWORD=pypi-...` in the environment) — the release publishes to PyPI from your machine.

**Steps**

1. **Update the changelog** — regenerate `CHANGELOG.md` from the commit history (uses `git-changelog`, so commits must follow the Angular convention) and pick the version bump:

   ```bash
   python scripts/make changelog bump=minor   # or: major | patch | <explicit-version>
   ```

   Review the generated `CHANGELOG.md` and commit any manual touch-ups you need before releasing.

2. **Release** — this single task does everything else:

   ```bash
   python scripts/make release 0.6.0
   ```

   It runs locally and, in order:
   - stages `pyproject.toml` + `CHANGELOG.md` and commits them as `chore: Prepare release 0.6.0`;
   - creates an annotated Git tag `0.6.0`;
   - pushes the commit and the tag (`git push` + `git push --tags`);
   - then, via its post-hooks, builds the source and wheel distributions (`build`) and uploads them to PyPI (`publish`, `twine upload --skip-existing`).

3. **GitHub Actions (automated)** — pushing the tag triggers `.github/workflows/release.yml`, which:
   - generates release notes with `git-changelog --release-notes` and creates the corresponding GitHub Release;
   - builds the docs and publishes them to ClickUp (`PUBLISH_TO_CLICKUP=1 mkdocs build`), targeting the release Doc configured in `mkdocs.yml`.

Docs are no longer deployed to GitHub Pages as part of a release; ClickUp is now the published destination. `python scripts/make docs-deploy` (`mkdocs gh-deploy --force`) still exists as a manual, opt-in command if you need it.

## ClickUp API research

Findings from a first research pass on the ClickUp API, specifically the Docs/Pages
endpoints (public API v3, launched May 2024), to ground the first real OpenSpec
change ("publish to ClickUp Pages") in facts instead of guesses. This is a
research note, not a spec — it will be cited from that change's `proposal.md`/
`design.md` once written.

**Caveat:** these findings come from ClickUp's public developer docs and
third-party summaries (fetched via web search, not verified against a live
token/workspace). A few details below are flagged as needing confirmation with
a real API key before the implementation change starts.

### 1. Authentication

- **Personal token** (`pk_...`): sent as `Authorization: {personal_token}` (no
  `Bearer` prefix). Never expires. Simplest option for a first implementation —
  the plugin config would just take a token string.
- **OAuth2** (authorization-code grant): for multi-user/multi-workspace apps.
  Authorization URL `https://app.clickup.com/api`, token URL
  `https://api.clickup.com/api/v2/oauth/token`. Access token sent as
  `Authorization: Bearer {access_token}` and currently does not expire (per
  ClickUp's docs, "subject to change").
- For a MkDocs build-time plugin (not a multi-user app), a personal token is
  almost certainly the right fit — no interactive OAuth flow makes sense in a
  CI/build context.
- Rate limits (see [Rate Limits](https://developer.clickup.com/docs/rate-limits)):
  100 req/min (Free/Unlimited/Business), 1,000 req/min (Business Plus), 10,000
  req/min (Enterprise) — per token. Exceeding returns HTTP 429 with
  `X-RateLimit-Limit`/`X-RateLimit-Remaining`/`X-RateLimit-Reset` headers. A
  large doc site built on a low-tier workspace could plausibly hit this if
  every page is a separate create/update call with no batching — worth a
  backoff/retry-on-429 design point.

### 2. Page hierarchy model

- Top-level container is a **Doc**, created inside a Workspace with a required
  `parent` (Space, Folder, or List — exact field shape e.g. `{id, type}` not
  confirmed from docs alone, needs a live-token check). A Doc is NOT
  auto-created; the plugin will need to create one, or accept an existing
  Doc ID via config.
- **Pages** live inside a Doc and can nest via `parent_page_id` (omitted for
  root-level pages). The "Fetch Pages" endpoint supports a `max_page_depth`
  query param (`-1` = unlimited), confirming nesting depth is not hard-capped
  in a documented way, but the exact response shape for parent/child
  relationships wasn't visible in the fetched docs — needs a live check too.
- This maps reasonably well onto MkDocs' `nav` tree (page → sub-page), but the
  exact mapping (does every `nav` entry with children need its own ClickUp
  Doc, or one Doc with nested Pages for the whole site?) is a design decision
  for the real proposal, not something the API dictates.

### 3. Create/update endpoints (confirmed via official reference pages)

| Action | Method | Path |
|---|---|---|
| Create Doc | `POST` | `/api/v3/workspaces/{workspace_id}/docs` |
| Create Page | `POST` | `/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages` |
| Fetch Doc's Pages | `GET` | `/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages` |
| Update Page | `PUT` | `/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages/{page_id}` |

- **Create Page** body: `name` (string), `content` (string), `content_format`
  (`text/md` default, or `text/plain`), optional `parent_page_id`,
  `sub_title`. Returns HTTP 201; whether the body includes the new page's ID
  wasn't confirmed from docs excerpts — needs a live check (this matters a lot
  for §5 below).
- **Update Page** body: `name`, `content`, `content_format`
  (`text/md`/`text/plain`), and **`content_edit_mode`**: `replace` (default),
  `append`, or `prepend`. This is genuinely idempotent by page ID — no
  delete+recreate needed to update content.
- **Create Doc** body: `name`, `parent` (object), `visibility`
  (`PUBLIC`/`PRIVATE`/`PERSONAL`/`HIDDEN`), optional `create_page` (bool,
  defaults `true` — so creating a Doc auto-creates a first page unless
  disabled).

### 4. Content format — the highest-impact unknown, now resolved

**ClickUp's Page API accepts plain Markdown directly** (`content_format:
"text/md"`, which is also the default) — not a proprietary block-based
rich-text JSON as originally feared. This is the best possible outcome for
reuse: the existing `_generate_page_markdown()` pipeline in
`src/mkdocs_clickup/_internal/plugin.py` (autoclean → user preprocess → link
conversion → markdownify → mdformat) can very plausibly feed its output
**directly** into the `content` field of Create/Update Page calls, with no
second conversion stage needed. This substantially de-risks the real
implementation change.

`text/plain` is also accepted as a fallback/simpler mode.

### 5. Identifying existing pages for updates

- Pages have a stable `page_id`, and the Update Page endpoint updates by that
  ID — so a "create once, update thereafter" flow is supported *if* the
  plugin can persist the mapping from an MkDocs page (`src_uri`) to its
  ClickUp `page_id` across builds (e.g. a local JSON/YAML sidecar file
  checked into the docs repo, since there's nothing else stable to key on
  between MkDocs and ClickUp).
- Open item needing a live-token check: does the Create Page response body
  actually return the new `page_id`? (Needed to populate that mapping file
  after a first create.) The Fetch Doc's Pages endpoint (§3) is the fallback
  if not — look up by page `name`/`sub_title` to recover IDs if the mapping
  file is lost or a page was created out-of-band.

### 6. Rate limits and batching

Covered in §1. No batch/bulk page-create endpoint was found in the docs
excerpts fetched — each page is one API call. For large doc sites this means
build time scales linearly with page count and the plugin should implement
basic 429 backoff (respecting `X-RateLimit-Reset`) rather than assuming
unlimited throughput.

### 7. Workspace/Space prerequisites

- The **Workspace** itself is always a pre-existing top-level ClickUp account
  construct — never created via this API. `GET /api/v2/team` ("Get
  Authorized Workspaces") lists the workspaces a given token can access, so
  the plugin config will need at least a `workspace_id` (obtainable via this
  endpoint) plus a token.
- Creating a **Doc** requires a `parent` (Space, Folder, or List) that must
  already exist — the API does not appear to provision Spaces/Folders/Lists
  from scratch as part of Doc creation. So plugin config will likely need
  either an existing Doc ID (simplest — publish into an already-created Doc)
  or a `parent` reference (Space/Folder/List ID) to create a new Doc under.

### 8. Image support — resolved, live-verified

There is **no attachment/upload endpoint for Docs or Pages**. The v3
Attachments API (`GET/POST
.../workspaces/{id}/{entity_type}/{entity_id}/attachments`) only accepts
`entity_type` values `attachments` (tasks) and `custom_fields` (File-type
Custom Field) — confirmed via the "Get Attachments" reference page and
independently via ClickUp community/feedback reports ("no endpoint exists to
add attachments to a doc via API").

The official Docs import/export limitations page
(`developer.clickup.com/docs/docsimportexportlimitations`) states, verbatim:
**"Attachments: Yes, but sizing is not retained"** — confirming images are
supported through the same `content`/`content_format` mechanism already used
for Create/Edit Page: a plain Markdown image reference, `![alt](url)`.

Live-verified against a real ClickUp workspace (Create/Edit Page API, not
just the manual editor): a `data:image/png;base64,...` URI and a normal
remote image URL round-trip **identically** through `content_format=text/md`
(preserved verbatim) and `content_format=text/plain` (both collapse to
blank — consistent with both being recognized as embedded-image blocks, not
broken text), and both render correctly when viewed in the ClickUp UI. So
either a `data:` URI or an absolute URL works; a `data:` URI additionally
removes any dependency on the site being deployed/publicly reachable before
publishing, at the cost of inflating `content`'s size (~33% over the image's
own byte size) — see item 4 below.

Also confirmed (separately): passing a `` ```mermaid `` fenced code block
through `content` renders as a plain code block, not a live diagram — Mermaid
rendering via the Create/Edit Page API path is not supported, even though
ClickUp's own editor can render Mermaid when pasted manually into a
different, UI-only block type.

**Later, live-verified against the plugin's own real documentation** (not
just synthetic probes): `data:image/svg+xml` does **not** reliably render.
A large, `<style>`-heavy SVG (Mermaid's own output) showed as literal
unrendered Markdown text. Separately, a hand-authored inline SVG also failed
to render — traced to a plugin-side bug, not a ClickUp one: `BeautifulSoup`'s
`html.parser` lowercases attribute names on parse, silently corrupting
case-sensitive SVG attributes (`viewBox` → `viewbox`) before they ever reach
ClickUp. Small, simple SVGs (e.g. a single `<rect>`, or a small shape with
`<defs>`/`<marker>`/`<text>`) rendered fine in isolated tests, so this may be
survivable-complexity-dependent rather than an outright SVG ban — but since
PNG has rendered correctly in **every** test run against this API, the
plugin now rasterizes all SVG content (Mermaid diagrams and hand-authored
content SVGs alike) to PNG before embedding, rather than chasing exactly
which SVG constructs ClickUp's importer tolerates.

### Open items needing a live-token check before implementation

1. Exact shape of the `parent` object on Create Doc (`{id, type}` or similar).
2. Whether Create Page's response body includes the new `page_id`.
3. Exact response shape of "Fetch Pages belonging to a Doc" for parent/child
   nesting (to confirm the hierarchy model assumed in §2).
4. Whether there's any size/length limit on `content` per page. Relevant for
   very long generated Markdown pages (e.g. API reference pages), and now
   also for image-heavy pages using the `data:` URI approach from §8 — still
   unresolved; a build-time test would need to write increasingly large
   payloads to a real Doc to find the threshold, ideally against a
   disposable/sandbox workspace rather than production.

### Sources

- [Get Started with the ClickUp API](https://developer.clickup.com/docs/Getting%20Started)
- [Authentication](https://developer.clickup.com/docs/authentication)
- [Rate Limits](https://developer.clickup.com/docs/rate-limits)
- [Create a Page](https://developer.clickup.com/reference/createpagepublic)
- [Edit a Page](https://developer.clickup.com/reference/editpagepublic)
- [Create a Doc](https://developer.clickup.com/reference/createdocpublic)
- [Fetch Pages belonging to a Doc](https://developer.clickup.com/reference/getdocpagespublic)
- [Get Authorized Teams (Workspaces)](https://developer.clickup.com/reference/getauthorizedteams)
- [Access and edit Docs via the API (feedback/roadmap post, context on the v3 Docs API launch)](https://feedback.clickup.com/public-api/p/access-and-edit-docs-via-the-api)

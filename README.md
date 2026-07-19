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

### Known limitations (v1)

- **Every publish always creates new pages.** There is no update-in-place and no persisted mapping between MkDocs pages and ClickUp pages — running the same build twice creates two separate pages in ClickUp. This is a deliberate, accepted limitation of this first version, not a bug.
- **Pages are flat.** All pages are created directly under the configured Doc, with no nesting — the MkDocs navigation hierarchy is not reflected in ClickUp.
- **Links are published as-authored.** Relative links between pages are not rewritten in any way; they are not resolved against ClickUp's own addressing model. Confirmed against a real ClickUp workspace: ClickUp itself parses submitted Markdown into its own document model on ingestion, and a relative link pointing at a target it can't resolve (e.g. `other.md`) is normalized away, keeping only the link's text — this is ClickUp's own behavior, not something the plugin does.
- **Every page MkDocs builds is published** — there's no page-selection or filtering configuration yet.

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

### Open items needing a live-token check before implementation

1. Exact shape of the `parent` object on Create Doc (`{id, type}` or similar).
2. Whether Create Page's response body includes the new `page_id`.
3. Exact response shape of "Fetch Pages belonging to a Doc" for parent/child
   nesting (to confirm the hierarchy model assumed in §2).
4. Whether there's any size/length limit on `content` per page (relevant for
   very long generated Markdown pages, e.g. API reference pages).

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

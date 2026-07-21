## Why

Today, every image in a MkDocs site is silently dropped before publishing to
ClickUp: `autoclean()` (enabled by default) unconditionally removes every
`<img>`/`<svg>` element, a behavior inherited byte-for-byte from the
`mkdocs-llmstxt` ancestor (where it made sense for an `/llms.txt` file) and
never revisited once the project pivoted to publishing full documentation
pages. Before touching code, we researched whether ClickUp's Docs/Pages API
can even render images at all, and, if so, which mechanism actually works —
grounding the design in a live test against a real ClickUp workspace instead
of assumptions.

## What Changes

- `autoclean()` (`preprocess.py`) stops unconditionally removing `<img>` and
  most inline `<svg>` elements. `<img>` elements are always preserved; inline
  `<svg>` elements are preserved *unless* they match the existing decorative
  `twemoji`-class check (emoji and `:material-*:`-style icon shortcodes,
  rendered as inline SVG by this project's `pymdownx.emoji` `to_svg`
  configuration) — no new `autoclean` config option is introduced.
- For an `<img>` whose `src` resolves to a local file in the built site (not
  an already-absolute external URL), and for a preserved inline `<svg>`, the
  plugin reads/serializes the bytes and rewrites the image into a
  `data:<mime>;base64,...` URI embedded directly in the published Markdown.
  Already-absolute/remote `<img src>` values are left untouched.
- A local image or inline SVG that can't be resolved/read SHALL raise an
  error that aborts the build (consistent with the capability's existing
  "Publish failures abort the build" philosophy), rather than silently
  publishing broken content.
- Embedding does not depend on `site_url` or the site having been deployed —
  consistent with the existing "Links are published as-authored" requirement
  in the same capability, which already avoids that dependency for links.
- **Not resolved by this change:** the maximum size of ClickUp's `content`
  field is undocumented, and empirically testing it was declined against the
  production workspace used for research. This remains an open risk for
  image-heavy pages; see `design.md`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `clickup-pages-publishing`: adds requirements for preserving and embedding
  images and content SVGs as inline data URIs when generating the Markdown
  published to ClickUp.

## Impact

- `src/mkdocs_clickup/_internal/preprocess.py`: `_to_remove()` no longer
  matches `<img>` or (non-decorative) `<svg>`.
- `src/mkdocs_clickup/_internal/plugin.py`: `_generate_page_markdown` (or a
  new step in its pipeline) resolves local image/SVG sources to `data:` URIs.
- New tests covering: images/content-SVGs surviving `autoclean`, decorative
  SVG icons still removed, local images/SVGs embedded as data URIs, remote
  image URLs left untouched, and a build error on an unreadable local image.
- README's "ClickUp API research" section gets updated with the confirmed
  findings (no attachment/upload endpoint for Docs; images work via a
  Markdown `data:` URI or absolute URL, live-verified against a real
  workspace).

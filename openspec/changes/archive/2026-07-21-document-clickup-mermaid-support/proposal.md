## Why

MkDocs sites (notably via mkdocs-material's built-in diagram support) commonly
render Mermaid diagrams client-side: the page's build-time HTML contains only
the raw Mermaid diagram source inside a code block, with the actual diagram
drawn later by JavaScript in the reader's browser. Today, `mkdocs-clickup`
has no special handling for this — a Mermaid code block would either get
silently mislabeled (losing its `mermaid` language tag, since the plugin only
recognizes `language-*`-prefixed classes) or, once the sibling
`document-clickup-image-support` change lands, still just publish as an inert
code block, never as a diagram. Before designing a fix, we researched whether
ClickUp can render Mermaid at all through the same publishing path this
plugin already uses.

## What Changes

- A fenced code block rendered by mkdocs-material's Mermaid support (bare
  `mermaid` class, per `pymdownx.superfences` custom fence config) is
  rendered to an image **locally, at build time** — no external rendering
  service — using a pure-Python renderer (`mermaidx` or `merm`; final pick is
  an implementation task), and embedded via the same `data:` URI mechanism
  designed in `document-clickup-image-support`.
- Passing the fence through untouched to ClickUp was tried and **confirmed
  not to work**: content sent through the Create/Edit Page API's
  `content`/`content_format: text/md` renders a Mermaid fence as a plain code
  block, not a diagram (ClickUp's own live-Mermaid support appears to be a
  distinct, UI-only editor block, not reachable through the generic
  page-content import path this plugin uses).
- Rendering happens locally specifically to avoid depending on an external
  service's (e.g. `mermaid.ink`) uptime for every build that publishes to
  ClickUp.
- When local rendering fails (unsupported diagram syntax, a diagram type the
  chosen library doesn't handle), the plugin SHALL fall back to publishing
  the fenced source as a plain code block — today's behavior for that
  diagram, not a build failure.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `clickup-pages-publishing`: adds requirements for rendering Mermaid code
  blocks to an image locally at build time and embedding them the same way
  as other content images/SVGs.

## Impact

- `src/mkdocs_clickup/_internal/plugin.py` / `preprocess.py`: detect a fenced
  code block carrying the bare `mermaid` class, render it locally to an
  image, and route it through the `document-clickup-image-support` embedding
  step; on render failure, leave the fence as a plain code block.
- New third-party dependency on a Mermaid-rendering Python library (exact
  choice — `mermaidx` vs. `merm` — is an implementation task, not decided
  here); whether it's a required or optional (`extras`) dependency is also an
  implementation task.
- New tests covering: a renderable Mermaid fence becomes an embedded image;
  an unrenderable one falls back to a plain code block without aborting the
  build.
- Depends on `document-clickup-image-support` landing first (or alongside),
  since this capability's implementation reuses its embedding mechanism
  rather than duplicating it.

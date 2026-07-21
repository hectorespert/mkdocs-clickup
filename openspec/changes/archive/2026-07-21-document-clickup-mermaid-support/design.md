## Context

**How Mermaid diagrams reach a MkDocs page's build-time HTML:** with
mkdocs-material's documented setup —

```yaml
markdown_extensions:
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
```

— a `` ```mermaid `` fence becomes `<pre><code class="mermaid">...</code></pre>`
at build time, containing the **raw Mermaid diagram source as text**. The
actual diagram (an SVG) is only drawn later, client-side, by `mermaid.js`
running in the reader's browser after page load. `on_page_content` never
sees a rendered image for this case — no plugin hook in this pipeline does.

**The existing gap this creates in `mkdocs-clickup`:** `_language_callback`
(`plugin.py`) only recognizes classes prefixed `language-` when picking a
fenced code block's language for the generated Markdown. mkdocs-material's
mermaid fence uses the bare class `mermaid`, not `language-mermaid` — so
today, a Mermaid block would be emitted as an untagged code fence, losing the
one signal (`` ```mermaid ``) that would let any downstream renderer
recognize it as a diagram at all.

**Live verification performed:** reused the same test page from the images
research (`workspace 90121909276` / `doc 2kxuyd0w-532` / page
`2kxuyd0w-1892`). Sent, via the Edit Page API (`content_format: text/md`), a
page whose `content` included:

```
​```mermaid
graph TD;
    A[MkDocs page] --> B[mkdocs-clickup plugin];
    B --> C[ClickUp Page];
​```
```

- `GET` confirmed the fence round-tripped through `content` byte-for-byte.
- User visually confirmed in the ClickUp UI: **it renders as a plain code
  block, not a diagram.**

This contradicts what ClickUp's own product blog describes ("paste your
Mermaid code into a Markdown block and it renders instantly") — that
description almost certainly refers to a distinct, UI-only block type
reachable via the editor's `/Markdown` slash command, not the generic
page-`content` import path this plugin's Create/Edit Page calls use. The two
are evidently backed by different rendering logic in ClickUp, and only the
UI-block one currently executes Mermaid.

## Goals / Non-Goals

**Goals:**
- Establish, with a live test (not assumptions or marketing copy), whether
  ClickUp renders Mermaid source sent through the same API path this plugin
  already uses.
- Identify the resulting implementation direction for a future change.

**Non-Goals:**
- Implementing anything in `mkdocs-clickup` yet.
- Solving diagram rendering for a hypothetical MkDocs setup that already
  pre-renders Mermaid to a real `<svg>`/`<img>` at build time — such a case
  would already fall under the plain content-SVG/image handling designed in
  `document-clickup-image-support`, with no extra work needed. **Correction:**
  an earlier draft of this document cited `mkdocs-mermaid2-plugin` as an
  example of such a pre-rendering setup. That's wrong — checked directly:
  `mkdocs-mermaid2-plugin` is client-side rendering too, same as
  mkdocs-material's native support. It converts a diagram fence into a
  `<div>` holding the raw diagram text, with mermaid.js drawing it in the
  browser; it does not produce an image at build time either. No known
  MkDocs-ecosystem plugin was found that pre-renders Mermaid to a static
  image at build time — this capability has to do that itself.

## Decisions

**Confirmed: passing the fence through untouched does not work.** Ruled out
as a viable path — no further investigation needed here, the negative result
is conclusive for the `content`/`content_format: text/md` API path.

**Direction: pre-render to an image at build time, then reuse the
`data:` URI embedding mechanism from `document-clickup-image-support`.**
Rejected the hosted-service option (`mermaid.ink`) explicitly: publishing to
ClickUp should not gain a new runtime dependency on an unrelated third-party
service's uptime just to render a diagram. Rendering must happen locally,
at build time, using only what the build machine already has (or what this
plugin installs as a dependency) — no network call to a diagram-rendering
service.

Candidates researched for local rendering, from the same ecosystem search
that turned up `mermaid.ink`:

| Option | Mechanism | Note |
|---|---|---|
| `mermaid-cli` (`mmdc`, official) | Node.js + Puppeteer, spins up real headless Chromium, runs actual `mermaid.js` | Fully faithful (it's the real renderer), but pulls a Node.js/Chromium toolchain (~170MB+) into a Python project's build |
| `mermaid-cli-python` | Same idea, Python-orchestrated, needs Playwright | Same browser weight, different orchestration language |
| `mermaidx` | `pip install mermaidx` | Initial web research claimed this used PhantomJS - **wrong, corrected below after actually installing and inspecting it** |
| `merm` | `pip install merm`, a from-scratch pure-Python reimplementation of Mermaid's diagram layout | Diagram-type coverage and maintenance were unverified claims until tried directly, below |

**Correction after hands-on trial (not just web search):** installed both via
`uv run --with mermaidx --with merm` (ephemeral, no project changes) and
inspected their actual package metadata instead of trusting the earlier
search summary. Findings:

- **`mermaidx`** (v0.9.3, source at `github.com/mohammadraziei/mermaidx`) does
  **not** use PhantomJS. Its own metadata: "Renders diagrams to SVG/PNG/PDF
  using an embedded QuickJS engine and resvg" — `quickjs-ng` (a small,
  actively-maintained embeddable JS engine binding) runs mermaid.js's actual
  logic, and `resvg-py` (Rust-based) rasterizes SVG when needed. No Node.js,
  no npm, no browser, no Puppeteer, no PhantomJS. The earlier PhantomJS claim
  in this document was wrong — an artifact of an outdated/inaccurate web
  search summary, not of anything actually in the current package.
- **`merm`** is at a much earlier version (0.1.5) with no `Project-URL`
  metadata at all (no visible source repository link) — a materially weaker
  maintenance signal than `mermaidx`.
- **Trial run** against all four representative diagram types
  (flowchart, sequence, class, gantt): **both libraries rendered all four
  successfully**, no failures. `mermaidx`'s output SVGs were 3-9x larger than
  `merm`'s for the same input, consistent with `mermaidx` running the real
  mermaid.js renderer (full styling/fonts/layout) versus `merm`'s simpler,
  from-scratch layout engine.

**Decision: use `mermaidx`.** Since it runs mermaid.js's own logic (via
QuickJS) rather than reimplementing diagram layout from scratch, it inherits
mermaid.js's actual syntax coverage and fidelity, without needing Node.js, a
browser, or PhantomJS — the exact property this design wanted, just achieved
differently than the initial (incorrect) research suggested. `merm` was a
reasonable fallback candidate but loses on both maintenance signal and
rendering fidelity now that `mermaidx`'s real mechanism is understood.

**Decision: a local rendering failure falls back to publishing the raw fence
as plain code, rather than aborting the build.** Deliberately inconsistent
with the unreadable-local-image behavior in `document-clickup-image-support`
(which aborts): a broken/missing image file is almost always a real content
error, but a Mermaid diagram `mermaidx` can't handle (unsupported syntax, a
newer diagram type) is a renderer *limitation*, not necessarily an authoring
mistake — failing the whole build over that would be too harsh. The fenced
source still gets published (today's behavior, degraded but not broken), just
without becoming a rendered diagram.

**Decision: `mermaidx` is an optional extra** (`mkdocs-clickup[mermaid]`),
not a required dependency. It pulls in `quickjs-ng` as a native dependency -
a real (if much lighter than Node.js/Chromium) footprint that sites without
any Mermaid diagrams shouldn't be forced to install. (`resvg-py`, `mermaidx`'s
other native dependency, became a required *base* dependency of
`mkdocs-clickup` anyway - see the PNG-rasterization finding below - so it no
longer adds anything extra-only.)

**Post-implementation finding: Mermaid diagrams are embedded as PNG, not
SVG.** After publishing the real, Mermaid-rendered diagram to the production
ClickUp Doc, it failed to render - shown as literal unrendered Markdown text,
not an image. The decoded SVG was ~20KB with a `<style>` block full of
mermaid.js's generated CSS and `@keyframes` animations; ClickUp evidently
doesn't render SVGs like that through its Page API, regardless of how
well-formed they are. This mirrors an unrelated but analogous finding in
`document-clickup-image-support` (a hand-authored content SVG also failed,
there due to a `BeautifulSoup` case-mangling bug) - taken together, the
simplest robust fix was to stop embedding SVG at all: `_render_mermaid_diagrams`
now calls `mermaidx`'s `.png()` output instead of `.svg()`, reusing the same
`data:image/png` embedding path. See that other change's design.md for the
full investigation.

## Risks / Trade-offs

- **[Risk] New native-extension dependencies** (`quickjs-ng`, `resvg-py`) →
  mitigated by making the whole capability an optional extra rather than a
  required dependency of `mkdocs-clickup`.
- **[Risk] Diagrams become non-editable inside ClickUp** once pre-rendered to
  an image — unlike ClickUp's own (UI-only) live Mermaid block, a reader
  can't tweak the diagram in place. Accepted trade-off: the source of truth
  is the MkDocs repo, not ClickUp (consistent with the existing do-not-edit
  notice's whole premise).
- **[Risk] Still depends on `document-clickup-image-support` landing first**
  for the embedding mechanism this design reuses — sequencing dependency
  between the two changes, not a technical risk in itself (already landed).

## Migration Plan

N/A — no code or config migration; this change is documentation-only.

## Open Questions

(none remaining — resolved above: `mermaidx`, optional extra, fallback on
render failure)

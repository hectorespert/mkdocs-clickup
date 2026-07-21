## 1. Pick a local rendering library

- [x] 1.1 Trial `mermaidx` against a representative set of diagram types (flowchart, sequence, class, gantt) and note coverage/failures
- [x] 1.2 Trial `merm` against the same set and note coverage/failures
- [x] 1.3 Pick one based on coverage and maintenance signal; document the choice and why in `design.md`
- [x] 1.4 Decide whether the chosen library is a required dependency or an optional extra (e.g. `mkdocs-clickup[mermaid]`), and update `pyproject.toml` accordingly

## 2. Detect and render Mermaid fences

- [x] 2.1 Detect a fenced code block carrying the bare `mermaid` class (distinct from the existing `language-*` detection in `_language_callback`)
- [x] 2.2 Extract the diagram's raw source text from the block
- [x] 2.3 Render it locally to a PNG image using the chosen library (not SVG - live-verified that ClickUp fails to render Mermaid's own large, `<style>`-heavy SVG output; see `document-clickup-image-support`'s design.md for the full finding)
- [x] 2.4 On render failure, leave the block as a plain fenced code block (today's behavior) instead of raising

## 3. Reuse the image-embedding pipeline

- [x] 3.1 Route a successfully-rendered diagram through the same `data:` URI embedding step built in `document-clickup-image-support`, rather than duplicating it
- [x] 3.2 Confirm the embedded diagram's Markdown reference shape matches what a content SVG/image produces (same downstream handling)

## 4. Tests

- [x] 4.1 A renderable Mermaid fence is embedded as a `data:` URI image in the generated Markdown
- [x] 4.2 An unrenderable Mermaid fence (invalid/unsupported syntax) falls back to a plain fenced code block, and the build does not abort
- [x] 4.3 A build with one unrenderable diagram still successfully publishes all other pages
- [x] 4.4 A page with no Mermaid content is unaffected (no regression to normal code-fence handling)

## 5. Documentation

- [x] 5.1 Document the Mermaid support and its local-rendering requirement (and optional-dependency install instructions, if applicable) in the README
- [x] 5.2 Note the fallback-on-failure behavior as a known limitation tied to the chosen renderer's diagram-type coverage

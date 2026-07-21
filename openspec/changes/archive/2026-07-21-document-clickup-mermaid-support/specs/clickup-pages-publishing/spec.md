## ADDED Requirements

### Requirement: Mermaid diagrams are rendered locally and embedded as images
When a page's rendered HTML contains a fenced code block produced by mkdocs-material's Mermaid support (a code block carrying the bare `mermaid` class, as configured via `pymdownx.superfences` custom fences), the plugin SHALL render that diagram to a PNG image locally at build time — without depending on any external rendering service reachable over the network — and embed it in the generated Markdown as a `data:image/png` URI, using the same embedding mechanism used for other content images. Rendering to PNG rather than SVG is deliberate: ClickUp was live-verified to fail rendering Mermaid's own SVG output.

#### Scenario: Renderable Mermaid fence becomes an embedded diagram
- **WHEN** a page's rendered HTML contains a Mermaid fenced code block that the local renderer can successfully process
- **THEN** the generated Markdown SHALL contain that diagram embedded as a `data:` URI image, in place of the original fenced code block

#### Scenario: Rendering does not depend on network access
- **WHEN** the build machine has no access to any external diagram-rendering service
- **THEN** the plugin SHALL still be able to render and embed a Mermaid diagram, because rendering happens locally

### Requirement: A Mermaid diagram that fails to render falls back to a plain code block
When the local renderer cannot process a Mermaid fenced code block (unsupported diagram syntax or type), the plugin SHALL publish that block as a plain fenced code block containing the original diagram source, rather than aborting the build. This is a deliberate exception to the capability's general "unreadable local image aborts the build" behavior: a renderer limitation is not treated as an authoring error.

#### Scenario: Unsupported diagram syntax falls back gracefully
- **WHEN** a page's rendered HTML contains a Mermaid fenced code block that the local renderer cannot process
- **THEN** the plugin SHALL publish that block as a plain fenced code block containing the original Mermaid source, and SHALL NOT abort the build because of it

#### Scenario: One page's unrenderable diagram does not affect other pages
- **WHEN** one page contains a Mermaid diagram that fails to render while other pages contain renderable diagrams or no diagrams at all
- **THEN** the plugin SHALL still successfully publish every page, with only the unrenderable diagram falling back to a plain code block

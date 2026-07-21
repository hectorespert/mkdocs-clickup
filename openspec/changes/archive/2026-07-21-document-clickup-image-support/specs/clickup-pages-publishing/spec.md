## ADDED Requirements

### Requirement: Images and content SVGs are preserved when converting page HTML to Markdown
The plugin SHALL NOT remove `<img>` elements from a page's HTML during Markdown conversion, regardless of the `autoclean` configuration value. Inline `<svg>` elements SHALL also be preserved, *except* those matching the plugin's existing decorative-icon detection (the `twemoji` class, used for both emoji and `:material-*:`-style icon shortcodes), which `autoclean`, when enabled, SHALL continue to remove as before.

#### Scenario: Page contains an image
- **WHEN** a MkDocs page's rendered HTML contains an `<img>` element
- **THEN** the generated Markdown SHALL include a corresponding image reference, regardless of whether `autoclean` is enabled

#### Scenario: Page contains a content SVG diagram
- **WHEN** a MkDocs page's rendered HTML contains an inline `<svg>` element that is not a decorative icon (no `twemoji` class)
- **THEN** the generated Markdown SHALL include a corresponding image reference for it, regardless of whether `autoclean` is enabled

#### Scenario: Decorative icon SVG is still removed
- **WHEN** a MkDocs page's rendered HTML contains an inline `<svg>` or `<img>` element with the `twemoji` class (an emoji or `:material-*:`-style icon shortcode)
- **THEN** `autoclean`, when enabled, SHALL remove it, same as before this change

### Requirement: Local images are embedded as inline data URIs
For an `<img>` whose `src` resolves to a file within the built site (not an already-absolute external URL), the plugin SHALL read that file's bytes from disk and rewrite the image reference in the generated Markdown to a `data:` URI (base64-encoded, with the file's MIME type). This SHALL NOT depend on `site_url` being configured or on the site having been deployed, consistent with the existing "Links are published as-authored" requirement's independence from `site_url`.

#### Scenario: Local image is embedded
- **WHEN** a page's `<img src>` refers to a local image file that exists in the built site
- **THEN** the plugin SHALL replace that `src` with a `data:<mime>;base64,<encoded bytes>` URI in the published Markdown

#### Scenario: Already-remote image is left untouched
- **WHEN** a page's `<img src>` is already an absolute URL (e.g. `https://...`)
- **THEN** the plugin SHALL publish that `src` unchanged, without embedding it as a data URI

#### Scenario: Image embedded without a configured site_url
- **WHEN** `site_url` is not set in the MkDocs configuration
- **THEN** the plugin SHALL still embed local images as data URIs

#### Scenario: Local image file cannot be read
- **WHEN** a page's `<img src>` resolves to a local file that cannot be found or read
- **THEN** the plugin SHALL raise an error that aborts the build, identifying the page and the missing image, per the existing "Publish failures abort the build" philosophy

### Requirement: Content SVGs are rasterized to PNG and embedded as inline data URIs
For a preserved inline `<svg>` (a content diagram, not a decorative icon), the plugin SHALL rasterize it to PNG and embed the result as a `data:image/png;base64,...` URI, operating on the raw HTML string *before* it is parsed into a soup. Rasterizing (rather than embedding the SVG markup directly) is required because: (1) `BeautifulSoup`'s `html.parser` lowercases attribute names on parse, corrupting case-sensitive SVG attributes (`viewBox`, `markerWidth`, `refX`, ...) if the markup is re-serialized after souping - live-verified to break the diagram entirely in a real ClickUp Doc; and (2) ClickUp itself was live-verified to fail rendering a large, `<style>`-heavy SVG (Mermaid's own output) even when well-formed. This SHALL NOT depend on `site_url` being configured or on the site having been deployed.

#### Scenario: Content SVG is rasterized and embedded
- **WHEN** a page's rendered HTML contains a preserved (non-decorative) inline `<svg>` element
- **THEN** the plugin SHALL replace it in the generated Markdown with an image reference whose URI is `data:image/png;base64,<rasterized bytes>`

#### Scenario: Case-sensitive SVG attributes survive rasterization
- **WHEN** a content SVG uses case-sensitive attributes (e.g. `viewBox`, `markerWidth`, `refX`)
- **THEN** the plugin SHALL rasterize the SVG using its original, unmodified markup, not a re-serialized (and potentially attribute-lowercased) version of it

#### Scenario: Content SVG embedded without a configured site_url
- **WHEN** `site_url` is not set in the MkDocs configuration
- **THEN** the plugin SHALL still rasterize and embed content SVGs as `data:image/png` URIs

#### Scenario: Content SVG cannot be rasterized
- **WHEN** a page's inline `<svg>` markup cannot be rasterized (e.g. malformed markup)
- **THEN** the plugin SHALL raise an error that aborts the build, identifying the page, per the existing "Publish failures abort the build" philosophy

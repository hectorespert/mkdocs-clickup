## REMOVED Requirements

### Requirement: All built pages are published
**Reason**: Replaced by real page-selection/filtering behavior — see the ADDED requirements below (front matter override, include/exclude patterns, configurable default).
**Migration**: No action needed to preserve current behavior — the new `default` config option defaults to `"all"`, and `include`/`exclude` default to empty, so every page continues to be published unless a site author opts into filtering.

## ADDED Requirements

### Requirement: Page publishing is filterable
The plugin SHALL determine whether each MkDocs page is published to ClickUp using, in order of precedence: (1) an explicit `clickup` value in the page's front matter, (2) a match against the `exclude` config patterns, (3) a match against the `include` config patterns, (4) the `default` config value. A page determined to be excluded SHALL NOT be converted to Markdown or stored for publishing — its HTML-to-Markdown conversion SHALL be skipped entirely, not merely excluded from the publish step afterward.

#### Scenario: Excluded page's conversion is skipped
- **WHEN** a page is determined to be excluded
- **THEN** the plugin SHALL NOT run HTML-to-Markdown conversion for it (including image embedding, content SVG rasterization, or Mermaid rendering), and SHALL NOT include it in the set of pages available for publishing

#### Scenario: Included page is published as before
- **WHEN** a page is determined to be included
- **THEN** the plugin SHALL convert and publish it exactly as it did before this capability existed

### Requirement: Front matter overrides publishing inclusion for a page
A page's YAML front matter SHALL be able to set a `clickup` key to `true` or `false`, which SHALL take precedence over both the `include`/`exclude` patterns and the `default` config value for that page.

#### Scenario: Front matter explicitly excludes a page
- **WHEN** a page's front matter sets `clickup: false`
- **THEN** the plugin SHALL exclude that page, regardless of `include`/`exclude` patterns or `default`

#### Scenario: Front matter explicitly includes a page
- **WHEN** a page's front matter sets `clickup: true`
- **THEN** the plugin SHALL include that page, regardless of `include`/`exclude` patterns or `default`

### Requirement: Include/exclude patterns select pages by src_uri
The plugin configuration SHALL accept `include` and `exclude` options, each a list of patterns matched against a page's `src_uri` using `fnmatch` semantics (where `*` matches any run of characters, including `/`). For a page without an explicit front-matter `clickup` value, a match against any `exclude` pattern SHALL exclude it; otherwise a match against any `include` pattern SHALL include it.

#### Scenario: A page matches an exclude pattern
- **WHEN** a page's `src_uri` matches a configured `exclude` pattern and its front matter has no explicit `clickup` value
- **THEN** the plugin SHALL exclude that page

#### Scenario: A page matches an include pattern
- **WHEN** a page's `src_uri` matches a configured `include` pattern, does not match any `exclude` pattern, and its front matter has no explicit `clickup` value
- **THEN** the plugin SHALL include that page

#### Scenario: A page matches both an include and an exclude pattern
- **WHEN** a page's `src_uri` matches both a configured `include` pattern and a configured `exclude` pattern
- **THEN** the plugin SHALL exclude that page (`exclude` takes precedence)

#### Scenario: A pattern matches across path segments
- **WHEN** a configured pattern contains `*` and a page's `src_uri` has multiple path segments (e.g. `internal-repo/sub/deep/page.md` against the pattern `internal-repo/*`)
- **THEN** the plugin SHALL treat it as a match, since `*` crosses `/` under `fnmatch` semantics

### Requirement: A configurable default determines unmatched pages
The plugin configuration SHALL accept a `default` option, either `"all"` (the default) or `"none"`. For a page whose front matter has no explicit `clickup` value and whose `src_uri` matches neither an `include` nor an `exclude` pattern, the plugin SHALL include it when `default` is `"all"` and exclude it when `default` is `"none"`.

#### Scenario: Default all publishes an unmatched page
- **WHEN** `default` is `"all"` (or unset) and a page matches no front-matter override or pattern
- **THEN** the plugin SHALL include that page

#### Scenario: Default none excludes an unmatched page
- **WHEN** `default` is `"none"` and a page matches no front-matter override or pattern
- **THEN** the plugin SHALL exclude that page

## MODIFIED Requirements

### Requirement: A Section's anchor is a real index page when one exists
When a `nav` section's direct children include a page whose source path ends in `index.md` or `README.md`, **and that page is itself being published** (not excluded by page-selection/filtering), the plugin SHALL use that page as the section's anchor: its ClickUp `page_id` becomes the `parent_page_id` for the section's other members. An `index.md`/`README.md` child that is excluded from publishing SHALL NOT be treated as the section's anchor — the section SHALL fall back to a placeholder anchor instead, as if it had no index child at all.

#### Scenario: Section with an index page
- **WHEN** a `nav` section has a direct child page ending in `index.md` or `README.md`, and that page is being published
- **THEN** the plugin SHALL NOT create a placeholder page for that section, and SHALL use the index page's ClickUp `page_id` as the `parent_page_id` for the section's other children

#### Scenario: Section's index page is excluded from publishing
- **WHEN** a `nav` section's direct child page ending in `index.md`/`README.md` is excluded from publishing (via front matter or patterns)
- **THEN** the plugin SHALL treat the section as if it had no index child, creating or using a placeholder anchor instead of pointing sibling pages' `parent_page_id` at the excluded (never-published) page

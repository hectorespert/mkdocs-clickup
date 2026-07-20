## ADDED Requirements

### Requirement: Every published page carries a do-not-edit notice

The plugin SHALL prepend a fixed do-not-edit notice to the Markdown content of every page it publishes, including section placeholder anchors. The notice SHALL make clear that the page is auto-generated from the source repository and that edits made in ClickUp are overwritten on the next publish. Because the plugin overwrites each page's content in full on every publish, the notice SHALL be regenerated each build and SHALL NOT accumulate across builds. The notice is fixed; there is no configuration to change or disable it.

#### Scenario: A published page begins with the notice

- **WHEN** the plugin publishes (creates or updates) a page
- **THEN** the content sent to ClickUp SHALL begin with the do-not-edit notice, followed by the page's own generated Markdown

#### Scenario: Placeholder anchors also carry the notice

- **WHEN** the plugin publishes a section placeholder anchor
- **THEN** its content SHALL be the do-not-edit notice (the placeholder is no longer empty)

#### Scenario: The notice does not accumulate on rebuild

- **WHEN** the same page is published across two builds
- **THEN** its content SHALL contain the notice exactly once, not once per build

### Requirement: The notice links to the source when an edit URL is available

When a published page has an edit URL (as computed by MkDocs from the site's `repo_url` and `edit_uri` and the page's source path), the plugin SHALL include a link to that source in the notice, so readers are directed to edit the source rather than ClickUp. When no edit URL is available — the site has no `repo_url`/`edit_uri`, or the page is a section placeholder with no source file — the plugin SHALL emit the notice without a link.

#### Scenario: Page with an edit URL

- **WHEN** a published page has a non-empty edit URL
- **THEN** its notice SHALL include a link to that edit URL

#### Scenario: Page or placeholder without an edit URL

- **WHEN** a published page has no edit URL (no repo configuration, or a placeholder anchor)
- **THEN** its notice SHALL be published without a source link, and publishing SHALL proceed normally

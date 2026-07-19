# clickup-pages-publishing

## Purpose

Publish MkDocs-generated page content to a ClickUp Doc as flat ClickUp Pages, using a fixed-env-var API token and required `workspace_id`/`doc_id` plugin config, always creating (never updating) pages.

## Requirements

### Requirement: Publish each converted page as a ClickUp Page
The plugin SHALL create a ClickUp Page for every MkDocs page whose HTML was converted to Markdown during the build.

#### Scenario: Page published on build completion
- **WHEN** a MkDocs site build completes and pages have been converted to Markdown
- **THEN** the plugin SHALL send a request to create a new ClickUp Page for each converted page, using the page's title as the ClickUp Page name and its generated Markdown as the page content with `content_format: text/md`

### Requirement: All built pages are published
The plugin SHALL publish every page that MkDocs converts to Markdown. There is no page-selection or filtering configuration in this capability.

#### Scenario: Every converted page is published
- **WHEN** a MkDocs build completes with N pages converted to Markdown
- **THEN** the plugin SHALL attempt to create N ClickUp Pages, one per converted page, with no exclusions

### Requirement: Publishing is opt-in per invocation
The plugin SHALL only attempt to publish pages to ClickUp when the `PUBLISH_TO_CLICKUP` environment variable is set to a truthy value. When it is unset or falsy, `on_post_build` SHALL do nothing — no configuration validation, no HTTP calls — regardless of whether `workspace_id`, `doc_id`, or the API token are set or valid.

#### Scenario: Publishing disabled by default
- **WHEN** a MkDocs build runs (via `build`, `serve`, or `gh-deploy`) without `PUBLISH_TO_CLICKUP` set to a truthy value
- **THEN** the plugin SHALL NOT make any ClickUp API requests and SHALL NOT validate `workspace_id`, `doc_id`, or the API token

#### Scenario: Publishing enabled explicitly
- **WHEN** `PUBLISH_TO_CLICKUP` is set to a truthy value and a MkDocs build completes
- **THEN** the plugin SHALL validate its ClickUp configuration and proceed to publish converted pages

### Requirement: Required workspace and Doc configuration when publishing
`workspace_id` and `doc_id` (identifying an existing ClickUp Workspace and Doc to publish into) are optional at the plugin's configuration-schema level, so that builds which do not publish are not forced to set them. When publishing is enabled (`PUBLISH_TO_CLICKUP` is set), the plugin SHALL require both to be present. The plugin SHALL NOT create a Workspace or Doc itself.

#### Scenario: Missing workspace_id or doc_id while publishing is enabled
- **WHEN** `PUBLISH_TO_CLICKUP` is set to a truthy value and the plugin config does not include both `workspace_id` and `doc_id`
- **THEN** the plugin SHALL raise an error during `on_post_build`, before attempting to publish any pages

### Requirement: API token from environment variable, validated when publishing
When publishing is enabled, the plugin SHALL read the ClickUp API token from the `CLICKUP_API_TOKEN` environment variable. The plugin configuration SHALL NOT accept the token as a `mkdocs.yml` value.

#### Scenario: Missing token while publishing is enabled
- **WHEN** `PUBLISH_TO_CLICKUP` is set to a truthy value and the `CLICKUP_API_TOKEN` environment variable is not set
- **THEN** the plugin SHALL raise an error during `on_post_build`, before attempting to publish any pages

### Requirement: Flat page creation
Pages SHALL be created directly under the configured Doc with no parent page — the plugin SHALL NOT set `parent_page_id` or otherwise nest created pages.

#### Scenario: Page created without a parent
- **WHEN** the plugin creates a ClickUp Page for a MkDocs page
- **THEN** the create-page request SHALL NOT include a `parent_page_id`, regardless of the page's position in the MkDocs navigation hierarchy

### Requirement: Always create, never update
The plugin SHALL always create a new ClickUp Page for each MkDocs page on every build. It SHALL NOT check for, update, or deduplicate against ClickUp Pages created by a previous build.

#### Scenario: Same page published across multiple builds
- **WHEN** the same MkDocs page is published in two separate builds
- **THEN** the plugin SHALL create two separate ClickUp Pages, with each build unaware of ClickUp Pages created by prior builds

### Requirement: Links are published as-authored
Markdown content published to ClickUp SHALL preserve relative links exactly as they appear in the generated Markdown. The plugin SHALL NOT rewrite relative links into absolute URLs and SHALL NOT require a `site_url` to be configured.

#### Scenario: Relative link left untouched
- **WHEN** a MkDocs page contains a relative link to another page
- **THEN** the Markdown content sent to ClickUp for that page SHALL contain that same relative link, unmodified

### Requirement: Publish failures abort the build
If creating any ClickUp Page fails (a non-success API response or a network/connection error), the plugin SHALL raise an error that fails the MkDocs build, rather than silently skipping the page or continuing to the next one.

#### Scenario: ClickUp API returns an error response
- **WHEN** the ClickUp API responds with a non-success status code while creating a Page
- **THEN** the plugin SHALL raise an error that stops the build, including the failing page and the API's error response in the error message

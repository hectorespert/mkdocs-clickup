# clickup-pages-publishing

## Purpose

Publish MkDocs-generated page content to a ClickUp Doc as flat ClickUp Pages, using a fixed-env-var API token and required `workspace_id`/`doc_id` plugin config, idempotently creating or updating pages by matching them across builds via `sub_title`.

## Requirements

### Requirement: Publish each converted page as a ClickUp Page
The plugin SHALL publish a ClickUp Page for every MkDocs page whose HTML was converted to Markdown during the build — creating it if no existing ClickUp page matches, or updating it in place if one does.

#### Scenario: Page published on build completion
- **WHEN** a MkDocs site build completes and pages have been converted to Markdown
- **THEN** the plugin SHALL send a create or update request for each converted page, depending on whether an existing ClickUp page matches it, using the page's title as the ClickUp Page name and its generated Markdown as the page content with `content_format: text/md`

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

### Requirement: Existing pages are fetched before publishing
The plugin SHALL fetch the Doc's existing pages (`GET .../docs/{doc_id}/pages`) once per build before creating or updating any page, to build a match set keyed by `sub_title`.

#### Scenario: Existing pages fetched once
- **WHEN** publishing is enabled and a MkDocs build completes
- **THEN** the plugin SHALL make exactly one request to list the Doc's existing pages before creating or updating any page

### Requirement: Pages are matched by sub_title, not by title
The plugin SHALL store each MkDocs page's `src_uri` in the ClickUp Page's `sub_title` field, and SHALL use `sub_title` (not the page title/`name`) to match a current MkDocs page against an existing ClickUp page across builds.

#### Scenario: Two pages share a title
- **WHEN** two different MkDocs pages have the same title but different `src_uri`
- **THEN** the plugin SHALL treat them as distinct pages and SHALL NOT match one's ClickUp page to the other

### Requirement: Matched pages are updated in place
When an existing ClickUp page's `sub_title` matches a current MkDocs page's `src_uri`, the plugin SHALL update that page (`PUT`) with the current title, content, and unchanged `sub_title`, rather than creating a new page.

#### Scenario: Same page published across multiple builds
- **WHEN** the same MkDocs page (same `src_uri`) is published in two separate builds
- **THEN** the plugin SHALL update the same ClickUp Page (same `page_id`) on the second build, rather than creating a second page

### Requirement: Unmatched pages are created
When no existing ClickUp page's `sub_title` matches a current MkDocs page's `src_uri`, the plugin SHALL create a new ClickUp Page (`POST`), setting `sub_title` to that page's `src_uri`.

#### Scenario: New MkDocs page published for the first time
- **WHEN** a MkDocs page's `src_uri` matches no existing ClickUp page's `sub_title`
- **THEN** the plugin SHALL create a new ClickUp Page for it, with `sub_title` set to its `src_uri`

### Requirement: Orphaned pages are archived best-effort
An existing ClickUp page whose `sub_title` matches no current MkDocs page's `src_uri` (its source was renamed or deleted) SHALL be archived by the plugin via `PUT` with `archived: true`. This field is not part of ClickUp's documented Edit Page schema; if the archive request fails or has no visible effect, the plugin SHALL log a warning and SHALL NOT raise an error or abort the build.

#### Scenario: MkDocs page removed since the last build
- **WHEN** a ClickUp page's `sub_title` matches no `src_uri` in the current build
- **THEN** the plugin SHALL attempt to archive that page and SHALL continue the build regardless of whether the archive attempt succeeds

#### Scenario: Archive attempt fails
- **WHEN** the plugin attempts to archive an orphaned page and the request fails
- **THEN** the plugin SHALL log a warning identifying the orphaned page and SHALL NOT raise an error or abort the build

### Requirement: Links are published as-authored
Markdown content published to ClickUp SHALL preserve relative links exactly as they appear in the generated Markdown. The plugin SHALL NOT rewrite relative links into absolute URLs and SHALL NOT require a `site_url` to be configured.

#### Scenario: Relative link left untouched
- **WHEN** a MkDocs page contains a relative link to another page
- **THEN** the Markdown content sent to ClickUp for that page SHALL contain that same relative link, unmodified

### Requirement: Publish failures abort the build
If creating or updating any ClickUp Page fails (a non-success API response or a network/connection error), the plugin SHALL raise an error that fails the MkDocs build, rather than silently skipping the page or continuing to the next one. This does NOT apply to orphan-archival failures, which are handled separately as a non-fatal, best-effort operation.

#### Scenario: ClickUp API returns an error response
- **WHEN** the ClickUp API responds with a non-success status code while creating or updating a Page
- **THEN** the plugin SHALL raise an error that stops the build, including the failing page and the API's error response in the error message

#### Scenario: Archive failure does not abort the build
- **WHEN** an orphan-archival request fails
- **THEN** the plugin SHALL NOT raise an error or abort the build because of that failure alone

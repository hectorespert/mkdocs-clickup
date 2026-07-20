# clickup-pages-publishing

## Purpose

Publish MkDocs-generated page content to a ClickUp Doc as ClickUp Pages nested to mirror the MkDocs `nav` hierarchy, using a fixed-env-var API token and required `workspace_id`/`doc_id` plugin config, idempotently creating or updating pages by matching them across builds via `sub_title`, and retrying transient ClickUp API failures so intermittent errors don't abort the build.

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

### Requirement: Pages are nested to mirror MkDocs navigation
The plugin SHALL set each published ClickUp Page's `parent_page_id` to reflect that page's position in the MkDocs `nav` hierarchy, rather than always publishing pages flat under the Doc. This is the default behavior; there is no configuration option to disable it.

#### Scenario: Page nested under its navigation section
- **WHEN** a MkDocs page belongs to a `nav` section
- **THEN** the plugin SHALL set that page's `parent_page_id` to the ClickUp page id of the section's resolved anchor (see "A Section's anchor is a real index page when one exists" and "A Section's anchor is a placeholder page when no index page exists")

#### Scenario: Top-level page has no parent
- **WHEN** a MkDocs page has no enclosing `nav` section (or its enclosing section is itself top-level with no anchor above it)
- **THEN** the plugin SHALL publish that page without a `parent_page_id`, same as a flat root-level page

### Requirement: A Section's anchor is a real index page when one exists
When a `nav` section's direct children include a page whose source path ends in `index.md` or `README.md`, the plugin SHALL use that page as the section's anchor: its ClickUp `page_id` becomes the `parent_page_id` for the section's other members.

#### Scenario: Section with an index page
- **WHEN** a `nav` section has a direct child page ending in `index.md` or `README.md`
- **THEN** the plugin SHALL NOT create a placeholder page for that section, and SHALL use the index page's ClickUp `page_id` as the `parent_page_id` for the section's other children

### Requirement: A Section's anchor is a placeholder page when no index page exists
When a `nav` section has no direct child page ending in `index.md` or `README.md`, the plugin SHALL create or update a placeholder ClickUp Page to act as that section's anchor. The placeholder SHALL have empty content and a `sub_title` synthesized from the section's title breadcrumb (its own title prefixed by its ancestor sections' titles), distinguishable from any real page's `sub_title` (which is always a `src_uri`).

#### Scenario: Section without an index page
- **WHEN** a `nav` section has no direct child page ending in `index.md` or `README.md`
- **THEN** the plugin SHALL create or update a placeholder ClickUp Page with empty content, using it as the `parent_page_id` for the section's children

#### Scenario: Placeholder matched across builds
- **WHEN** the same `nav` section (same title breadcrumb) is published in two separate builds
- **THEN** the plugin SHALL update the same placeholder ClickUp Page across both builds, rather than creating a second one

#### Scenario: Section renamed or restructured
- **WHEN** a `nav` section's title breadcrumb no longer matches any existing placeholder's synthetic `sub_title`
- **THEN** the plugin SHALL treat the previous placeholder as orphaned (archived best-effort, per the existing orphan-archival requirement) and create a new placeholder for the new breadcrumb

### Requirement: Existing pages are fetched before publishing
The plugin SHALL fetch the Doc's existing pages (`GET .../docs/{doc_id}/pages`) once per build before creating or updating any page, to build a match set keyed by `sub_title`. Because this endpoint returns a nested tree (each page's children listed recursively under its own `pages` key, with only root-level pages appearing at the top level), the plugin SHALL recursively flatten the response so that every existing page — root or nested at any depth — is included in the match set.

#### Scenario: Existing pages fetched once
- **WHEN** publishing is enabled and a MkDocs build completes
- **THEN** the plugin SHALL make exactly one request to list the Doc's existing pages before creating or updating any page

#### Scenario: Nested pages are included in the match set
- **WHEN** the Doc's existing pages include one or more pages with a non-null `parent_page_id`, nested under the top-level response's `pages` key
- **THEN** the plugin SHALL include those nested pages in its `sub_title`-keyed match set, exactly as it does for top-level pages

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

### Requirement: A matched page is re-parented when its computed parent changes
When an existing ClickUp page is matched (via `sub_title`) to a current MkDocs page or section anchor, and the page's newly computed `parent_page_id` differs from what it had before, the plugin SHALL update the page's `parent_page_id` via the same `PUT` request used to update its content — not by archiving and recreating it.

#### Scenario: Section gains a real index page
- **WHEN** a `nav` section previously anchored by a placeholder gains a direct child page ending in `index.md`/`README.md`
- **THEN** the plugin SHALL re-parent the section's other member pages to the new index page's ClickUp `page_id` via `PUT`, and SHALL treat the now-unused placeholder as orphaned

#### Scenario: Re-parenting failure is a normal publish failure
- **WHEN** a `PUT` request that includes an updated `parent_page_id` fails
- **THEN** the plugin SHALL raise an error that aborts the build, per the existing "Publish failures abort the build" requirement — a failed re-parent is not treated as a best-effort, non-fatal operation

### Requirement: Unmatched pages are created
When no existing ClickUp page's `sub_title` matches a current MkDocs page's `src_uri`, the plugin SHALL create a new ClickUp Page (`POST`), setting `sub_title` to that page's `src_uri`.

#### Scenario: New MkDocs page published for the first time
- **WHEN** a MkDocs page's `src_uri` matches no existing ClickUp page's `sub_title`
- **THEN** the plugin SHALL create a new ClickUp Page for it, with `sub_title` set to its `src_uri`

### Requirement: Pages are published in parent-before-child order
The plugin SHALL publish (create, update, or create as a placeholder) each page's resolved anchor before publishing that page itself, so that a page's `parent_page_id` always refers to an anchor that already has a ClickUp `page_id` — whether obtained from the pre-publish fetch or from having just been created earlier in the same build.

#### Scenario: Placeholder created before its children
- **WHEN** a `nav` section requires a new placeholder anchor and also contains new (previously unpublished) member pages
- **THEN** the plugin SHALL create the placeholder and obtain its ClickUp `page_id` before sending the create/update requests for that section's member pages

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

### Requirement: Transient ClickUp failures are retried before failing
The plugin SHALL retry a ClickUp API request that fails transiently, rather than aborting on the first failure. A failure is transient when it is a connection error, a read/connect timeout, or a response with status `429`, `500`, `502`, `503`, or `504`. The plugin SHALL make up to 5 total attempts (1 initial plus 4 retries) per request, waiting between attempts with exponential backoff plus jitter. This applies to every ClickUp call the plugin makes: fetching existing pages (GET), creating pages (POST), updating pages (PUT), and archiving orphaned pages (PUT). Only after all attempts are exhausted does the existing "Publish failures abort the build" requirement take effect (or, for archival, the existing best-effort behavior).

#### Scenario: A transient error is retried and then succeeds
- **WHEN** a ClickUp request fails with a timeout, connection error, or a `429`/`500`/`502`/`503`/`504` response, and a subsequent attempt succeeds
- **THEN** the plugin SHALL use the successful response and continue publishing, without aborting the build

#### Scenario: Retries are exhausted
- **WHEN** a ClickUp create or update request fails transiently on all 5 attempts
- **THEN** the plugin SHALL raise an error that aborts the build, per the existing "Publish failures abort the build" requirement

#### Scenario: Deterministic client errors are not retried
- **WHEN** a ClickUp request returns a non-`429` `4xx` response (for example `400`, `401`, or `404`)
- **THEN** the plugin SHALL NOT retry it and SHALL surface the failure immediately

### Requirement: Requests use an explicit timeout
The plugin SHALL configure its HTTP client with an explicit request timeout of 30 seconds, rather than relying on the client library's shorter default, so that a slow (but not failed) ClickUp response is not prematurely treated as a failure.

#### Scenario: A slow response within the timeout is honored
- **WHEN** ClickUp responds after longer than the library's default timeout but within 30 seconds
- **THEN** the plugin SHALL accept the response instead of timing out

### Requirement: Rate-limit responses honor Retry-After
When a retried response is a `429` (rate limited) and carries a `Retry-After` header, the plugin SHALL wait at least the indicated duration before the next attempt. When the header is absent, the plugin SHALL fall back to its exponential backoff. The plugin SHALL NOT add proactive delays between requests that are not rate limited.

#### Scenario: 429 with Retry-After
- **WHEN** a ClickUp request returns `429` with a `Retry-After` header
- **THEN** the plugin SHALL wait at least that long before retrying

#### Scenario: 429 without Retry-After
- **WHEN** a ClickUp request returns `429` with no `Retry-After` header
- **THEN** the plugin SHALL retry using its exponential backoff schedule

### Requirement: Page creation is duplicate-safe under retries
Because creating a page (POST) is not idempotent, the plugin SHALL NOT create a duplicate page when it retries a POST whose earlier attempt may have already been committed by ClickUp (for example when the response was lost to a timeout). Before re-sending a failed POST, the plugin SHALL re-fetch the Doc's pages and, if a page with the same `sub_title` now exists, adopt that page (use its id and treat the create as succeeded) instead of creating a second page. This preserves the `sub_title`-keyed idempotency the plugin relies on across builds.

#### Scenario: A lost POST response does not create a duplicate
- **WHEN** a POST to create a page fails transiently but ClickUp had already created the page, and the plugin retries
- **THEN** the plugin SHALL detect the existing page by its `sub_title`, adopt its id, and SHALL NOT create a second page with the same `sub_title`

#### Scenario: A genuinely uncreated page is retried
- **WHEN** a POST to create a page fails transiently and no page with that `sub_title` exists on re-fetch
- **THEN** the plugin SHALL re-send the POST to create the page

### Requirement: Publish failures abort the build
If creating or updating any ClickUp Page fails (a non-success API response or a network/connection error), the plugin SHALL raise an error that fails the MkDocs build, rather than silently skipping the page or continuing to the next one. This does NOT apply to orphan-archival failures, which are handled separately as a non-fatal, best-effort operation.

#### Scenario: ClickUp API returns an error response
- **WHEN** the ClickUp API responds with a non-success status code while creating or updating a Page
- **THEN** the plugin SHALL raise an error that stops the build, including the failing page and the API's error response in the error message

#### Scenario: Archive failure does not abort the build
- **WHEN** an orphan-archival request fails
- **THEN** the plugin SHALL NOT raise an error or abort the build because of that failure alone

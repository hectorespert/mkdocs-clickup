## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Publish failures abort the build
If creating or updating any ClickUp Page fails (a non-success API response or a network/connection error), the plugin SHALL raise an error that fails the MkDocs build, rather than silently skipping the page or continuing to the next one. This does NOT apply to orphan-archival failures, which are handled separately as a non-fatal, best-effort operation.

#### Scenario: ClickUp API returns an error response
- **WHEN** the ClickUp API responds with a non-success status code while creating or updating a Page
- **THEN** the plugin SHALL raise an error that stops the build, including the failing page and the API's error response in the error message

#### Scenario: Archive failure does not abort the build
- **WHEN** an orphan-archival request fails
- **THEN** the plugin SHALL NOT raise an error or abort the build because of that failure alone

## REMOVED Requirements

### Requirement: Always create, never update
**Reason**: Replaced by idempotent create-or-update, keyed on a `sub_title`-encoded `src_uri`, to stop accumulating duplicate pages across builds.
**Migration**: No user action required. On the first build after upgrading, existing v1-created pages (which have no `sub_title` set) will not match any current page and will be treated as orphans — best-effort archived (or left visible if archival is unavailable) — while every current MkDocs page publishes fresh with its `sub_title` set for future matching.

## ADDED Requirements

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

### Requirement: Pages are published in parent-before-child order
The plugin SHALL publish (create, update, or create as a placeholder) each page's resolved anchor before publishing that page itself, so that a page's `parent_page_id` always refers to an anchor that already has a ClickUp `page_id` — whether obtained from the pre-publish fetch or from having just been created earlier in the same build.

#### Scenario: Placeholder created before its children
- **WHEN** a `nav` section requires a new placeholder anchor and also contains new (previously unpublished) member pages
- **THEN** the plugin SHALL create the placeholder and obtain its ClickUp `page_id` before sending the create/update requests for that section's member pages

### Requirement: A matched page is re-parented when its computed parent changes
When an existing ClickUp page is matched (via `sub_title`) to a current MkDocs page or section anchor, and the page's newly computed `parent_page_id` differs from what it had before, the plugin SHALL update the page's `parent_page_id` via the same `PUT` request used to update its content — not by archiving and recreating it.

#### Scenario: Section gains a real index page
- **WHEN** a `nav` section previously anchored by a placeholder gains a direct child page ending in `index.md`/`README.md`
- **THEN** the plugin SHALL re-parent the section's other member pages to the new index page's ClickUp `page_id` via `PUT`, and SHALL treat the now-unused placeholder as orphaned

#### Scenario: Re-parenting failure is a normal publish failure
- **WHEN** a `PUT` request that includes an updated `parent_page_id` fails
- **THEN** the plugin SHALL raise an error that aborts the build, per the existing "Publish failures abort the build" requirement — a failed re-parent is not treated as a best-effort, non-fatal operation

## MODIFIED Requirements

### Requirement: Existing pages are fetched before publishing
The plugin SHALL fetch the Doc's existing pages (`GET .../docs/{doc_id}/pages`) once per build before creating or updating any page, to build a match set keyed by `sub_title`. Because this endpoint returns a nested tree (each page's children listed recursively under its own `pages` key, with only root-level pages appearing at the top level), the plugin SHALL recursively flatten the response so that every existing page — root or nested at any depth — is included in the match set.

#### Scenario: Existing pages fetched once
- **WHEN** publishing is enabled and a MkDocs build completes
- **THEN** the plugin SHALL make exactly one request to list the Doc's existing pages before creating or updating any page

#### Scenario: Nested pages are included in the match set
- **WHEN** the Doc's existing pages include one or more pages with a non-null `parent_page_id`, nested under the top-level response's `pages` key
- **THEN** the plugin SHALL include those nested pages in its `sub_title`-keyed match set, exactly as it does for top-level pages

## REMOVED Requirements

### Requirement: Flat page creation
**Reason**: Replaced by nested placement that mirrors the MkDocs `nav` hierarchy via `parent_page_id`, resolved through per-section anchors (a real index page or a synthetic placeholder). The flat structure was a proof-of-concept default while idempotent create/update was being built, not a behavior to preserve.
**Migration**: No user action required. On the first build after upgrading, a site with a non-trivial `nav` hierarchy will have its existing (previously flat) pages re-parented in place via the existing `sub_title` match, and new placeholder pages may appear for sections without their own index page. A flat site with no nested `nav` sections is unaffected.

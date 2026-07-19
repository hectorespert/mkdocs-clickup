## Why

`mkdocs-clickup` is currently a bootstrap skeleton: it converts each MkDocs page's HTML into Markdown (`on_page_content`) but publishes nothing anywhere. The project's whole purpose is to publish MkDocs documentation to ClickUp Pages, and a first research spike (see README.md's "ClickUp API research" section) has already resolved the biggest unknowns — auth, endpoints, and content format. It's time to implement the smallest version of the actual publishing behavior so the plugin does something real, and to establish the pattern (config validation, HTTP client, error handling) that later changes will extend.

## What Changes

- Add a `on_post_build` hook to `MkdocsClickUpPlugin` that, for every page converted during the build, creates a corresponding page in a ClickUp Doc via the ClickUp API.
- Add required plugin config: `workspace_id` and `doc_id`, identifying a pre-existing ClickUp Workspace and Doc to publish into. Validated the same way `site_url` already is in `on_config` — a clear `PluginError`/`ValueError` if missing.
- Read the ClickUp API token from a fixed environment variable (`CLICKUP_API_TOKEN`), not from plugin config — never accept it as a `mkdocs.yml` value, since that file is typically committed to version control.
- Every page MkDocs builds is published — no page-selection/filtering config in this change.
- Every page is created flat, directly under the given Doc — no nested pages, no `parent_page_id`.
- Every build always creates new ClickUp pages; there is no update-in-place and no persisted mapping between MkDocs pages and ClickUp page IDs. Running the same build twice produces duplicate pages in ClickUp. This is a known, accepted limitation of this first version, not an oversight — see design.md for why, and what a future change would need to add to fix it.

## Capabilities

### New Capabilities
- `clickup-pages-publishing`: publishing MkDocs-generated page content to a ClickUp Doc as flat ClickUp Pages, using a fixed-env-var API token and required `workspace_id`/`doc_id` plugin config, always creating (never updating) pages.

### Modified Capabilities
(none — no existing specs in `openspec/specs/` yet)

## Impact

- `src/mkdocs_clickup/_internal/plugin.py`: new `on_post_build` hook; `on_config` gains `workspace_id`/`doc_id`/token validation.
- `src/mkdocs_clickup/_internal/config.py`: new required `workspace_id` and `doc_id` fields on `_PluginConfig`.
- New dependency: an HTTP client for calling the ClickUp REST API (none is currently a project dependency — `httpx` or `requests` need to be added to `pyproject.toml`).
- `tests/`: new tests covering config validation and the publish behavior (mocking the ClickUp API).
- No changes to `mkdocs.yml`'s own docs-build config in this repo (self-dogfooding the `clickup` plugin to publish this project's own docs is out of scope here — would need a real ClickUp workspace/Doc to point at).

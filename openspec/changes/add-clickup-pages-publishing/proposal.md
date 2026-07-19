## Why

`mkdocs-clickup` is currently a bootstrap skeleton: it converts each MkDocs page's HTML into Markdown (`on_page_content`) but publishes nothing anywhere. The project's whole purpose is to publish MkDocs documentation to ClickUp Pages, and a first research spike (see README.md's "ClickUp API research" section) has already resolved the biggest unknowns — auth, endpoints, and content format. It's time to implement the smallest version of the actual publishing behavior so the plugin does something real, and to establish the pattern (config validation, HTTP client, error handling) that later changes will extend.

## What Changes

- Add a `on_post_build` hook to `MkdocsClickUpPlugin` that, for every page converted during the build, creates a corresponding page in a ClickUp Doc via the ClickUp API.
- Publishing only happens when the `PUBLISH_TO_CLICKUP` environment variable is set to a truthy value — e.g. `PUBLISH_TO_CLICKUP=1 mkdocs build`. When it's unset, `on_post_build` does nothing at all: no config validation, no HTTP calls. This matters because `mkdocs serve` runs the exact same build hooks (including `on_post_build`) on every file save during live-reload, and `mkdocs gh-deploy` runs them too before its GitHub push — without this opt-in gate, routine local development would spam-create ClickUp pages. (MkDocs itself has no plugin extension point for adding CLI flags or subcommands — confirmed by reading `mkdocs/__main__.py` and empirically: `mkdocs build --publish` errors with "No such option" — so an environment variable, not a new CLI flag, is the mechanism.)
- Add plugin config: `workspace_id` and `doc_id`, identifying a pre-existing ClickUp Workspace and Doc to publish into. These are optional at the config-schema level (a build that isn't publishing shouldn't be forced to set them) but required — with a clear `PluginError` — once publishing is actually enabled.
- Read the ClickUp API token from a fixed environment variable (`CLICKUP_API_TOKEN`), not from plugin config — never accept it as a `mkdocs.yml` value, since that file is typically committed to version control. Like `workspace_id`/`doc_id`, it's only validated once publishing is enabled.
- Every page MkDocs builds is published — no page-selection/filtering config in this change.
- Every page is created flat, directly under the given Doc — no nested pages, no `parent_page_id`.
- **Remove** the `site_url` requirement and the relative-to-absolute link rewriting inherited from the llms.txt-era plugin (`_convert_to_absolute_links`/`_convert_to_absolute_link`, and the `base_url` config option). That mechanism rewrote relative links to point at a publicly hosted MkDocs site — it doesn't apply to ClickUp Pages and was already flagged in the code as needing revisiting once ClickUp's addressing model was known. Links inside Markdown published to ClickUp are left exactly as authored (relative); proper link resolution for ClickUp is deferred to a future change once that addressing model is actually designed.
- Every build always creates new ClickUp pages; there is no update-in-place and no persisted mapping between MkDocs pages and ClickUp page IDs. Running the same build twice produces duplicate pages in ClickUp. This is a known, accepted limitation of this first version, not an oversight — see design.md for why, and what a future change would need to add to fix it.

## Capabilities

### New Capabilities
- `clickup-pages-publishing`: publishing MkDocs-generated page content to a ClickUp Doc as flat ClickUp Pages, using a fixed-env-var API token and required `workspace_id`/`doc_id` plugin config, always creating (never updating) pages.

### Modified Capabilities
(none — no existing specs in `openspec/specs/` yet)

## Impact

- `src/mkdocs_clickup/_internal/plugin.py`: new `on_post_build` hook, gated on `PUBLISH_TO_CLICKUP` (all ClickUp-specific validation — `workspace_id`, `doc_id`, token — happens inside it); `on_config` loses its `site_url` check and `base_url` resolution, keeping only the `self._md_pages` reset; `_convert_to_absolute_links`/`_convert_to_absolute_link` and their call site in `_generate_page_markdown` are removed.
- `src/mkdocs_clickup/_internal/config.py`: new optional `workspace_id` and `doc_id` fields on `_PluginConfig`; `base_url` field removed.
- `tests/test_link_conversion.py`: removed along with the functions it tests.
- New dependency: an HTTP client for calling the ClickUp REST API (none is currently a project dependency — `httpx` or `requests` need to be added to `pyproject.toml`).
- `tests/`: new tests covering config validation and the publish behavior (mocking the ClickUp API).
- No changes to `mkdocs.yml`'s own docs-build config in this repo (self-dogfooding the `clickup` plugin to publish this project's own docs is out of scope here — would need a real ClickUp workspace/Doc to point at).

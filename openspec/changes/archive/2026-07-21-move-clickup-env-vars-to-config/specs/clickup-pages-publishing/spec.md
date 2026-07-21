## MODIFIED Requirements

### Requirement: Publishing is opt-in per invocation
The plugin SHALL only attempt to publish pages to ClickUp when the `publish` plugin configuration option is set to `true`. When it is unset or `false` (the default), `on_post_build` SHALL do nothing — no configuration validation, no HTTP calls — regardless of whether `workspace_id`, `doc_id`, or `token` are set or valid.

#### Scenario: Publishing disabled by default
- **WHEN** a MkDocs build runs (via `build`, `serve`, or `gh-deploy`) without `publish` set to `true` in the plugin configuration
- **THEN** the plugin SHALL NOT make any ClickUp API requests and SHALL NOT validate `workspace_id`, `doc_id`, or `token`

#### Scenario: Publishing enabled explicitly
- **WHEN** `publish` is set to `true` in the plugin configuration and a MkDocs build completes
- **THEN** the plugin SHALL validate its ClickUp configuration and proceed to publish converted pages

### Requirement: API token from plugin configuration, validated when publishing
When publishing is enabled, the plugin SHALL read the ClickUp API token from the `token` plugin configuration option. The plugin configuration SHALL accept the token as a `mkdocs.yml` value; sourcing it from an environment variable (e.g. via MkDocs' `!ENV` YAML tag) rather than a literal string is the site author's responsibility, not the plugin's.

#### Scenario: Missing token while publishing is enabled
- **WHEN** `publish` is set to `true` and the `token` plugin configuration option is not set
- **THEN** the plugin SHALL raise an error during `on_post_build`, before attempting to publish any pages

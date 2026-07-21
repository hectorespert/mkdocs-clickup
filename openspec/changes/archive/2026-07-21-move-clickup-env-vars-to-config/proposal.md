## Why

`PUBLISH_TO_CLICKUP` and `CLICKUP_API_TOKEN` are hardcoded environment-variable names read directly from `os.environ` inside `on_post_build`. The plugin's other identity settings (`workspace_id`, `doc_id`) are already proper `mkdocs.yml` config options, but the publish gate and the API token are not — a user can't rename them, source them from a different variable, or see them documented as part of the plugin's config schema. MkDocs already ships a native `!ENV` YAML tag for exactly this kind of indirection (this project's own `mkdocs.yml` already uses it for `doc_id`), so there is no reason for the plugin itself to own an env-var contract instead of exposing plain config options and letting the site author decide how to populate them.

## What Changes

- **BREAKING**: `_PluginConfig` gains two new options: `token` (optional string) and `publish` (boolean, default `false`).
- **BREAKING**: `on_post_build` reads `self.config.token` and `self.config.publish` instead of `os.environ.get("CLICKUP_API_TOKEN")` / `os.environ.get("PUBLISH_TO_CLICKUP")`. There is no fallback to the old environment variables — a site relying on the bare env vars stops publishing until its `mkdocs.yml` is updated.
- The `_PUBLISH_ENV_VAR` / `_TOKEN_ENV_VAR` constants and all direct `os.environ` reads for these two settings are removed from `plugin.py`.
- Error messages raised when `token` is missing while `publish` is enabled now name the `token` config option, not an environment variable.
- This project's own `mkdocs.yml` (dogfooding config) adds `token: !ENV CLICKUP_API_TOKEN` and `publish: !ENV [PUBLISH_TO_CLICKUP, false]` to its `clickup:` plugin block, so its own CI publish step keeps working.
- `.github/workflows/release.yml`'s `publish-clickup` job changes `PUBLISH_TO_CLICKUP: "1"` to `PUBLISH_TO_CLICKUP: "true"` — required because MkDocs' `!ENV` tag resolves `"1"` to the YAML/Python integer `1`, not a boolean, which fails the new `publish` option's strict `bool` type validation.
- README documents the new options, including an explicit warning to source `token` via `!ENV` rather than a literal string (since `mkdocs.yml` is typically committed to version control).

## Capabilities

### Modified Capabilities
- `clickup-pages-publishing`: the "Publishing is opt-in per invocation" requirement changes its trigger from the `PUBLISH_TO_CLICKUP` environment variable to a `publish` config option; the "API token from environment variable, validated when publishing" requirement is replaced by a `token` config option (the plugin config now *does* accept the token as an `mkdocs.yml` value, reversing the prior explicit prohibition).

## Impact

- `src/mkdocs_clickup/_internal/config.py` — add `token`, `publish` options.
- `src/mkdocs_clickup/_internal/plugin.py` — `on_post_build` reads config instead of environment; remove the two env-var constants and related error-message text.
- `mkdocs.yml` — wire `token`/`publish` via `!ENV` for this project's own dogfood build.
- `.github/workflows/release.yml` — change `PUBLISH_TO_CLICKUP: "1"` to `"true"`.
- `tests/test_plugin.py`, `tests/test_images.py`, `tests/test_mermaid.py` — every test that currently does `monkeypatch.setenv("PUBLISH_TO_CLICKUP", ...)` / `monkeypatch.setenv("CLICKUP_API_TOKEN", ...)` (~40 occurrences total) switches to passing `token`/`publish` through the plugin's config fixture instead.
- README — document `token`/`publish`, with a security note recommending `!ENV` for the token.
- Next release after this change ships is a major version bump (breaking change), with a migration note in `CHANGELOG.md`.

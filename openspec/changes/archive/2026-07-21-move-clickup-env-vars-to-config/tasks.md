## 1. Config schema

- [x] 1.1 Add `token = mkconf.Optional(mkconf.Type(str))` to `_PluginConfig` in `src/mkdocs_clickup/_internal/config.py`.
- [x] 1.2 Add `publish = mkconf.Type(bool, default=False)` to `_PluginConfig`.

## 2. Plugin logic

- [x] 2.1 In `plugin.py`, replace `if not os.environ.get(_PUBLISH_ENV_VAR): return` with `if not self.config.publish: return` in `on_post_build`.
- [x] 2.2 Replace `token = os.environ.get(_TOKEN_ENV_VAR)` with `token = self.config.token`.
- [x] 2.3 Update the "missing token" error message to reference the `token` config option instead of the `CLICKUP_API_TOKEN` environment variable (e.g. `"The 'token' plugin configuration option must be set to publish to ClickUp"`).
- [x] 2.4 Remove the `_PUBLISH_ENV_VAR` and `_TOKEN_ENV_VAR` constants and the `os` import if it becomes unused.
- [x] 2.5 Update the `MkdocsClickUpPlugin` class docstring (currently describes the `PUBLISH_TO_CLICKUP` environment variable) to describe the `publish` config option instead, keeping the explanation of why it defaults to `false` (avoiding accidental publish on `mkdocs serve`/`gh-deploy`) and recommending `!ENV` for CI-only activation.

## 3. Tests

- [x] 3.1 In `tests/test_plugin.py`, extend `_base_config()` (or add a variant) to accept `token`/`publish` values and include them directly in the returned config dict's `clickup` plugin block, instead of every test monkeypatching `PUBLISH_TO_CLICKUP`/`CLICKUP_API_TOKEN`.
- [x] 3.2 Update `test_no_publish_without_env_var` (rename if appropriate, e.g. `test_no_publish_when_disabled`) to omit `publish` from config (relying on the `false` default) instead of `monkeypatch.delenv(...)`, and assert `clickup.requests == []`.
- [x] 3.3 Update `test_missing_token_raises` to enable `publish` via config, omit `token` from config, and assert the `PluginError` message references `token` (not `CLICKUP_API_TOKEN`).
- [x] 3.4 Update `test_missing_workspace_or_doc_id_raises` and every other test in `tests/test_plugin.py` currently using `monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")` / `monkeypatch.setenv("CLICKUP_API_TOKEN", "token")` (~30 occurrences) to instead pass `publish: true` / `token: "token"` through the config dict.
- [x] 3.5 Apply the same migration to all occurrences in `tests/test_images.py` (7 occurrences).
- [x] 3.6 Apply the same migration to all occurrences in `tests/test_mermaid.py` (4 occurrences).
- [x] 3.7 Run the full test suite (`python scripts/make test`) and confirm no test still references `PUBLISH_TO_CLICKUP`/`CLICKUP_API_TOKEN` via `monkeypatch`.

## 4. Project config and CI

- [x] 4.1 Add `token: !ENV CLICKUP_API_TOKEN` and `publish: !ENV [PUBLISH_TO_CLICKUP, false]` to the `clickup:` plugin block in this project's own `mkdocs.yml`.
- [x] 4.2 In `.github/workflows/release.yml`, change the `publish-clickup` job's `PUBLISH_TO_CLICKUP: "1"` to `PUBLISH_TO_CLICKUP: "true"` (required so the `!ENV`-resolved value is a real YAML/Python bool, not an int, per the design doc's gotcha).

## 5. Documentation

- [x] 5.1 Update README's plugin configuration section to document `token` and `publish`, showing `!ENV` as the primary example for both (not literal values), with an explicit warning that a literal `token` string is equivalent to committing the secret to source control.
- [x] 5.2 Add a "Breaking changes" entry to the next `CHANGELOG.md` release section (or note for the next `changelog bump=major` run) describing the migration: bare `PUBLISH_TO_CLICKUP`/`CLICKUP_API_TOKEN` environment variables no longer work standalone; users must add `token`/`publish` to their `mkdocs.yml`, wired via `!ENV` to preserve current behavior. (Deferred to the commit message's breaking-change footer, since `git-changelog` regenerates `CHANGELOG.md` from commits at release time — hand-editing it now would be overwritten.)

## 6. Validation

- [x] 6.1 Run `python scripts/make check` (quality, types, docs, API compatibility) and confirm it passes.
- [x] 6.2 Manually verify (or live-test against the real ClickUp workspace, as done for prior changes this session) that a build with `mkdocs.yml`-configured `token`/`publish` via `!ENV` still publishes successfully end-to-end. (Skipped by user decision — test coverage plus `make check` deemed sufficient; no live ClickUp call made.)

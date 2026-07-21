## Context

`_PluginConfig` (`src/mkdocs_clickup/_internal/config.py`) already exposes `autoclean`, `preprocess`, `workspace_id`, and `doc_id` as `mkdocs.yml` options. The publish gate and the API token are the two remaining settings still read directly from `os.environ` inside `on_post_build` (`plugin.py`), via hardcoded constants `_PUBLISH_ENV_VAR = "PUBLISH_TO_CLICKUP"` and `_TOKEN_ENV_VAR = "CLICKUP_API_TOKEN"`.

The env-var approach was originally deliberate for `PUBLISH_TO_CLICKUP`: `mkdocs serve` and `mkdocs gh-deploy` fire the same `on_post_build` hook as `mkdocs build`, so a static `true` in a committed `mkdocs.yml` would publish on every local save. An environment variable let CI turn publishing on without touching the committed config. MkDocs' own `!ENV` YAML tag (via the `pyyaml-env-tag` package it depends on) provides the same runtime indirection *as a config value* — this project's own `mkdocs.yml` already uses it for `doc_id` (`doc_id: !ENV [CLICKUP_DOC_ID, "2kxuyd0w-532"]`) — so the safety property can be preserved without the plugin owning any env-var-specific code path.

## Goals / Non-Goals

**Goals:**
- Replace the plugin's two hardcoded env-var reads with two `mkdocs.yml` config options: `token` and `publish`.
- Let the site author decide how those options get their values (literal, `!ENV`, `!ENV` with a default, `!ENV` with multiple fallback variable names) using MkDocs' existing, general-purpose mechanism — the plugin itself no longer has an opinion about environment variables at all.
- Preserve the existing safety property that `mkdocs serve`/`gh-deploy` don't publish by accident, by documenting the `!ENV` pattern as the recommended way to set `publish` in CI-only.

**Non-Goals:**
- No backward-compatible fallback to the old `CLICKUP_API_TOKEN`/`PUBLISH_TO_CLICKUP` env vars. This is a clean breaking change (confirmed).
- Not changing `workspace_id`/`doc_id`, which are already config options and unaffected by this change.
- Not adding any new validation/format for the token beyond "non-empty string" (e.g. no ClickUp-specific token format checking).

## Decisions

### `token` config option, no env-var fallback
Add `token = mkconf.Optional(mkconf.Type(str))` to `_PluginConfig`. `on_post_build` reads `self.config.token` directly. The existing spec requirement text "The plugin configuration SHALL NOT accept the token as a `mkdocs.yml` value" is fully reversed by this change — it's exactly the opposite of what we want now.

Rejected alternative: keep reading `os.environ.get("CLICKUP_API_TOKEN")` as a fallback when `self.config.token` is empty. Rejected because the user explicitly asked for a clean breaking change, and a silent dual-path (config *or* env) is exactly the kind of implicit behavior this change is trying to eliminate — it would leave two ways to configure the same thing with unclear precedence.

### `publish` config option, boolean, default `false`
Add `publish = mkconf.Type(bool, default=False)` to `_PluginConfig`. `on_post_build` checks `if not self.config.publish: return` instead of checking the environment variable. Default `false` preserves "publishing is opt-in", matching the existing spec requirement's intent.

### The `!ENV` boolean-resolution gotcha (verified by live-testing this session)
MkDocs' `!ENV` tag (from the `yaml_env_tag` package) does not return raw strings — it resolves the environment variable's value through PyYAML's *implicit* type resolvers before handing it to the config schema. Concretely, tested against the actual loader used by `mkdocs.utils.get_yaml_loader()`:

```python
PUBLISH_TO_CLICKUP=1     → yaml.load("publish: !ENV [PUBLISH_TO_CLICKUP, false]") → {'publish': 1}     # int, not bool
PUBLISH_TO_CLICKUP=true  → yaml.load("publish: !ENV [PUBLISH_TO_CLICKUP, false]") → {'publish': True}  # bool
```

`mkconf.Type(bool)`'s validator (`mkdocs.config.config_options.Type.run_validation`) does a strict `isinstance(value, bool)` check — an `int` `1` fails it with `ValidationError: Expected type: <class 'bool'> but received: <class 'int'>`. This means the *value* set in the environment matters, not just its truthiness: `"1"`/`"0"` (this project's own CI convention until now) do not work with a `bool`-typed `!ENV` config option; only PyYAML's recognized boolean tokens (`true`/`false`, `yes`/`no`, `on`/`off`, in various cases) resolve to real Python `bool`.

Consequence: `.github/workflows/release.yml`'s `PUBLISH_TO_CLICKUP: "1"` must become `PUBLISH_TO_CLICKUP: "true"` as part of this change, and the README must warn downstream users of the same constraint if they wire `publish` via `!ENV`.

### README guidance: never commit `token` as a literal
Because `token` is now a first-class config option, there's a real risk of a user writing `token: pk_12345_ABC...` directly in a committed `mkdocs.yml`. The README must show `!ENV` as the primary example for `token` and explicitly call out that a literal value there is equivalent to committing the secret to source control.

### Test migration approach
All ~40 occurrences across `tests/test_plugin.py`, `tests/test_images.py`, `tests/test_mermaid.py` of `monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")` / `monkeypatch.setenv("CLICKUP_API_TOKEN", "token")` move to passing `token`/`publish` through the plugin's config dict in the test's `mkdocs_conf`/`plugin` fixture setup (however each test currently constructs its MkDocs config for the `clickup` plugin block), rather than through environment variables. This is a mechanical, per-test edit — no test's asserted behavior changes, only how `token`/`publish` are supplied. The one exception is the "no-op when publishing disabled" test (`tests/test_plugin.py:169-171`), which currently uses `monkeypatch.delenv(...)`; its equivalent is simply not setting `publish` in config (relying on the `false` default).

## Risks / Trade-offs

- **[Breaking change for existing users]** → Mitigated by a major version bump and an explicit CHANGELOG migration note showing the `!ENV` wiring needed to restore current behavior.
- **[Users might commit a literal token]** → Mitigated by README guidance and example code that leads with `!ENV`, but the plugin has no way to *enforce* this (MkDocs config options can't detect "was this value typed literally vs. resolved from `!ENV`" — by the time the plugin sees `self.config.token`, both look identical).
- **[`!ENV` boolean gotcha could resurface for any other future boolean env-wired option]** → No general mitigation beyond documenting it once here and in the README; it's a MkDocs/PyYAML behavior, not something this plugin can change.

## Open Questions

None outstanding — scope and breaking-change status were confirmed by the user during exploration.

## Why

ClickUp's v3 Pages API returns **intermittent** read-timeouts and 5xx errors under the plugin's sequential burst of one HTTP request per page (~15 for this repo's own docs). The current client uses the default 5s timeout, performs no retries, and aborts the whole build on the first failure — so publishing fails at a *different* page on nearly every run. This was confirmed empirically this session against the real workspace: the same `changelog.md` that 500s on one run publishes fine (201) on the next, and posting its exact generated Markdown directly always succeeds. The failures are transient API flakiness meeting a fragile, no-retry client — not a content problem.

## What Changes

- Give the ClickUp HTTP client an **explicit 30s timeout** (up from the httpx 5s default).
- **Retry transient failures** with exponential backoff + jitter (5 attempts total): connection errors, read/connect timeouts, and responses with status `429`, `500`, `502`, `503`, `504`.
- Honor `Retry-After` on `429` responses (reactive rate-limit handling); fall back to exponential backoff when the header is absent.
- Do **not** retry deterministic `4xx` (e.g. `400`/`401`/`404`) — surface those immediately.
- Apply retries to **all** ClickUp calls: fetch (GET), create (POST), update (PUT), and the best-effort archive (PUT).
- Keep failure semantics unchanged: once retries are exhausted, still **abort the build** (a failure surviving 5 attempts is a real failure). The existing "Publish failures abort the build" requirement is **not** modified.
- Make POST retries **duplicate-safe**: because creating a page is non-idempotent, a retry after a lost response could create a second page with the same `sub_title`. On a transient POST failure, re-fetch the Doc's pages first and, if a page with that `sub_title` already exists, adopt its id instead of creating a duplicate. This preserves the `sub_title`-keyed idempotency established by `add-clickup-idempotent-page-sync`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `clickup-pages-publishing`: add requirements for transient-failure resilience (retry/backoff, explicit timeout, `Retry-After` handling) and duplicate-safe POST retries. The existing "Publish failures abort the build" requirement is explicitly preserved, not changed.

## Impact

- `pyproject.toml`: add `tenacity` as a runtime dependency.
- `src/mkdocs_clickup/_internal/plugin.py`: explicit httpx timeout; tenacity-based retry for GET/PUT; bespoke duplicate-safe POST create-with-retry (re-fetch + adopt-or-create); route the archive PUT through retry too.
- `tests/test_plugin.py`: cover retry-then-success on transient errors, no-retry on 4xx, abort-after-exhaustion, and the POST-adopt-on-duplicate path.
- Spec delta on `clickup-pages-publishing`.

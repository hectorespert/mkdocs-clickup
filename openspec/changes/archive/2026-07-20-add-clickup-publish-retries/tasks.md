## 1. Dependency

- [x] 1.1 Add `tenacity` to `[project].dependencies` in `pyproject.toml` and sync the environment (`python scripts/make setup`).

## 2. HTTP client hardening

- [x] 2.1 Give the `httpx.Client` in `on_post_build` an explicit 30s timeout.
- [x] 2.2 Define the set of retryable conditions: `httpx.TimeoutException`, `httpx.ConnectError`, and responses with status `429`/`500`/`502`/`503`/`504`; wrap a retryable *response* in a sentinel exception so tenacity can retry on it and read `Retry-After`.

## 3. Retry helper (GET/PUT)

- [x] 3.1 Add a tenacity-based `_request_with_retry` (5 attempts, exponential backoff + jitter, cap ~30s) used for GET (fetch) and PUT (update, archive).
- [x] 3.2 Add a custom `wait` that honors a `Retry-After` value from a `429`, falling back to exponential+jitter; ensure non-`429` `4xx` are never retried.
- [x] 3.3 Route `_fetch_existing_pages`, the update (PUT) path in `_publish_units`, and `_archive_orphaned_page` through the retry helper. Keep archive failures best-effort (log-only) after retries.

## 4. Duplicate-safe POST (create)

- [x] 4.1 Add a bespoke create-with-retry: on a transient POST failure, re-fetch the Doc's pages and, if a page with the target `sub_title` exists, adopt its id (treat as success); otherwise re-POST with backoff.
- [x] 4.2 Wire the create path in `_publish_units` to use it, so a lost POST response can never create a second page with the same `sub_title`.

## 5. Failure semantics

- [x] 5.1 Ensure that once retries are exhausted, create/update still raise `PluginError` and abort the build (existing behavior preserved), and that deterministic `4xx` still surface immediately.

## 6. Tests

- [x] 6.1 Extend the `FakeClickUp` test harness to script per-request sequences (e.g. fail N times then succeed, or return a lost-response then reveal the created page on GET).
- [x] 6.2 Test: a transient timeout/5xx/429 is retried and then publishing succeeds without aborting.
- [x] 6.3 Test: `Retry-After` on a `429` is honored (waited on) before the retry.
- [x] 6.4 Test: a non-`429` `4xx` is not retried and surfaces immediately.
- [x] 6.5 Test: retries exhausted → `PluginError`/build abort.
- [x] 6.6 Test: a lost POST response whose page already exists is adopted by `sub_title` — no duplicate page is created.

## 7. Quality gates & docs

- [x] 7.1 Run `python scripts/make check-quality`, `check-types`, `check-docs`, and `test`; fix any findings.
- [x] 7.2 Update `README.md` "Known limitations" to note the retry/backoff resilience (transient 5xx/timeout/429 are retried; a longer timeout is used).

## Context

The plugin publishes one HTTP request per MkDocs page to ClickUp's v3 Pages API (see `_publish_units` / `_fetch_existing_pages` in `src/mkdocs_clickup/_internal/plugin.py`). For this repo's own docs that is ~15 sequential requests per build.

Empirically confirmed this session against workspace `90121909276` / doc `2kxuyd0w-532`: ClickUp returns **intermittent** read-timeouts and 5xx under that burst. Across three CI runs the publish job aborted at a *different* point each time (GET fetch → 500; `changelog.md` POST → 500; `contributing.md` POST → read-timeout). Isolation probes proved it is **not** content-specific: posting `changelog.md`'s exact generated Markdown directly returns 201, and a child page with `parent_page_id` + that content also returns 201. The failure "moves around" — the signature of transient server-side flakiness.

The current client is fragile by construction: `httpx.Client()` with the **default 5s timeout**, **no retries**, and **abort-on-first-failure** (`raise PluginError`). With ~15 requests, hitting one slow/failed request is nearly certain, and a single one sinks the whole publish.

Constraints:
- ClickUp exposes no batch endpoint (one call per page stays).
- Documented rate limit: 100 req/min on lower tiers, surfaced as `429` with `Retry-After` / `X-RateLimit-*` headers.
- The prior `add-clickup-idempotent-page-sync` change made publishing idempotent **between builds** by matching existing pages on `sub_title`; there is no in-build dedup.

## Goals / Non-Goals

**Goals:**
- Survive transient ClickUp failures (timeouts, 5xx, 429) so a normal build publishes reliably.
- Keep the change minimal and localized to the HTTP layer of `plugin.py`.
- Preserve the existing `sub_title`-keyed idempotency — retries must never create duplicate pages.
- Leave the "publish failures abort the build" contract intact: a failure that survives all retries is still fatal.

**Non-Goals:**
- Proactive rate-limit throttling / inter-request delays (reactive 429 handling only).
- Making per-page failures non-fatal (log + skip) — we deliberately keep abort-after-retries.
- Async/concurrent publishing or request batching.
- Changing how content is generated or matched.

## Decisions

**1. Use `tenacity` for retry orchestration** (new runtime dependency).
Rationale: a small, well-tested, zero-dependency library gives declarative stop/wait/retry policies and a clean custom-wait hook for `Retry-After`. Alternatives considered: hand-rolled retry loop (no dep, but reimplements backoff/jitter/attempt bookkeeping we'd want to test ourselves) and `httpx.HTTPTransport(retries=N)` (rejected — it only retries connection-level failures, **not** read-timeouts or 5xx *responses*, which are exactly our failure modes).

**2. Explicit 30s timeout** on the `httpx.Client` (up from the 5s default). Many "timeouts" observed were likely slowness, not outages; a longer ceiling reduces spurious retries.

**3. Retry policy**: 5 attempts total (1 + 4 retries), exponential backoff **with jitter**, cap ~30s. Retry on `httpx.TimeoutException`, `httpx.ConnectError` (transport errors), and responses whose status is `429`, `500`, `502`, `503`, `504`. Never retry other `4xx` — those are deterministic client errors and must surface immediately.

**4. `Retry-After`-aware wait for 429**: a custom tenacity `wait` callable inspects the retried outcome; when it carries a `Retry-After` value it waits that long, otherwise it falls back to the exponential+jitter policy. Retryable *responses* (not just exceptions) are turned into a sentinel exception so tenacity can retry on them and the wait callable can read the header. Reactive only — no proactive spacing between requests.

**5. Scope: every ClickUp call goes through retry** — GET (fetch existing pages), POST (create), PUT (update), and the best-effort archive PUT. The archive stays non-fatal (its failure is still only logged), but retrying it improves its odds.

**6. Failure semantics unchanged**: after retries are exhausted, raise `PluginError` and abort the build, exactly as today. The existing "Publish failures abort the build" requirement is preserved verbatim; we only insert retries *before* that final raise.

**7. Duplicate-safe POST (the subtle one)**: creating a page is non-idempotent. If ClickUp commits the create but the response is lost (timeout, or 5xx after commit), a blind retry would POST again and create a **second** page with the same `sub_title`. Because idempotency is only enforced across builds (via the next build's initial GET), that duplicate would match its own `sub_title`, escape orphan-archival, and linger. So POST gets a bespoke wrapper: on a transient POST failure, **re-fetch** the Doc's pages and look for a page with the target `sub_title`; if present, **adopt** its id and treat the create as succeeded; only if absent do we re-POST (with backoff). GET/PUT, being idempotent, use the plain tenacity retry. Alternative considered: idempotency key / dedup on next build (rejected — ClickUp exposes no idempotency-key mechanism, and letting duplicates land then cleaning up later reintroduces exactly the bug the previous change fixed).

## Risks / Trade-offs

- **Worst-case build time grows** (5 attempts × up to 30s per failing request) → Mitigated by capped attempts and jittered backoff; retries only trigger on actual failures, and the normal path is unchanged.
- **New dependency (`tenacity`)** → Low risk: mature, permissively licensed, no transitive deps; pinned via the existing dependency workflow.
- **Re-fetch on POST failure costs an extra GET** → Only on the (rare) transient-POST path; the correctness win (no duplicates) outweighs one extra request.
- **A genuinely-down ClickUp still fails the build** → Intended: after 5 attempts we treat it as a real failure and abort, consistent with the unchanged failure contract.
- **`Retry-After` could specify a long delay** → Acceptable and correct for rate-limit compliance; bounded in practice by ClickUp's limits and the 5-attempt cap.

## Migration Plan

Pure additive behavior change to the HTTP layer; no config, data, or spec-breaking changes. Existing successful publishes behave identically (retries never fire on the happy path). Rollback is reverting the `plugin.py` HTTP-layer edits and dropping the `tenacity` dependency.

## Open Questions

None — all design axes (library, timeout, attempts/backoff, retryable set, 429 handling, scope, failure semantics, POST duplicate-safety) were settled during exploration.

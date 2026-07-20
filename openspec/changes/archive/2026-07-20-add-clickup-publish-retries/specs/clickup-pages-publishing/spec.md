## ADDED Requirements

### Requirement: Transient ClickUp failures are retried before failing

The plugin SHALL retry a ClickUp API request that fails transiently, rather than aborting on the first failure. A failure is transient when it is a connection error, a read/connect timeout, or a response with status `429`, `500`, `502`, `503`, or `504`. The plugin SHALL make up to 5 total attempts (1 initial plus 4 retries) per request, waiting between attempts with exponential backoff plus jitter. This applies to every ClickUp call the plugin makes: fetching existing pages (GET), creating pages (POST), updating pages (PUT), and archiving orphaned pages (PUT). Only after all attempts are exhausted does the existing "Publish failures abort the build" requirement take effect (or, for archival, the existing best-effort behavior).

#### Scenario: A transient error is retried and then succeeds

- **WHEN** a ClickUp request fails with a timeout, connection error, or a `429`/`500`/`502`/`503`/`504` response, and a subsequent attempt succeeds
- **THEN** the plugin SHALL use the successful response and continue publishing, without aborting the build

#### Scenario: Retries are exhausted

- **WHEN** a ClickUp create or update request fails transiently on all 5 attempts
- **THEN** the plugin SHALL raise an error that aborts the build, per the existing "Publish failures abort the build" requirement

#### Scenario: Deterministic client errors are not retried

- **WHEN** a ClickUp request returns a non-`429` `4xx` response (for example `400`, `401`, or `404`)
- **THEN** the plugin SHALL NOT retry it and SHALL surface the failure immediately

### Requirement: Requests use an explicit timeout

The plugin SHALL configure its HTTP client with an explicit request timeout of 30 seconds, rather than relying on the client library's shorter default, so that a slow (but not failed) ClickUp response is not prematurely treated as a failure.

#### Scenario: A slow response within the timeout is honored

- **WHEN** ClickUp responds after longer than the library's default timeout but within 30 seconds
- **THEN** the plugin SHALL accept the response instead of timing out

### Requirement: Rate-limit responses honor Retry-After

When a retried response is a `429` (rate limited) and carries a `Retry-After` header, the plugin SHALL wait at least the indicated duration before the next attempt. When the header is absent, the plugin SHALL fall back to its exponential backoff. The plugin SHALL NOT add proactive delays between requests that are not rate limited.

#### Scenario: 429 with Retry-After

- **WHEN** a ClickUp request returns `429` with a `Retry-After` header
- **THEN** the plugin SHALL wait at least that long before retrying

#### Scenario: 429 without Retry-After

- **WHEN** a ClickUp request returns `429` with no `Retry-After` header
- **THEN** the plugin SHALL retry using its exponential backoff schedule

### Requirement: Page creation is duplicate-safe under retries

Because creating a page (POST) is not idempotent, the plugin SHALL NOT create a duplicate page when it retries a POST whose earlier attempt may have already been committed by ClickUp (for example when the response was lost to a timeout). Before re-sending a failed POST, the plugin SHALL re-fetch the Doc's pages and, if a page with the same `sub_title` now exists, adopt that page (use its id and treat the create as succeeded) instead of creating a second page. This preserves the `sub_title`-keyed idempotency the plugin relies on across builds.

#### Scenario: A lost POST response does not create a duplicate

- **WHEN** a POST to create a page fails transiently but ClickUp had already created the page, and the plugin retries
- **THEN** the plugin SHALL detect the existing page by its `sub_title`, adopt its id, and SHALL NOT create a second page with the same `sub_title`

#### Scenario: A genuinely uncreated page is retried

- **WHEN** a POST to create a page fails transiently and no page with that `sub_title` exists on re-fetch
- **THEN** the plugin SHALL re-send the POST to create the page

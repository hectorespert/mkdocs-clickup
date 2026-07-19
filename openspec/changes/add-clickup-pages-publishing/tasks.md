## 1. Dependencies and config

- [ ] 1.1 Add `httpx>=0.27` to `pyproject.toml`'s `dependencies`
- [ ] 1.2 Add `workspace_id` and `doc_id` as required `mkconf.Type(str)` fields on `_PluginConfig` (`src/mkdocs_clickup/_internal/config.py`)

## 2. Plugin implementation

- [ ] 2.1 In `on_config`, read `CLICKUP_API_TOKEN` from the environment and raise a `ValueError` (matching the existing `site_url` check's style) if unset; store it as `self._clickup_token`
- [ ] 2.2 Change `self._md_pages` from `dict[str, str]` to `dict[str, tuple[str, str]]` (title, markdown), updating `on_page_content` to store `(page.title or page.file.src_uri, page_md)`
- [ ] 2.3 Implement `on_post_build`: for each entry in `self._md_pages`, `POST` to `https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages` with `Authorization: {token}` header and JSON body `{"name": title, "content": markdown, "content_format": "text/md"}`, using a short-lived `httpx.Client()` as a context manager
- [ ] 2.4 On any non-2xx response or `httpx` request exception, raise `mkdocs.exceptions.PluginError` including the page's `src_uri` and the response status/body (or exception) in the message, aborting the rest of `on_post_build`

## 3. Tests

- [ ] 3.1 Test: `on_config` raises when `workspace_id` or `doc_id` is missing from plugin config
- [ ] 3.2 Test: `on_config` raises when `CLICKUP_API_TOKEN` is not set (use `monkeypatch.delenv`)
- [ ] 3.3 Test: `on_post_build` sends one create-page request per converted page, with correct URL, headers, and body (mock `httpx` — e.g. `httpx.MockTransport` or `respx`), asserting no `parent_page_id` is present in any request
- [ ] 3.4 Test: publishing the same page across two separate builds results in two separate create-page requests (no dedup/update logic)
- [ ] 3.5 Test: a non-2xx response from the mocked API raises `PluginError` and stops further page publishing

## 4. Docs

- [ ] 4.1 Update README.md's "Usage" section with the new required config (`workspace_id`, `doc_id`) and the `CLICKUP_API_TOKEN` environment variable, plus a note on the known always-creates/duplicates limitation

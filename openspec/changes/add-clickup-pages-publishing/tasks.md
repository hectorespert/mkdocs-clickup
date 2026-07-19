## 1. Dependencies and config

- [ ] 1.1 Add `httpx>=0.27` to `pyproject.toml`'s `dependencies`
- [ ] 1.2 Add `workspace_id` and `doc_id` as **optional** `mkconf.Optional(mkconf.Type(str))` fields on `_PluginConfig`; remove the `base_url` field (`src/mkdocs_clickup/_internal/config.py`)

## 2. Remove leftover llms.txt-era link rewriting

- [ ] 2.1 Remove the `site_url` check and `base_url` resolution from `on_config`, keeping only the `self._md_pages = {}` reset
- [ ] 2.2 Remove `_convert_to_absolute_links`/`_convert_to_absolute_link` from `plugin.py`, and drop the `base_uri`/`page_uri` parameters (and the call to `_convert_to_absolute_links`) from `_generate_page_markdown`
- [ ] 2.3 Delete `tests/test_link_conversion.py`

## 3. Plugin implementation

- [ ] 3.1 In `on_post_build`, first check `os.environ.get("PUBLISH_TO_CLICKUP")`; if unset/falsy, return immediately — no further validation, no HTTP calls
- [ ] 3.2 Still in `on_post_build`, once publishing is confirmed enabled: validate `workspace_id`, `doc_id`, and read `CLICKUP_API_TOKEN` from the environment, raising `mkdocs.exceptions.PluginError` if any are missing, before making any HTTP calls
- [ ] 3.3 Change `self._md_pages` from `dict[str, str]` to `dict[str, tuple[str, str]]` (title, markdown), updating `on_page_content` to store `(page.title or page.file.src_uri, page_md)`
- [ ] 3.4 Continue `on_post_build`: for each entry in `self._md_pages`, `POST` to `https://api.clickup.com/api/v3/workspaces/{workspace_id}/docs/{doc_id}/pages` with `Authorization: {token}` header and JSON body `{"name": title, "content": markdown, "content_format": "text/md"}`, using a short-lived `httpx.Client()` as a context manager
- [ ] 3.5 On any non-2xx response or `httpx` request exception, raise `mkdocs.exceptions.PluginError` including the page's `src_uri` and the response status/body (or exception) in the message, aborting the rest of `on_post_build`

## 4. Tests

- [ ] 4.1 Test: `on_post_build` makes no HTTP calls and raises no error when `PUBLISH_TO_CLICKUP` is unset, even if `workspace_id`/`doc_id`/token are otherwise valid
- [ ] 4.2 Test: with `PUBLISH_TO_CLICKUP` set, `on_post_build` raises `PluginError` when `workspace_id` or `doc_id` is missing from plugin config
- [ ] 4.3 Test: with `PUBLISH_TO_CLICKUP` set, `on_post_build` raises `PluginError` when `CLICKUP_API_TOKEN` is not set (use `monkeypatch.delenv`)
- [ ] 4.4 Test: with `PUBLISH_TO_CLICKUP` set and valid config, `on_post_build` sends one create-page request per converted page, with correct URL, headers, and body (mock `httpx` — e.g. `httpx.MockTransport` or `respx`), asserting no `parent_page_id` is present in any request
- [ ] 4.5 Test: a relative link in a page's source Markdown is preserved unmodified in the content sent to ClickUp
- [ ] 4.6 Test: publishing the same page across two separate builds (both with `PUBLISH_TO_CLICKUP` set) results in two separate create-page requests (no dedup/update logic)
- [ ] 4.7 Test: a non-2xx response from the mocked API raises `PluginError` and stops further page publishing

## 5. Docs

- [ ] 5.1 Update README.md's "Usage" section with the new optional-but-required-to-publish config (`workspace_id`, `doc_id`), the `CLICKUP_API_TOKEN` and `PUBLISH_TO_CLICKUP` environment variables, and notes on the two known v1 limitations: always-creates/duplicates, and links published as-authored (not rewritten)

## 1. Config schema

- [x] 1.1 Add `default = mkconf.Choice(("all", "none"), default="all")` to `_PluginConfig` in `src/mkdocs_clickup/_internal/config.py`.
- [x] 1.2 Add `include = mkconf.ListOfItems(mkconf.Type(str), default=[])` to `_PluginConfig`.
- [x] 1.3 Add `exclude = mkconf.ListOfItems(mkconf.Type(str), default=[])` to `_PluginConfig`.

## 2. Page-selection logic

- [x] 2.1 In `plugin.py`, add `_is_page_included(page: Page, *, default: str, include: list[str], exclude: list[str]) -> bool` implementing the resolution order: front matter `clickup` (if present, `True`/`False`) > `exclude` pattern match (via `fnmatch.fnmatch(page.file.src_uri, pattern)`) > `include` pattern match > `default == "all"`.
- [x] 2.2 In `on_page_content`, call `_is_page_included` first; if it returns `False`, return `html` unchanged without calling `_generate_page_markdown` or storing into `self._md_pages`.
- [x] 2.3 Add the `import fnmatch` (or equivalent) needed by 2.1.

## 3. Anchor-detection fix

- [x] 3.1 Change `_find_index_child(section)` to `_find_index_child(section, published_uris: set[str])`, requiring `_is_index_page(child) and child.file.src_uri in published_uris` for a child to count as the section's real anchor.
- [x] 3.2 Update `_build_publish_units`'s `anchor()` closure to pass `set(md_pages)` (the published `src_uri`s) through to `_find_index_child`.
- [x] 3.3 Verify (via a new test, see 4.5) that an excluded `index.md`/`README.md` falls back to a placeholder anchor instead of being selected, and that sibling pages are parented to the placeholder.

## 4. Tests

- [x] 4.1 Test: a page with front matter `clickup: false` is excluded (not published, not present in any POST/PUT body) even though `default` is `"all"`.
- [x] 4.2 Test: a page with front matter `clickup: true` is published even when `default` is `"none"` and no `include` pattern matches it.
- [x] 4.3 Test: `exclude` pattern match excludes a page under `default: "all"`.
- [x] 4.4 Test: `include` pattern match includes a page under `default: "none"`.
- [x] 4.5 Test: a page matching both an `include` and an `exclude` pattern is excluded (exclude wins).
- [x] 4.6 Test: a monorepo-shaped alias-prefixed pattern (e.g. `exclude: ["internal-repo/*"]`) matches a nested page (`internal-repo/sub/deep/page.md`), confirming `*` crosses `/`.
- [x] 4.7 Test: `default: "all"` with no patterns/front-matter overrides publishes every page (regression test for backward compatibility, equivalent to today's behavior).
- [x] 4.8 Test: `default: "none"` with no patterns/front-matter overrides publishes nothing.
- [x] 4.9 Test: a section's `index.md` excluded (via front matter or pattern) falls back to a placeholder anchor; sibling pages are parented to the placeholder, not to the excluded page.
- [x] 4.10 Test: a page previously published, now excluded on a later build, is archived by the existing orphan-archival mechanism (confirms no regression / validates the "no new code needed" design decision).
- [x] 4.11 Test: an excluded page's conversion is skipped entirely — e.g. assert a Mermaid-diagram-containing excluded page never triggers the Mermaid renderer (monkeypatch/spy to confirm no call), demonstrating the build-cost savings.

## 5. Documentation

- [x] 5.1 Update README to document `default`, `include`, `exclude`, and the front-matter `clickup` key, including the resolution order and the `fnmatch`-crosses-`/` pattern semantics with a concrete example.
- [x] 5.2 Add a monorepo-oriented example to the README showing `exclude: ["internal-repo/*"]` bulk-excluding an aggregated sub-repo's subtree.

## 6. Validation

- [x] 6.1 Run `python scripts/make test` and confirm all tests (existing and new) pass. (57/57 pass)
- [x] 6.2 Run `python scripts/make check` and confirm quality/types/docs pass. (all pass on every supported Python version; `check-api` fails only due to a pre-existing, unrelated `griffecli` environment issue, reproduced identically on `main` before this change)

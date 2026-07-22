## Why

The plugin currently publishes every page MkDocs builds, with no way to exclude any of them — the spec says so explicitly ("There is no page-selection or filtering configuration in this capability"). This is a real limitation for two use cases: a site with pages that shouldn't reach ClickUp (internal notes, drafts) and, more concretely, a monorepo setup (`mkdocs-monorepo-plugin`, already analyzed in the archived `document-monorepo-plugin-compat` change) where a root build aggregates several independently-maintained sub-repos and needs to bulk-exclude or bulk-include whole sub-repos it doesn't control the content of.

## What Changes

- The plugin config gains `default` (`"all"` or `"none"`, default `"all"` — fully backward-compatible), `include` (list of patterns), and `exclude` (list of patterns).
- A page's inclusion is resolved in this order, most specific wins: (1) an explicit `clickup: true`/`clickup: false` in the page's front matter, (2) a match against `exclude` patterns, (3) a match against `include` patterns, (4) the `default` config value.
- Patterns match against a page's `src_uri` using `fnmatch` semantics, where `*` crosses `/` (deliberately not gitignore-style) — chosen so a single pattern like `"internal-repo/*"` can bulk-select an entire monorepo-aggregated sub-repo's subtree.
- An excluded page's HTML→Markdown conversion is skipped entirely in `on_page_content` (not just excluded from publishing afterward), so filtering also saves the cost of Mermaid rendering / SVG rasterization for pages that were never going to be published.
- **Bug fix bundled into this change**: `_find_index_child`'s nav-Section-anchor detection currently checks only whether a candidate child is named `index.md`/`README.md`, with no awareness of whether that page actually got published. Once pages can be filtered out, an excluded `index.md` could otherwise be selected as a section's anchor even though it has no corresponding ClickUp page, breaking other pages' `parent_page_id`. This change makes anchor detection check the actually-published page set (`self._md_pages`) too.
- No change to orphan-archival: a previously-published page that becomes excluded on a later build is simply absent from the current build's identifier set, and the plugin's existing orphan-archival mechanism already archives it, same as a renamed/deleted source file.

## Capabilities

### Modified Capabilities
- `clickup-pages-publishing`: replaces the "All built pages are published" requirement with real page-selection behavior (front matter override, include/exclude patterns, configurable default), and adds a requirement that nav-Section anchor detection only considers pages that are actually going to be published.

## Impact

- `src/mkdocs_clickup/_internal/config.py` — add `default`, `include`, `exclude` options.
- `src/mkdocs_clickup/_internal/plugin.py` — new page-selection check in `on_page_content` (skips conversion+storage for excluded pages); `_find_index_child`/`anchor()` gains awareness of the published page set.
- Tests — new coverage for front matter override, pattern matching (including the monorepo-shaped alias-prefix case), both `default` modes, the anchor-fix regression case (excluded `index.md`), and confirming an excluded-then-republished page is still archived via the existing orphan mechanism.
- README — document the three config options and the resolution order, with a monorepo-oriented example.

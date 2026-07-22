## Context

Today `on_page_content` (`plugin.py`) unconditionally converts every page's HTML to Markdown and stores it in `self._md_pages`, keyed by `src_uri`; `on_post_build` then turns every entry into a publish unit via `_build_publish_units`. There is no concept of "this page should not be published." The plugin's other config (`workspace_id`, `doc_id`, `token`, `publish`, `autoclean`, `preprocess`) lives in `_PluginConfig` (`config.py`); none of it is list- or pattern-typed today.

Two concrete drivers: (1) ordinary sites with pages that shouldn't reach ClickUp (drafts, internal notes), and (2) `mkdocs-monorepo-plugin` setups (analyzed in the archived `document-monorepo-plugin-compat` change), where a root build aggregates several independently-maintained sub-repos, each getting an alias-prefixed `src_uri` (e.g. `internal-repo/index.md`, `internal-repo/sub/deep/page.md`). In that setup, bulk-excluding a whole sub-repo by front matter isn't always possible — the sub-repo may not even be owned by whoever configures the root build.

## Goals / Non-Goals

**Goals:**
- Let a page opt out (or, in `default: none` mode, opt in) via front matter, with no new parsing (MkDocs already parses front matter into `page.meta`).
- Let the root `mkdocs.yml` bulk-select whole subtrees via patterns, without touching the pages themselves — the monorepo case's actual requirement.
- Support both a permissive default (`all`, backward-compatible) and a restrictive default (`none`), since the user confirmed wanting both immediately rather than deferring `none`.
- Skip the cost of HTML→Markdown conversion (including Mermaid rendering and SVG rasterization) for excluded pages, not just skip publishing them.
- Fix nav-Section anchor detection so it can't select an excluded page as an anchor.

**Non-Goals:**
- No change to orphan-archival logic — it already does the right thing for a page that becomes excluded (see Decisions).
- No new pattern syntax beyond `fnmatch`. No gitignore-style `**`/`*` distinction.
- No section-level (as opposed to page-level or pattern-level) filtering primitive — a whole section is filtered by patterns matching all its pages' `src_uri`s, not by a separate "exclude this Section" mechanism.

## Decisions

### Resolution order: front matter > exclude pattern > include pattern > default
```
if page.meta has an explicit `clickup` key (True/False):
    use it
elif src_uri matches any `exclude` pattern:
    False
elif src_uri matches any `include` pattern:
    True
else:
    default == "all"
```
Front matter wins because it's the most specific, deliberate signal from whoever owns that individual page. `exclude` is checked before `include` so that if the same page matches both lists (a plausible authoring mistake, or a deliberate "include this whole tree except this one item" pattern pair), the safer, more restrictive interpretation wins.

Rejected alternative: giving `include` precedence over `exclude`. This would make it impossible to carve a single exception out of an included subtree (e.g. `include: ["docs/*"]`, `exclude: ["docs/wip.md"]`) without reordering — exclude-wins is the more useful and more common precedent (`.gitignore`-adjacent tools generally treat the more specific/later-declared rule as authoritative, and here "the thing that says no" is the more specific intent when both fire).

### Pattern matching: `fnmatch`, not gitignore semantics
`fnmatch.fnmatch(src_uri, pattern)` treats `*` as matching any run of characters, including `/`. This means `"internal-repo/*"` matches both `internal-repo/index.md` and `internal-repo/sub/deep/page.md` with no `**` needed — exactly the shape of a monorepo-plugin alias-prefixed subtree. This is a deliberate divergence from gitignore-style globbing (where `*` stops at `/`), and must be called out clearly in the README so it doesn't surprise anyone bringing gitignore intuition.

Rejected alternative: `pathlib.PurePosixPath.match()` or a gitignore-style library (e.g. `pathspec`, already a transitive dependency of MkDocs itself). Rejected because the primary use case (bulk-selecting an entire aggregated subtree with one simple pattern) is exactly what plain `fnmatch` gives for free, and adding gitignore-style `**`-vs-`*` semantics would need a new dependency and more config-surface explanation for no benefit to the target use case.

### Config shape
```python
default = mkconf.Choice(("all", "none"), default="all")
include = mkconf.ListOfItems(mkconf.Type(str), default=[])
exclude = mkconf.ListOfItems(mkconf.Type(str), default=[])
```
Verified against the installed MkDocs version: `Choice` validates against a fixed set of values; `ListOfItems(Type(str), default=[])` validates a homogeneous list of strings, defaulting to empty. Both are existing MkDocs primitives — no new dependency.

### Filtering happens in `on_page_content`, before conversion
The selection check (a new `_is_page_included(page, config) -> bool` helper) runs at the top of `on_page_content`, before `_generate_page_markdown` is called. If it returns `False`, `on_page_content` returns early without converting or storing anything in `self._md_pages`. This means an excluded page's Mermaid rendering / SVG rasterization / image embedding never runs — filtering is also a build-time-saving mechanism for pages that were never going to be published, not merely a post-hoc publish filter.

### Anchor-detection fix: `_find_index_child` must know what actually got published
`_find_index_child(section)` currently returns any child satisfying `_is_index_page(item)` (a name check against `item.file.src_uri`), independent of whether that child is present in `self._md_pages`. Once pages can be excluded, an excluded `index.md`/`README.md` could still be selected as its Section's anchor, and `_build_publish_units` would compute sibling pages' `parent_page_id` pointing at a ClickUp page that was never created that build — a silent broken hierarchy, not a crash (nothing raises; the `parent_page_id` value would just reference a nonexistent or stale page).

Fix: change `_find_index_child`'s signature to also accept the set of actually-published `src_uri`s (`published_uris: set[str]`, i.e. `set(md_pages)` — already computed as a side effect of the dict `_build_publish_units` already receives) and require `_is_index_page(child) and child.file.src_uri in published_uris`. An excluded index page then falls back to the placeholder-anchor path exactly like a genuinely-absent index page does today — no separate "was this excluded" check is duplicated at the anchor layer; it just asks "is this actually in the published set," which is correct regardless of *why* a page might be missing (filtered by front matter, by pattern, or by some future mechanism).

### Orphan-archival requires no change
`on_post_build` already computes `current_identifiers = set(units)` and archives (best-effort) any previously-published page whose `sub_title` isn't in that set. A page that becomes excluded on a later build is, from this mechanism's point of view, indistinguishable from a page whose source file was renamed or deleted — it's simply absent from `units`. No new code is needed; this is called out here so it's understood as a deliberate design consequence, not an oversight, and so a test can assert it explicitly.

## Risks / Trade-offs

- **[Risk] `exclude`-wins-over-`include` could surprise someone expecting `include` to be the stronger, more explicit "yes"** → Mitigated by documenting the precedence order explicitly in the README and spec; this is a one-time learning cost, not an ongoing footgun once understood.
- **[Risk] `fnmatch`'s `*`-crosses-`/` behavior could surprise anyone expecting gitignore semantics** → Mitigated by an explicit README callout with a side-by-side example.
- **[Risk] A page matching neither pattern list nor front matter, under `default: none`, silently never reaches ClickUp** → This is the intended behavior of `default: none`, not a bug, but it's worth a README example showing the "curated opt-in" use case so it doesn't read as a foot-gun.
- **[Risk] Skipping conversion in `on_page_content` for excluded pages means excluded pages never get an entry in `self._md_pages` at all, including their `edit_url`/`section`/title** → this is fine because nothing downstream needs that data for a page that's never published; it's the same shape as the plugin's existing behavior when `publish` itself is `false` (nothing is stored... actually, note: today `_md_pages` is populated regardless of `publish`, since `on_page_content` doesn't check `self.config.publish` at all. This change only skips storage for pages *excluded by filtering*, not a broader change to when `_md_pages` is populated relative to `publish`.)

## Migration Plan

Fully additive and backward-compatible: `default` defaults to `"all"`, `include`/`exclude` default to empty lists, so a `mkdocs.yml` with no filtering config behaves exactly as before. No breaking change, no version-bump implication beyond a normal minor/feature release.

## Open Questions

None outstanding — the resolution order, pattern semantics, and both `default` modes were confirmed by the user during exploration.

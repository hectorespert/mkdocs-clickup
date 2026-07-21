## Context

Target setup: a root repo running `mkdocs build` with both
`mkdocs-monorepo-plugin` and `clickup` (this plugin) enabled. The root
`mkdocs.yml` nav uses `!include ../repo-v1/mkdocs.yml` / `!include
../repo-v2/mkdocs.yml` to pull in docs from separate git repos (each with its
own `mkdocs.yml`, checked out locally before the build runs). Goal: a single
ClickUp Doc with the full merged hierarchy.

Traced monorepo-plugin's actual source (not just its README, which doesn't
document hook mechanics) to ground this analysis:

- `plugin.py`: registers `on_config`, `on_pre_page`, `on_serve`, and a bare
  `post_build` (not `on_post_build` — likely dead/legacy-named and never
  invoked by current MkDocs; irrelevant to us either way since we don't touch
  `docs_dir`).
- `parser.py`: resolves `!include`/`*include` into a merged `nav`, prefixing
  every link with an `alias` derived from the included site's `site_name`
  (slugified).
- `merger.py`: physically copies every included `docs_dir` into one temp
  directory (`docs_dir/<alias>/...`) and swaps `config["docs_dir"]` to it
  before MkDocs core builds `File`/`Page` objects.
- `edit_uri.py`: in `on_pre_page`, restores `page.file.abs_src_path` to the
  real source file and recomputes `page.edit_url`: passthrough for pages
  under the root `docs_dir`; `repo_url_of_subrepo + edit_uri + relative_path`
  for pages whose sub-project declares its own `repo_url`; **`None`** if the
  sub-project has no `repo_url`.

Our plugin's relevant surface (`src/mkdocs_clickup/_internal/plugin.py`):
`on_page_content` (per-page, keys `self._md_pages` by `page.file.src_uri`,
reads `page.parent` and `page.edit_url`) and `on_post_build`
(`_build_publish_units` walks `page.parent` Section chain to build
parent/anchor relationships; `_notice()` renders the edit link only when
`edit_url` is truthy).

## Goals / Non-Goals

**Goals:**
- Establish, with evidence from both codebases, whether `mkdocs-clickup`
  needs any change to work correctly under `mkdocs-monorepo-plugin`.
- Record the mechanics precisely enough that a future implementer (or test
  author) doesn't have to re-derive them.

**Non-Goals:**
- Implementing anything in `mkdocs-clickup` — analysis found none is needed.
- Solving monorepo-plugin's own limitations (e.g. alias collisions, cross-repo
  relative links) — those are upstream concerns, not ours.
- Designing CI orchestration for checking out the separate sub-repos before
  the build — orthogonal to this plugin.

## Decisions

**No code change to `_build_publish_units` / `_generate_page_markdown`.**
Both operate purely on MkDocs' already-resolved `Page`/`Section` objects and
never touch `docs_dir` or the filesystem layout directly. Because
monorepo-plugin fully resolves the merged `nav` and swaps `docs_dir` inside
its own `on_config`, by the time our `on_page_content`/`on_post_build` run,
the tree looks like an entirely ordinary (if deep) MkDocs nav. Alternative
considered: proactively special-case alias-wrapper sections — rejected,
because the existing placeholder-anchor mechanism (`_placeholder_sub_title`,
`_find_index_child`) already handles "Section with no index child" generically,
which is exactly the shape an alias wrapper has.

**Treat `sub_title` (= `src_uri`, alias-prefixed e.g. `v1/index.md`) as stable
identity.** It's deterministic across builds as long as the `!include` config
and each sub-project's alias (`site_name`) don't change — same guarantee we
already rely on for non-monorepo builds. No change needed to the
`page_by_sub_title` matching in `on_post_build`.

**Leave `edit_url = None` handling as-is.** `_notice()` already renders the
notice without an edit link when `edit_url` is falsy
(`plugin.py:373-389`). monorepo-plugin can legitimately set `None` for a
whole sub-project's pages, and that's the correct degradation, not a bug to
paper over.

## Risks / Trade-offs

- **[Risk] A sub-repo's `mkdocs.yml` has no `repo_url`** → its pages publish
  to ClickUp without an "Edit the source" link (silent, not a crash).
  Mitigation: document in the README that each `!include`d sub-repo should
  set its own `repo_url` (and ideally `edit_uri`) for working edit links —
  authoring guidance for the sub-repos, not a code fix.
- **[Risk] No regression test exercises a monorepo-shaped nav** — a Section
  with no `index.md`/`README.md` child, nested 2+ levels (the shape every
  `!include` alias produces), combined with a page whose `edit_url` is
  `None`. If a future refactor of `_build_publish_units` or `_notice()`
  regresses this shape, nothing would catch it today. Mitigation: add a
  fixture-driven test before relying on this in production (see Open
  Questions / not scoped to this change).
- **[Risk] Alias collisions across independently-maintained sub-repos**
  (`Merger.merge()` raises `SystemExit(1)` on duplicate `site_name` slugs) —
  upstream monorepo-plugin behavior, fails the whole build loudly before our
  plugin ever runs. Not mitigated here; just noted so it isn't mistaken for a
  `mkdocs-clickup` bug if it happens.

## Migration Plan

N/A — no code or config migration; this change is documentation-only.

## Open Questions

- Do we want to formally add the monorepo-shaped nav test fixture (Section
  without index, 2+ levels deep, `edit_url=None`) as its own follow-up
  change, or fold it into whatever change next touches
  `_build_publish_units`/`_notice()`?
- Do we want a "Compatibility" note in the README documenting the
  per-sub-repo `repo_url` recommendation, or is that better placed in this
  project's own docs site once the monorepo is actually stood up?

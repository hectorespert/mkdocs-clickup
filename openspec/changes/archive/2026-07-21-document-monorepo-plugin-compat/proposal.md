## Why

We're about to run `mkdocs-clickup` in a real monorepo setup that also uses
[`backstage/mkdocs-monorepo-plugin`](https://github.com/backstage/mkdocs-monorepo-plugin)
(multiple separate git repos, each with its own `mkdocs.yml`, combined via
`!include` into one root build that publishes a single ClickUp Doc with full
hierarchy). Before touching code, we traced monorepo-plugin's actual
mechanics (`on_config`, `on_pre_page`, `merger.py`, `edit_uri.py`) against how
`mkdocs-clickup` uses MkDocs hooks, to ground what's actually compatible
versus what's a real gap.

## What Changes

- No behavior change to `mkdocs-clickup` itself — the analysis found the
  plugin is already compatible with monorepo-plugin's merged-nav/merged-`docs_dir`
  approach, with one caveat that's a sub-repo authoring concern, not ours (see
  `design.md`).
- Capture the analysis in `design.md` as a durable reference: how
  monorepo-plugin merges `docs_dir` and rewrites `nav`, why our `sub_title`
  identifiers (`src_uri`) stay stable across builds, why `edit_url` can
  legitimately be `None` per page, and why our nav-Section anchor/placeholder
  logic already covers the alias-wrapper sections monorepo-plugin introduces.
- Identify one concrete, low-risk gap worth closing later: no test today
  exercises a monorepo-shaped nav (a Section with no `index.md`/`README.md`
  child, nested 2+ levels, some pages with `edit_url = None`).

## Capabilities

### New Capabilities

(none — no new behavior)

### Modified Capabilities

(none — no requirement changes; this change only records analysis for
reference and flags a future test-coverage improvement)

## Impact

- Docs only: adds `design.md` to this change directory for future reference.
- No changes to `src/mkdocs_clickup/`.
- Flags a follow-up (not part of this change): add regression test coverage
  for monorepo-shaped nav trees in `tests/`, and a README note recommending
  each included sub-repo declare its own `repo_url` for working ClickUp edit
  links.

"""Tests for page-selection/filtering: front matter, include/exclude patterns, and default."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from mkdocs.commands.build import build

from mkdocs_clickup._internal import plugin as plugin_module
from tests.test_plugin import FakeClickUp

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig


def _base_config(
    *,
    default: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict:
    """Return a fresh plugin config dict (MkDocs mutates it in place during validation)."""
    clickup_config: dict = {"workspace_id": "ws1", "doc_id": "doc1", "token": "token", "publish": True}
    if default is not None:
        clickup_config["default"] = default
    if include is not None:
        clickup_config["include"] = include
    if exclude is not None:
        clickup_config["exclude"] = exclude
    return {"plugins": [{"clickup": clickup_config}]}


@pytest.fixture(name="clickup")
def fixture_clickup(monkeypatch: pytest.MonkeyPatch) -> FakeClickUp:
    """Patch `httpx.Client` to talk to an in-memory fake ClickUp Pages API."""
    fake = FakeClickUp()
    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(fake.handle)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return fake


def _published_sub_titles(clickup: FakeClickUp) -> set[str]:
    return {json.loads(r.content)["sub_title"] for r in clickup.requests if r.method == "POST"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "index.md": "# Home",
                "draft.md": "---\nclickup: false\n---\n\n# Draft",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_front_matter_false_excludes_page(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """A page with front matter `clickup: false` is excluded even though `default` is `all`."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == {"index.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(default="none"),
            "pages": {
                "index.md": "# Home",
                "special.md": "---\nclickup: true\n---\n\n# Special",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_front_matter_true_includes_page_under_default_none(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
) -> None:
    """A page with front matter `clickup: true` is published even when `default` is `none`."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == {"special.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(exclude=["drafts/*"]),
            "pages": {
                "index.md": "# Home",
                "drafts/wip.md": "# WIP",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_exclude_pattern_excludes_matching_page(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """An `exclude` pattern match excludes a page under `default: all`."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == {"index.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(default="none", include=["public/*"]),
            "pages": {
                "index.md": "# Home",
                "public/page.md": "# Public",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_include_pattern_includes_matching_page_under_default_none(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
) -> None:
    """An `include` pattern match includes a page under `default: none`."""
    build(config=mkdocs_conf)
    sub_titles = _published_sub_titles(clickup)
    assert "public/page.md" in sub_titles
    assert "index.md" not in sub_titles


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(include=["shared/*"], exclude=["shared/secret.md"]),
            "pages": {
                "shared/secret.md": "# Secret",
                "shared/open.md": "# Open",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_exclude_wins_over_include_on_overlap(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """A page matching both `include` and `exclude` is excluded - exclude takes precedence."""
    build(config=mkdocs_conf)
    sub_titles = _published_sub_titles(clickup)
    assert "shared/open.md" in sub_titles
    assert "shared/secret.md" not in sub_titles


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(exclude=["internal-repo/*"]),
            "pages": {
                "internal-repo/index.md": "# Internal Home",
                "internal-repo/sub/deep/page.md": "# Deep",
                "public.md": "# Public",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_pattern_matches_across_path_segments(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """A monorepo-shaped alias-prefixed pattern matches nested pages - `*` crosses `/` under fnmatch."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == {"public.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {"index.md": "# Home", "page1.md": "# Page 1"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_default_all_publishes_every_page(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """`default: all` with no patterns/overrides publishes every page (backward-compat regression test)."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == {"index.md", "page1.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(default="none"),
            "pages": {"index.md": "# Home", "page1.md": "# Page 1"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_default_none_publishes_nothing(mkdocs_conf: MkDocsConfig, clickup: FakeClickUp) -> None:
    """`default: none` with no patterns/overrides publishes nothing."""
    build(config=mkdocs_conf)
    assert _published_sub_titles(clickup) == set()


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "topics/index.md": "---\nclickup: false\n---\n\n# Topics Index",
                "topics/a.md": "# A",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_excluded_index_falls_back_to_placeholder_anchor(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
) -> None:
    """A section's excluded index.md is not used as anchor; siblings are parented to a placeholder instead."""
    build(config=mkdocs_conf)

    creates = [json.loads(r.content) for r in clickup.requests if r.method == "POST"]
    sub_titles = {body["sub_title"] for body in creates}
    assert "topics/index.md" not in sub_titles
    placeholder_sub_titles = [s for s in sub_titles if s.startswith("__section__:")]
    assert len(placeholder_sub_titles) == 1
    placeholder_id = next(p["id"] for p in clickup.pages.values() if p["sub_title"] == placeholder_sub_titles[0])
    a_body = next(body for body in creates if body["sub_title"] == "topics/a.md")
    assert a_body["parent_page_id"] == placeholder_id


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_page_excluded_after_previous_publish_is_archived(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
) -> None:
    """A page published in a prior build, now excluded, is archived by the existing orphan mechanism."""
    build(config=mkdocs_conf)
    page_id = next(p["id"] for p in clickup.pages.values() if p["sub_title"] == "index.md")

    Path(mkdocs_conf.docs_dir, "index.md").write_text("---\nclickup: false\n---\n\n# Hello")
    build(config=mkdocs_conf)

    assert clickup.pages[page_id].get("archived") is True


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(exclude=["excluded.md"]),
            "pages": {
                "index.md": "# Home",
                "excluded.md": "# Excluded\n\n```mermaid\ngraph TD;\n    A --> B;\n```",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_excluded_page_conversion_is_skipped(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An excluded page's HTML-to-Markdown conversion never runs at all."""
    converted_paths: list[str] = []
    original = plugin_module._generate_page_markdown

    def spy(html: str, **kwargs: object) -> str:
        converted_paths.append(kwargs["path"])  # type: ignore[arg-type]
        return original(html, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(plugin_module, "_generate_page_markdown", spy)
    build(config=mkdocs_conf)

    assert converted_paths == ["index.html"]
    assert _published_sub_titles(clickup) == {"index.md"}

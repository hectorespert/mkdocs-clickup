"""Tests for the plugin's ClickUp publishing behavior."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from mkdocs.commands.build import build
from mkdocs.exceptions import Abort, PluginError

from mkdocs_clickup._internal.plugin import _fetch_existing_pages

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

    from mkdocs_clickup._internal.plugin import MkdocsClickUpPlugin


class FakeClickUp:
    """In-memory fake of the ClickUp Pages API, stateful across multiple builds."""

    def __init__(self) -> None:
        """Start with no requests recorded and no pages seeded."""
        self.requests: list[httpx.Request] = []
        self.pages: dict[str, dict] = {}
        self.archive_fails = False
        self._next_id = 0

    def seed(self, *, sub_title: str, name: str = "", content: str = "", parent_page_id: str | None = None) -> str:
        """Pre-populate an existing ClickUp page, returning its page_id."""
        self._next_id += 1
        page_id = f"seed-{self._next_id}"
        self.pages[page_id] = {
            "id": page_id,
            "name": name,
            "sub_title": sub_title,
            "content": content,
            "parent_page_id": parent_page_id,
        }
        return page_id

    def _tree(self) -> list[dict]:
        """Build the nested-tree GET response: root pages, each with recursive `pages` children."""
        children_by_parent: dict[str | None, list[dict]] = {}
        for page in self.pages.values():
            children_by_parent.setdefault(page.get("parent_page_id"), []).append(page)

        def build_nodes(parent_id: str | None) -> list[dict]:
            return [{**page, "pages": build_nodes(page["id"])} for page in children_by_parent.get(parent_id, [])]

        return build_nodes(None)

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Route a captured request to fake GET/POST/PUT behavior."""
        self.requests.append(request)

        if request.method == "GET":
            return httpx.Response(200, json=self._tree())

        body = json.loads(request.content)

        if request.method == "POST":
            self._next_id += 1
            page_id = f"page-{self._next_id}"
            page = {"id": page_id, "parent_page_id": None, **body}
            self.pages[page_id] = page
            return httpx.Response(201, json=page)

        if request.method == "PUT":
            page_id = request.url.path.rsplit("/", 1)[-1]
            if body.get("archived") and self.archive_fails:
                return httpx.Response(500, text="archive failed")
            page = self.pages.setdefault(page_id, {"id": page_id, "parent_page_id": None})
            page.update(body)
            return httpx.Response(200, json=page)

        raise AssertionError(f"Unexpected method {request.method}")


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


def _base_config() -> dict:
    """Return a fresh plugin config dict (MkDocs mutates it in place during validation)."""
    return {
        "plugins": [
            {
                "clickup": {
                    "workspace_id": "ws1",
                    "doc_id": "doc1",
                },
            },
        ],
    }


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_no_publish_without_env_var(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` makes no requests and raises nothing when PUBLISH_TO_CLICKUP is unset."""
    monkeypatch.delenv("PUBLISH_TO_CLICKUP", raising=False)
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    build(config=mkdocs_conf)
    assert clickup.requests == []


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": {"plugins": [{"clickup": {}}]}, "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_missing_workspace_or_doc_id_raises(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` raises when workspace_id/doc_id are missing, if publishing is enabled."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    plugin: MkdocsClickUpPlugin = mkdocs_conf.plugins["clickup"]  # type: ignore[assignment]
    plugin.on_config(mkdocs_conf)
    with pytest.raises(PluginError, match="workspace_id"):
        plugin.on_post_build(config=mkdocs_conf)
    assert clickup.requests == []


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_missing_token_raises(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` raises when CLICKUP_API_TOKEN is unset, if publishing is enabled."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    plugin: MkdocsClickUpPlugin = mkdocs_conf.plugins["clickup"]  # type: ignore[assignment]
    plugin.on_config(mkdocs_conf)
    with pytest.raises(PluginError, match="CLICKUP_API_TOKEN"):
        plugin.on_post_build(config=mkdocs_conf)
    assert clickup.requests == []


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "index.md": "# Home",
                "page1.md": "# Page 1\n\nSome content.",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_publishes_each_page(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every converted page is created (no prior match), flat, with sub_title set to its src_uri."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    creates = [r for r in clickup.requests if r.method == "POST"]
    assert len(creates) == 2
    sub_titles = set()
    for request in creates:
        assert request.url == "https://api.clickup.com/api/v3/workspaces/ws1/docs/doc1/pages"
        assert request.headers["Authorization"] == "token"
        body = json.loads(request.content)
        assert "parent_page_id" not in body
        assert body["content_format"] == "text/md"
        sub_titles.add(body["sub_title"])
    assert sub_titles == {"index.md", "page1.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "index.md": "# Home\n\n[Other page](page1.md)",
                "page1.md": "# Page 1",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_relative_link_preserved(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative links are published exactly as authored, with no rewriting."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    bodies = [json.loads(r.content) for r in clickup.requests if r.method != "GET"]
    index_body = next(body for body in bodies if body["name"] == "Home")
    assert "(page1.md)" in index_body["content"] or "(page1/)" in index_body["content"]


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_matched_page_is_updated_in_place(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current page whose src_uri matches an existing page's sub_title is PUT, not POST."""
    page_id = clickup.seed(sub_title="index.md", name="Old title", content="Old content")
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    non_get = [r for r in clickup.requests if r.method != "GET"]
    assert len(non_get) == 1
    request = non_get[0]
    assert request.method == "PUT"
    assert request.url.path.endswith(f"/{page_id}")
    body = json.loads(request.content)
    assert body["sub_title"] == "index.md"
    assert body["name"] == "Hello"


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_unmatched_page_is_created(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A current page with no matching sub_title is created, with sub_title set to its src_uri."""
    clickup.seed(sub_title="other.md", name="Unrelated")
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    creates = [r for r in clickup.requests if r.method == "POST"]
    assert len(creates) == 1
    body = json.loads(creates[0].content)
    assert body["sub_title"] == "index.md"


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_orphaned_page_is_archived(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An existing page whose sub_title matches no current src_uri is archived."""
    orphan_id = clickup.seed(sub_title="removed.md", name="Removed page")
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    archive_requests = [
        r for r in clickup.requests if r.method == "PUT" and r.url.path.endswith(f"/{orphan_id}")
    ]
    assert len(archive_requests) == 1
    body = json.loads(archive_requests[0].content)
    assert body["archived"] is True
    assert clickup.pages[orphan_id]["archived"] is True


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_orphan_archive_failure_does_not_abort_build(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed archive attempt on an orphan is logged, not raised - the build still succeeds."""
    clickup.seed(sub_title="removed.md", name="Removed page")
    clickup.archive_fails = True
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")

    build(config=mkdocs_conf)  # must not raise

    creates = [r for r in clickup.requests if r.method == "POST"]
    assert len(creates) == 1


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_updates_same_page_on_rebuild(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing the same page across two builds updates the same ClickUp page, not a new one."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)
    build(config=mkdocs_conf)

    creates = [r for r in clickup.requests if r.method == "POST"]
    updates = [r for r in clickup.requests if r.method == "PUT"]
    assert len(creates) == 1
    assert len(updates) == 1
    (page_id,) = clickup.pages.keys()
    assert updates[0].url.path.endswith(f"/{page_id}")


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "a/index.md": "# Overview",
                "b/index.md": "# Overview",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_title_collision_does_not_cross_match(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two pages sharing a title but with different src_uri are matched/updated independently."""
    page_a = clickup.seed(sub_title="a/index.md", name="Overview", content="Old A")
    page_b = clickup.seed(sub_title="b/index.md", name="Overview", content="Old B")
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    updates = [r for r in clickup.requests if r.method == "PUT"]
    assert len(updates) == 2
    updated_ids = {r.url.path.rsplit("/", 1)[-1] for r in updates}
    assert updated_ids == {page_a, page_b}
    for request in updates:
        body = json.loads(request.content)
        page_id = request.url.path.rsplit("/", 1)[-1]
        expected_sub_title = "a/index.md" if page_id == page_a else "b/index.md"
        assert body["sub_title"] == expected_sub_title


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_publish_failure_raises_and_stops(
    mkdocs_conf: MkDocsConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-2xx response while creating/updating raises PluginError and stops publishing further pages."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(500, text="internal error")

    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")

    plugin: MkdocsClickUpPlugin = mkdocs_conf.plugins["clickup"]  # type: ignore[assignment]
    plugin.on_config(mkdocs_conf)
    plugin._md_pages = {
        "index.md": ("Home", "# Home", None),
        "page1.md": ("Page 1", "# Page 1", None),
    }

    with pytest.raises(PluginError, match="500"):
        plugin.on_post_build(config=mkdocs_conf)

    non_get_calls = [c for c in calls if c.method != "GET"]
    assert len(non_get_calls) == 1


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "guide/index.md": "# Guide",
                "guide/other.md": "# Other",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_page_nested_under_real_index_anchor(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page whose section has a real index page is parented to it; no placeholder is created."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    bodies = {json.loads(r.content)["sub_title"]: json.loads(r.content) for r in clickup.requests if r.method == "POST"}
    assert set(bodies) == {"guide/index.md", "guide/other.md"}
    assert "parent_page_id" not in bodies["guide/index.md"]
    index_id = next(p["id"] for p in clickup.pages.values() if p["sub_title"] == "guide/index.md")
    assert bodies["guide/other.md"]["parent_page_id"] == index_id


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "topics/a.md": "# A",
                "topics/b.md": "# B",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_page_nested_under_placeholder_anchor(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A section with no index page gets an empty placeholder anchor; its pages are parented to it."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    creates = [json.loads(r.content) for r in clickup.requests if r.method == "POST"]
    sub_titles = {body["sub_title"] for body in creates}
    assert {"topics/a.md", "topics/b.md"}.issubset(sub_titles)
    placeholder_sub_titles = [s for s in sub_titles if s.startswith("__section__:")]
    assert len(placeholder_sub_titles) == 1
    placeholder_body = next(body for body in creates if body["sub_title"] == placeholder_sub_titles[0])
    assert placeholder_body["content"] == ""
    placeholder_id = next(p["id"] for p in clickup.pages.values() if p["sub_title"] == placeholder_sub_titles[0])
    a_body = next(body for body in creates if body["sub_title"] == "topics/a.md")
    b_body = next(body for body in creates if body["sub_title"] == "topics/b.md")
    assert a_body["parent_page_id"] == placeholder_id
    assert b_body["parent_page_id"] == placeholder_id


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"topics/a.md": "# A"}}],
    indirect=["mkdocs_conf"],
)
def test_placeholder_is_updated_not_duplicated_on_rebuild(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same section's placeholder anchor is updated, not recreated, on a second build."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)
    build(config=mkdocs_conf)

    placeholder_ids = {p["id"] for p in clickup.pages.values() if p["sub_title"].startswith("__section__:")}
    assert len(placeholder_ids) == 1
    updates = [r for r in clickup.requests if r.method == "PUT"]
    assert any(r.url.path.endswith(f"/{next(iter(placeholder_ids))}") for r in updates)


def test_fetch_existing_pages_flattens_nested_tree() -> None:
    """`_fetch_existing_pages` recursively flattens a multi-level nested response."""
    nested = [
        {
            "id": "root-1",
            "sub_title": "root.md",
            "pages": [
                {
                    "id": "child-1",
                    "sub_title": "child.md",
                    "pages": [
                        {"id": "grandchild-1", "sub_title": "grandchild.md"},
                    ],
                },
            ],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json=nested)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages = _fetch_existing_pages(client, "https://example.test/pages", {})

    assert {p["id"] for p in pages} == {"root-1", "child-1", "grandchild-1"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"topics/a.md": "# A"}}],
    indirect=["mkdocs_conf"],
)
def test_reparented_when_section_gains_index_page(
    mkdocs_conf: MkDocsConfig,
    clickup: FakeClickUp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a section gains a real index page, siblings are re-parented and the old placeholder is archived."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    placeholder = next(p for p in clickup.pages.values() if p["sub_title"].startswith("__section__:"))
    a_page_id = next(p["id"] for p in clickup.pages.values() if p["sub_title"] == "topics/a.md")
    assert clickup.pages[a_page_id]["parent_page_id"] == placeholder["id"]

    Path(mkdocs_conf.docs_dir, "topics", "index.md").write_text("# Topics")
    build(config=mkdocs_conf)

    index_page = next(p for p in clickup.pages.values() if p["sub_title"] == "topics/index.md")
    assert clickup.pages[a_page_id]["parent_page_id"] == index_page["id"]
    assert clickup.pages[placeholder["id"]]["archived"] is True


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {"topics/index.md": "# Topics", "topics/a.md": "# A"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_reparenting_failure_raises_and_aborts(
    mkdocs_conf: MkDocsConfig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A PUT that fails while re-parenting a matched page is a normal, build-aborting failure."""
    existing_id = "existing-a"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": existing_id,
                        "sub_title": "topics/a.md",
                        "name": "A",
                        "content": "",
                        "parent_page_id": None,
                    },
                ],
            )
        if request.method == "POST":
            return httpx.Response(201, json={"id": "new-index-page"})
        if request.method == "PUT":
            return httpx.Response(500, text="internal error")
        raise AssertionError(f"Unexpected method {request.method}")

    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    caplog.set_level(logging.ERROR)

    with pytest.raises(Abort):
        build(config=mkdocs_conf)

    assert "Failed to publish page 'topics/a.md' to ClickUp: 500" in caplog.text

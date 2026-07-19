"""Tests for the plugin's ClickUp publishing behavior."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from mkdocs.commands.build import build
from mkdocs.exceptions import PluginError

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

    def seed(self, *, sub_title: str, name: str = "", content: str = "") -> str:
        """Pre-populate an existing ClickUp page, returning its page_id."""
        self._next_id += 1
        page_id = f"seed-{self._next_id}"
        self.pages[page_id] = {"id": page_id, "name": name, "sub_title": sub_title, "content": content}
        return page_id

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Route a captured request to fake GET/POST/PUT behavior."""
        self.requests.append(request)

        if request.method == "GET":
            return httpx.Response(200, json=list(self.pages.values()))

        body = json.loads(request.content)

        if request.method == "POST":
            self._next_id += 1
            page_id = f"page-{self._next_id}"
            page = {"id": page_id, **body}
            self.pages[page_id] = page
            return httpx.Response(201, json=page)

        if request.method == "PUT":
            page_id = request.url.path.rsplit("/", 1)[-1]
            if body.get("archived") and self.archive_fails:
                return httpx.Response(500, text="archive failed")
            page = self.pages.setdefault(page_id, {"id": page_id})
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
        "index.md": ("Home", "# Home"),
        "page1.md": ("Page 1", "# Page 1"),
    }

    with pytest.raises(PluginError, match="500"):
        plugin.on_post_build(config=mkdocs_conf)

    non_get_calls = [c for c in calls if c.method != "GET"]
    assert len(non_get_calls) == 1

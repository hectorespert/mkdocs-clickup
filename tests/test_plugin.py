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


@pytest.fixture(name="clickup_requests")
def fixture_clickup_requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Capture every request made through `httpx.Client`, returning 201 Created for each."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json={"id": "page-id"})

    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return captured


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
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` makes no requests and raises nothing when PUBLISH_TO_CLICKUP is unset."""
    monkeypatch.delenv("PUBLISH_TO_CLICKUP", raising=False)
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    build(config=mkdocs_conf)
    assert clickup_requests == []


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": {"plugins": [{"clickup": {}}]}, "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_missing_workspace_or_doc_id_raises(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` raises when workspace_id/doc_id are missing, if publishing is enabled."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    plugin: MkdocsClickUpPlugin = mkdocs_conf.plugins["clickup"]  # type: ignore[assignment]
    plugin.on_config(mkdocs_conf)
    with pytest.raises(PluginError, match="workspace_id"):
        plugin.on_post_build(config=mkdocs_conf)
    assert clickup_requests == []


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_missing_token_raises(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`on_post_build` raises when CLICKUP_API_TOKEN is unset, if publishing is enabled."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    plugin: MkdocsClickUpPlugin = mkdocs_conf.plugins["clickup"]  # type: ignore[assignment]
    plugin.on_config(mkdocs_conf)
    with pytest.raises(PluginError, match="CLICKUP_API_TOKEN"):
        plugin.on_post_build(config=mkdocs_conf)
    assert clickup_requests == []


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
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every converted page is sent as a flat create-page request, with no parent_page_id."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    assert len(clickup_requests) == 2
    for request in clickup_requests:
        assert request.url == "https://api.clickup.com/api/v3/workspaces/ws1/docs/doc1/pages"
        assert request.headers["Authorization"] == "token"
        body = json.loads(request.content)
        assert "parent_page_id" not in body
        assert body["content_format"] == "text/md"


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
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative links are published exactly as authored, with no rewriting."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    bodies = [json.loads(request.content) for request in clickup_requests]
    index_body = next(body for body in bodies if body["name"] == "Home")
    assert "(page1.md)" in index_body["content"] or "(page1/)" in index_body["content"]


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_duplicate_pages_on_rebuild(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing the same page across two builds creates two separate pages (no dedup)."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)
    build(config=mkdocs_conf)
    assert len(clickup_requests) == 2


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello"}}],
    indirect=["mkdocs_conf"],
)
def test_publish_failure_raises_and_stops(
    mkdocs_conf: MkDocsConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-2xx response raises PluginError and stops publishing further pages."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
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
    assert len(calls) == 1

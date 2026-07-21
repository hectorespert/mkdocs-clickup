"""Tests for rendering Mermaid diagrams locally and embedding them as images."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from mkdocs.commands.build import build
from pymdownx.superfences import fence_code_format

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig


def _config() -> dict:
    """A fresh plugin config dict with the Mermaid custom fence configured."""
    return {
        "plugins": [{"clickup": {"workspace_id": "ws1", "doc_id": "doc1"}}],
        "markdown_extensions": [
            {
                "pymdownx.superfences": {
                    "custom_fences": [
                        {"name": "mermaid", "class": "mermaid", "format": fence_code_format},
                    ],
                },
            },
        ],
    }


@pytest.fixture(name="clickup_requests")
def fixture_clickup_requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Patch `httpx.Client` to record requests and return a fake 201/200 for everything."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(201, json={"id": "page-1"})

    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, *args: object, **kwargs: object) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return requests


def _published_content(requests: list[httpx.Request], *, sub_title: str) -> str:
    for request in requests:
        if request.method != "POST":
            continue
        body = json.loads(request.content)
        if body["sub_title"] == sub_title:
            return str(body["content"])
    raise AssertionError(f"No published page found with sub_title={sub_title!r}")


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _config(),
            "pages": {"index.md": "# Hello\n\n```mermaid\ngraph TD;\n    A --> B;\n```"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_renderable_mermaid_fence_is_embedded(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A renderable Mermaid fence is embedded as a `data:image/png` URI, not published as code."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests, sub_title="index.md")
    assert "data:image/png;base64," in content
    assert "graph TD" not in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _config(),
            "pages": {"index.md": "# Hello\n\n```mermaid\nthis is not valid mermaid syntax {{{\n```"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_unrenderable_mermaid_fence_falls_back_to_code(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrenderable Mermaid fence falls back to a plain fenced code block; the build does not abort."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)  # must not raise

    content = _published_content(clickup_requests, sub_title="index.md")
    assert "data:image/png" not in content
    assert "this is not valid mermaid syntax" in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _config(),
            "pages": {
                "broken.md": "# Broken\n\n```mermaid\nthis is not valid mermaid syntax {{{\n```",
                "fine.md": "# Fine\n\nJust regular content.",
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_unrenderable_diagram_does_not_block_other_pages(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page with an unrenderable diagram doesn't stop other pages from publishing successfully."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)  # must not raise

    sub_titles = {json.loads(r.content)["sub_title"] for r in clickup_requests if r.method == "POST"}
    assert sub_titles == {"broken.md", "fine.md"}


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _config(), "pages": {"index.md": "# Hello\n\nJust regular content, no diagrams."}}],
    indirect=["mkdocs_conf"],
)
def test_page_without_mermaid_is_unaffected(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page with no Mermaid content publishes normally, unaffected by the new rendering step."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests, sub_title="index.md")
    assert "Just regular content" in content

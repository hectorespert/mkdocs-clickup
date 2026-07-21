"""Tests for embedding images and content SVGs as inline data URIs."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from mkdocs.commands.build import build
from mkdocs.exceptions import Abort, PluginError

from mkdocs_clickup._internal import plugin as plugin_module

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

# A minimal valid 1x1 red pixel PNG.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
)


def _base_config(*, autoclean: bool | None = None, site_url: str | None = "https://example.org/") -> dict:
    """Return a fresh plugin config dict (MkDocs mutates it in place during validation)."""
    clickup_config: dict = {"workspace_id": "ws1", "doc_id": "doc1"}
    if autoclean is not None:
        clickup_config["autoclean"] = autoclean
    config: dict = {"plugins": [{"clickup": clickup_config}]}
    if site_url is not None:
        config["site_url"] = site_url
    return config


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


def _published_content(requests: list[httpx.Request]) -> str:
    body = next(json.loads(r.content) for r in requests if r.method == "POST")
    return str(body["content"])


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello\n\n![Local](pic.png)"}}],
    indirect=["mkdocs_conf"],
)
def test_local_image_embedded_as_data_uri(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local image is read from disk and embedded as a base64 data URI with the correct MIME type."""
    Path(mkdocs_conf.docs_dir, "pic.png").write_bytes(_PNG_BYTES)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    expected_data_uri = f"data:image/png;base64,{base64.b64encode(_PNG_BYTES).decode('ascii')}"
    assert expected_data_uri in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(autoclean=False), "pages": {"index.md": "# Hello\n\n![Local](pic.png)"}}],
    indirect=["mkdocs_conf"],
)
def test_local_image_embedded_regardless_of_autoclean(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Images are embedded whether `autoclean` is enabled or disabled - it no longer controls this."""
    Path(mkdocs_conf.docs_dir, "pic.png").write_bytes(_PNG_BYTES)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    assert "data:image/png;base64," in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {"index.md": '# Hello\n\n<svg viewBox="0 0 2 2"><rect width="2" height="2"/></svg>'},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_content_svg_embedded_as_data_uri(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inline content SVG (no twemoji class) survives autoclean and is rasterized to a PNG data URI."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    assert "data:image/png;base64," in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {
                "index.md": (
                    "# Hello\n\n"
                    '<svg class="twemoji" viewBox="0 0 2 2"><rect width="2" height="2"/></svg>\n\n'
                    '<img class="twemoji" src="icon.png">'
                ),
            },
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_decorative_twemoji_icons_still_removed(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A decorative twemoji-classed SVG or image (emoji / :material-*: icon shortcode) is still removed."""
    Path(mkdocs_conf.docs_dir, "icon.png").write_bytes(_PNG_BYTES)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    assert "data:image/svg+xml" not in content
    assert "data:image/png" not in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [
        {
            "config": _base_config(),
            "pages": {"index.md": "# Hello\n\n![Remote](https://example.test/remote.png)"},
        },
    ],
    indirect=["mkdocs_conf"],
)
def test_remote_image_left_untouched(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already-absolute/remote image src is published unchanged, never embedded."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    assert "https://example.test/remote.png" in content
    assert "data:" not in content


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(), "pages": {"index.md": "# Hello\n\n![Broken](missing.png)"}}],
    indirect=["mkdocs_conf"],
)
def test_missing_local_image_aborts_build(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local image reference that resolves to no file aborts the build."""
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")

    with pytest.raises(Abort):
        build(config=mkdocs_conf)


@pytest.mark.parametrize(
    "mkdocs_conf",
    [{"config": _base_config(site_url=None), "pages": {"index.md": "# Hello\n\n![Local](pic.png)"}}],
    indirect=["mkdocs_conf"],
)
def test_embedding_works_without_site_url(
    mkdocs_conf: MkDocsConfig,
    clickup_requests: list[httpx.Request],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding a local image does not depend on `site_url` being configured."""
    Path(mkdocs_conf.docs_dir, "pic.png").write_bytes(_PNG_BYTES)
    monkeypatch.setenv("PUBLISH_TO_CLICKUP", "1")
    monkeypatch.setenv("CLICKUP_API_TOKEN", "token")
    build(config=mkdocs_conf)

    content = _published_content(clickup_requests)
    assert "data:image/png;base64," in content


def test_content_svg_rasterization_preserves_attribute_case(monkeypatch: pytest.MonkeyPatch) -> None:
    """Case-sensitive SVG attributes (viewBox, markerWidth, ...) reach resvg_py unmangled.

    Regression test for a real bug: BeautifulSoup's `html.parser` lowercases attribute names on
    parse (`viewBox` -> `viewbox`), corrupting case-sensitive SVG attributes and breaking the
    rendered diagram - live-verified against a real ClickUp workspace. `_rasterize_content_svgs`
    must run on the raw HTML string, before any souping, to avoid this.
    """
    captured: dict[str, str] = {}

    def fake_svg_to_bytes(*, svg_string: str, **_kwargs: object) -> list[int]:
        captured["svg_string"] = svg_string
        return list(_PNG_BYTES)

    monkeypatch.setattr(plugin_module.resvg_py, "svg_to_bytes", fake_svg_to_bytes)

    html = '<svg viewBox="0 0 10 10"><marker markerWidth="5" refX="2"></marker></svg>'
    plugin_module._rasterize_content_svgs(html, page_dest_uri="index.html")

    assert "viewBox=" in captured["svg_string"]
    assert "markerWidth=" in captured["svg_string"]
    assert "refX=" in captured["svg_string"]


def test_malformed_content_svg_raises_plugin_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A content SVG that resvg_py can't rasterize raises a PluginError naming the page."""

    def failing_svg_to_bytes(**_kwargs: object) -> list[int]:
        raise ValueError("boom")

    monkeypatch.setattr(plugin_module.resvg_py, "svg_to_bytes", failing_svg_to_bytes)

    html = "<svg><rect/></svg>"
    with pytest.raises(PluginError, match=re.escape("index.html")):
        plugin_module._rasterize_content_svgs(html, page_dest_uri="index.html")

# MkDocs plugin that publishes documentation to ClickUp Pages.

from __future__ import annotations

import base64
import mimetypes
import os
import posixpath
import re
from itertools import chain
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

import httpx
import mdformat
import resvg_py
from bs4 import BeautifulSoup as Soup
from bs4 import Tag
from markdownify import ATX, MarkdownConverter
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.exceptions import PluginError
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from mkdocs_clickup._internal.config import _PluginConfig
from mkdocs_clickup._internal.logger import _get_logger
from mkdocs_clickup._internal.preprocess import _preprocess, autoclean

if TYPE_CHECKING:
    from typing import Any

    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import File, Files
    from mkdocs.structure.nav import Section
    from mkdocs.structure.pages import Page


_logger = _get_logger(__name__)

_PUBLISH_ENV_VAR = "PUBLISH_TO_CLICKUP"
_TOKEN_ENV_VAR = "CLICKUP_API_TOKEN"  # noqa: S105 (this is an env var name, not a secret)


class MkdocsClickUpPlugin(BasePlugin[_PluginConfig]):
    """The MkDocs plugin to publish documentation to ClickUp Pages.

    Publishing only happens when the `PUBLISH_TO_CLICKUP` environment variable is
    set to a truthy value (e.g. `PUBLISH_TO_CLICKUP=1 mkdocs build`). This is
    deliberate: `mkdocs serve` and `mkdocs gh-deploy` fire the same build hooks as
    `mkdocs build`, so publishing unconditionally would create ClickUp pages on
    every local save during development.

    Check the [Developing Plugins](https://www.mkdocs.org/user-guide/plugins/#developing-plugins) page of `mkdocs`
    for more information about its plugin system.
    """

    _md_pages: dict[str, tuple[str, str, Section | None, str | None]]

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        """Reset the per-build page cache.

        Hook for the [`on_config` event](https://www.mkdocs.org/user-guide/plugins/#on_config).

        Arguments:
            config: The MkDocs config object.

        Returns:
            The same, untouched config.
        """
        self._md_pages = {}
        return config

    def on_page_content(self, html: str, *, page: Page, files: Files, **kwargs: Any) -> str | None:  # noqa: ARG002
        """Convert page content into Markdown and store the result for later use.

        Hook for the [`on_page_content` event](https://www.mkdocs.org/user-guide/plugins/#on_page_content).

        Parameters:
            html: The rendered HTML.
            page: The page object.
            files: The collection of all files in the site, used to resolve local image sources.
        """
        page_md = _generate_page_markdown(
            html,
            should_autoclean=self.config.autoclean,
            preprocess=self.config.preprocess,
            path=page.file.dest_uri,
            files=files,
        )
        title = page.title if page.title is not None else page.file.src_uri
        self._md_pages[page.file.src_uri] = (str(title), page_md, page.parent, page.edit_url)

        return html

    def on_post_build(self, *, config: MkDocsConfig, **kwargs: Any) -> None:  # noqa: ARG002
        """Publish converted pages to ClickUp, if publishing is enabled.

        Hook for the [`on_post_build` event](https://www.mkdocs.org/user-guide/plugins/#on_post_build).

        Parameters:
            config: MkDocs configuration.
        """
        if not os.environ.get(_PUBLISH_ENV_VAR):
            return

        if not self.config.workspace_id or not self.config.doc_id:
            raise PluginError(
                f"'workspace_id' and 'doc_id' must be set in the 'clickup' plugin configuration "
                f"when {_PUBLISH_ENV_VAR} is set",
            )
        token = os.environ.get(_TOKEN_ENV_VAR)
        if not token:
            raise PluginError(f"The {_TOKEN_ENV_VAR} environment variable must be set to publish to ClickUp")

        url = (
            f"https://api.clickup.com/api/v3/workspaces/{self.config.workspace_id}"
            f"/docs/{self.config.doc_id}/pages"
        )
        headers = {"Authorization": token}

        with httpx.Client(timeout=_TIMEOUT) as client:
            existing_pages = _fetch_existing_pages(client, url, headers)
            page_by_sub_title = {page["sub_title"]: page for page in existing_pages if page.get("sub_title")}

            units = _build_publish_units(self._md_pages)
            _publish_units(client, url, headers, units, page_by_sub_title)

            current_identifiers = set(units)
            for page in existing_pages:
                sub_title = page.get("sub_title")
                if sub_title and sub_title not in current_identifiers:
                    _archive_orphaned_page(client, url, headers, page)


_TIMEOUT = httpx.Timeout(30.0)
"""Explicit per-request timeout, well above httpx's 5s default, so a slow (but not failed) ClickUp response isn't prematurely treated as a failure."""

_MAX_ATTEMPTS = 5
"""Total attempts per request (1 initial + 4 retries) before giving up."""

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
"""Response statuses treated as transient and retried; other 4xx are deterministic and surface immediately."""


class _RetryableResponse(Exception):  # noqa: N818
    """Wraps a response with a transient status so `tenacity` can retry on it.

    Not a real error condition on its own - it exists only to turn a retryable
    HTTP *response* into something `tenacity`'s exception-based retry can see,
    and to carry the `Retry-After` hint to the wait policy.
    """

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Retryable ClickUp response: {response.status_code}")

    @property
    def retry_after(self) -> float | None:
        """The `Retry-After` header as seconds, if present and integer-valued."""
        value = self.response.headers.get("Retry-After")
        if value is not None and value.strip().isdigit():
            return float(value.strip())
        return None


_exponential_wait = wait_random_exponential(multiplier=1, max=30)
"""Jittered exponential backoff, capped at 30s, used when no `Retry-After` applies."""


def _wait_policy(retry_state: Any) -> float:
    """Honor a `429`'s `Retry-After`, else fall back to jittered exponential backoff."""
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    if isinstance(exception, _RetryableResponse) and exception.retry_after is not None:
        return exception.retry_after
    return _exponential_wait(retry_state)


_retry_transient = retry(
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=_wait_policy,
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, _RetryableResponse)),
    reraise=True,
)
"""Shared `tenacity` policy: retry transient transport errors and retryable statuses."""


@_retry_transient
def _send(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send one request, raising `_RetryableResponse` for transient statuses so the policy retries."""
    response = client.request(method, url, **kwargs)
    if response.status_code in _RETRYABLE_STATUS:
        raise _RetryableResponse(response)
    return response


def _request_with_retry(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send a request with retries, returning the final response (even if its status is an error).

    Transport errors (timeouts, connection failures) propagate after the retries
    are exhausted; a retryable *status* that never recovered is handed back as a
    normal response so the caller's `raise_for_status()` produces the usual error.

    Parameters:
        client: The HTTP client to use.
        method: The HTTP method.
        url: The request URL.
        **kwargs: Extra arguments forwarded to the client (e.g. `headers`, `json`).

    Returns:
        The final HTTP response.
    """
    try:
        return _send(client, method, url, **kwargs)
    except _RetryableResponse as exhausted:
        return exhausted.response


def _find_page_by_sub_title(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    sub_title: str,
) -> dict[str, Any] | None:
    """Re-fetch the Doc's pages and return the one with the given `sub_title`, if any."""
    response = _request_with_retry(client, "GET", url, headers=headers)
    response.raise_for_status()
    for page in _flatten_pages(response.json()):
        if page.get("sub_title") == sub_title:
            return page
    return None


def _create_page(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    sub_title: str,
    body: dict[str, Any],
) -> str:
    """Create a page with duplicate-safe retries, returning its ClickUp `page_id`.

    Creating a page (POST) is not idempotent: if ClickUp commits the create but
    the response is lost, a blind retry would make a second page with the same
    `sub_title`. So on every attempt after the first, re-fetch the Doc first and,
    if a page with this `sub_title` already exists, adopt it instead of re-POSTing.

    Parameters:
        client: The HTTP client to use.
        url: The ClickUp Doc's pages endpoint.
        headers: Request headers, including auth.
        sub_title: The page's `sub_title` (its MkDocs `src_uri`), used to detect an already-created page.
        body: The create request body.

    Returns:
        The created (or adopted) page's `page_id`.
    """
    posted = False

    @_retry_transient
    def _attempt() -> httpx.Response | dict[str, Any]:
        nonlocal posted
        if posted:
            existing = _find_page_by_sub_title(client, url, headers, sub_title)
            if existing is not None:
                return existing
        posted = True
        response = client.post(url, headers=headers, json=body)
        if response.status_code in _RETRYABLE_STATUS:
            raise _RetryableResponse(response)
        return response

    try:
        result: httpx.Response | dict[str, Any] = _attempt()
    except _RetryableResponse as exhausted:
        result = exhausted.response
    if isinstance(result, dict):  # adopted an already-created page
        return result["id"]
    result.raise_for_status()
    return result.json()["id"]


def _fetch_existing_pages(client: httpx.Client, url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch every page currently in the configured ClickUp Doc.

    Parameters:
        client: The HTTP client to use.
        url: The ClickUp Doc's pages endpoint.
        headers: Request headers, including auth.

    Returns:
        The existing page objects, as returned by ClickUp, flattened to a single
        list regardless of nesting depth.
    """
    try:
        response = _request_with_retry(client, "GET", url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise PluginError(
            f"Failed to fetch existing ClickUp pages: {error.response.status_code} {error.response.text}",
        ) from error
    except httpx.HTTPError as error:
        raise PluginError(f"Failed to fetch existing ClickUp pages: {error}") from error
    return _flatten_pages(response.json())


def _flatten_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively flatten ClickUp's nested page tree into a single flat list.

    `GET .../docs/{doc_id}/pages` only lists root pages at the top level; every
    page's children are nested under its own `pages` key. A page with a
    `parent_page_id` never appears at the top level, so callers that need to
    match against *every* existing page (not just root ones) must flatten first.

    Parameters:
        pages: A list of page objects, each possibly holding nested children
            under a `pages` key.

    Returns:
        Every page in the tree (root and nested, at any depth) as a flat list.
    """
    flat: list[dict[str, Any]] = []
    for page in pages:
        flat.append(page)
        flat.extend(_flatten_pages(page.get("pages") or []))
    return flat


_PLACEHOLDER_SUB_TITLE_PREFIX = "__section__:"


def _is_index_page(item: Any) -> bool:
    """Whether a nav item is a Page backed by an `index.md` or `README.md` file."""
    if not item.is_page:
        return False
    return PurePosixPath(item.file.src_uri).name in ("index.md", "README.md")


def _find_index_child(section: Any) -> str | None:
    """Return the src_uri of a Section's direct index/README child page, if any.

    Parameters:
        section: The MkDocs nav Section to inspect.

    Returns:
        The child page's `src_uri`, or `None` if the section has no such child.
    """
    for child in section.children:
        if _is_index_page(child):
            return child.file.src_uri
    return None


def _section_breadcrumb(section: Any) -> str:
    """Build a stable ancestor-to-self breadcrumb of a Section's titles."""
    titles = []
    node: Any = section
    while node is not None:
        titles.append(node.title)
        node = node.parent
    return "/".join(reversed(titles))


def _placeholder_sub_title(section: Any) -> str:
    """Synthetic `sub_title` identifying a Section's placeholder anchor page.

    Prefixed so it can never collide with a real MkDocs page's `sub_title`,
    which is always a `src_uri`.
    """
    return f"{_PLACEHOLDER_SUB_TITLE_PREFIX}{_section_breadcrumb(section)}"


_NOTICE_TEXT = (
    "⚠️ **Auto-generated from code. Do not edit here.** "
    "Changes made in ClickUp are overwritten on the next publish."
)
"""Fixed do-not-edit notice reinforcing that the source repository, not ClickUp, is the source of truth."""


def _notice(edit_url: str | None) -> str:
    """Render the do-not-edit notice as a Markdown blockquote.

    Includes an "Edit the source" link when an edit URL is available, pointing
    readers at the source file rather than ClickUp.

    Parameters:
        edit_url: The page's source edit URL, or `None` when unavailable
            (no `repo_url`/`edit_uri`, or a section placeholder with no source).

    Returns:
        The notice as a single-line Markdown blockquote.
    """
    text = _NOTICE_TEXT
    if edit_url:
        text += f" [Edit the source]({edit_url})"
    return f"> {text}"


def _build_publish_units(
    md_pages: dict[str, tuple[str, str, Section | None, str | None]],
) -> dict[str, tuple[str, str, str | None]]:
    """Resolve every converted page and nav Section anchor into publish units.

    Each MkDocs `nav` Section resolves to an "anchor": a real `index.md`/
    `README.md` child page if one exists among the section's direct children,
    otherwise a synthetic placeholder page (notice-only content, matched across
    builds by a title-breadcrumb-derived `sub_title`). A page or placeholder's
    `parent_page_id` is the anchor of its own containing Section - except a
    page that *is* its Section's own anchor, which is parented to the
    Section's parent's anchor instead, to avoid a page being its own parent.

    Every unit's content is prefixed with the do-not-edit notice (see `_notice`),
    linking to the page's source when an edit URL is available.

    Parameters:
        md_pages: Mapping of `src_uri` to `(title, markdown, section, edit_url)`,
            where `section` is the page's nav parent (`None` for a top-level
            page) and `edit_url` is the page's source edit URL (`None` if none).

    Returns:
        Mapping of identifier (a page's `src_uri`, or a placeholder's synthetic
        `sub_title`) to `(title, content, parent_key)`, where `parent_key` is
        another unit's identifier, or `None` for a top-level unit.
    """
    anchor_of: dict[Any, str] = {}
    units: dict[str, tuple[str, str, str | None]] = {}

    def anchor(section: Any) -> str | None:
        if section is None:
            return None
        if section in anchor_of:
            return anchor_of[section]
        index_src_uri = _find_index_child(section)
        if index_src_uri is not None:
            anchor_of[section] = index_src_uri
            return index_src_uri
        placeholder_key = _placeholder_sub_title(section)
        anchor_of[section] = placeholder_key
        parent_key = anchor(section.parent)
        units[placeholder_key] = (section.title, _notice(None), parent_key)
        return placeholder_key

    for src_uri, (title, markdown, section, edit_url) in md_pages.items():
        if section is None:
            parent_key = None
        elif anchor(section) == src_uri:
            parent_key = anchor(section.parent)
        else:
            parent_key = anchor(section)
        units[src_uri] = (title, f"{_notice(edit_url)}\n\n{markdown}", parent_key)

    return units


def _publish_units(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    units: dict[str, tuple[str, str, str | None]],
    page_by_sub_title: dict[str, dict[str, Any]],
) -> None:
    """Create or update every publish unit, publishing parents before children.

    Parameters:
        client: The HTTP client to use.
        url: The ClickUp Doc's pages endpoint.
        headers: Request headers, including auth.
        units: Publish units as returned by `_build_publish_units`.
        page_by_sub_title: Existing ClickUp pages, keyed by `sub_title`.
    """
    published_ids: dict[str, str] = {}

    def publish(key: str) -> str:
        if key in published_ids:
            return published_ids[key]
        title, content, parent_key = units[key]
        parent_id = publish(parent_key) if parent_key is not None else None
        matched = page_by_sub_title.get(key)
        body: dict[str, Any] = {"name": title, "content": content, "content_format": "text/md", "sub_title": key}
        if parent_id is not None:
            body["parent_page_id"] = parent_id
        elif matched and matched.get("parent_page_id") is not None:
            body["parent_page_id"] = None
        try:
            if matched:
                response = _request_with_retry(client, "PUT", f"{url}/{matched['id']}", headers=headers, json=body)
                response.raise_for_status()
                page_id = matched["id"]
            else:
                page_id = _create_page(client, url, headers, key, body)
        except httpx.HTTPStatusError as error:
            raise PluginError(
                f"Failed to publish page '{key}' to ClickUp: {error.response.status_code} {error.response.text}",
            ) from error
        except httpx.HTTPError as error:
            raise PluginError(f"Failed to publish page '{key}' to ClickUp: {error}") from error
        _logger.debug(f"Published page '{key}' to ClickUp")
        published_ids[key] = page_id
        return page_id

    for key in units:
        publish(key)


def _archive_orphaned_page(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    page: dict[str, Any],
) -> None:
    """Best-effort archive a ClickUp page whose MkDocs source no longer exists.

    `archived` isn't part of ClickUp's documented Edit Page schema (only `name`, `sub_title`,
    `content`, `content_edit_mode`, and `content_format` are documented), though it was verified
    empirically to remove a page from subsequent listings. Because it's undocumented, a failure
    here is logged and never fails the build - an orphan simply stays visible, same as before.
    """
    page_id = page["id"]
    src_uri = page.get("sub_title")
    body = {
        "name": page.get("name", ""),
        "content": page.get("content", ""),
        "content_format": "text/md",
        "archived": True,
    }
    try:
        response = _request_with_retry(client, "PUT", f"{url}/{page_id}", headers=headers, json=body)
        response.raise_for_status()
    except httpx.HTTPError as error:
        _logger.warning(f"Could not archive orphaned ClickUp page for '{src_uri}' (page_id={page_id}): {error}")
    else:
        _logger.debug(f"Archived orphaned ClickUp page for '{src_uri}' (page_id={page_id})")


def _language_callback(tag: Tag) -> str:
    for css_class in chain(tag.get("class") or (), (tag.parent.get("class") or ()) if tag.parent else ()):
        if css_class.startswith("language-"):
            return css_class[9:]
    return ""


_converter = MarkdownConverter(
    bullets="-",
    code_language_callback=_language_callback,
    escape_underscores=False,
    heading_style=ATX,
)


def _generate_page_markdown(
    html: str,
    *,
    should_autoclean: bool,
    preprocess: str | None,
    path: str,
    files: Files,
) -> str:
    """Convert HTML to Markdown.

    Parameters:
        html: The HTML content.
        should_autoclean: Whether to autoclean the HTML.
        preprocess: An optional path of a Python module containing a `preprocess` function.
        path: The output path of the relevant Markdown file.
        files: The collection of all files in the site, used to resolve local image sources.

    Returns:
        The Markdown content.
    """
    html = _rasterize_content_svgs(html, page_dest_uri=path)
    soup = Soup(html, "html.parser")
    if should_autoclean:
        autoclean(soup)
    if preprocess:
        _preprocess(soup, preprocess, path)
    _render_mermaid_diagrams(soup)
    _resolve_images(soup, files=files, page_dest_uri=path)
    return mdformat.text(
        _converter.convert_soup(soup),
        options={"wrap": "no"},
        extensions=("tables",),
    )


_SVG_BLOCK_RE = re.compile(r"<svg\b[^>]*>.*?</svg\s*>", re.IGNORECASE | re.DOTALL)
_CLASS_ATTR_RE = re.compile(r'\bclass\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)


def _rasterize_content_svgs(html: str, *, page_dest_uri: str) -> str:
    """Rasterize inline content SVGs to `data:image/png` URIs, on the raw HTML string.

    This runs *before* HTML is parsed into a soup, so case-sensitive SVG attribute names
    (`viewBox`, `markerWidth`, `refX`, ...) survive intact. `BeautifulSoup`'s `html.parser`
    lowercases attribute names on parse (confirmed directly: `<svg viewBox="...">` round-trips
    as `<svg viewbox="...">`), which silently corrupts those attributes - live-verified against
    a real ClickUp workspace to break the diagram entirely. Rasterizing to PNG (via `resvg_py`)
    from the pristine, not-yet-parsed markup avoids that class of bug outright, and also sidesteps
    ClickUp failing to render a large, `<style>`-heavy SVG (also live-verified).

    Decorative Twemoji/icon SVGs (`class="twemoji"`) are left untouched here - `autoclean` removes
    them afterward via its own class-based check, which only inspects the `class` attribute and is
    unaffected by the attribute-name-casing issue above.

    Parameters:
        html: The raw HTML content, before any parsing.
        page_dest_uri: The current page's destination URI, used in the error message on failure.

    Returns:
        The HTML with non-decorative inline `<svg>` blocks replaced by `<img>` tags embedding the
        rasterized PNG as a `data:` URI.

    Raises:
        PluginError: When a content SVG's markup can't be rasterized.
    """

    def replace(match: re.Match[str]) -> str:
        svg_markup = match.group(0)
        opening_tag = svg_markup[: svg_markup.index(">") + 1]
        class_match = _CLASS_ATTR_RE.search(opening_tag)
        classes = class_match.group(2).split() if class_match else []
        if "twemoji" in classes:
            return svg_markup
        try:
            png_bytes = bytes(resvg_py.svg_to_bytes(svg_string=svg_markup))
        except Exception as error:
            raise PluginError(
                f"Could not rasterize an inline SVG on page '{page_dest_uri}': {error}",
            ) from error
        return f'<img src="{_data_uri(png_bytes, "image/png")}">'

    return _SVG_BLOCK_RE.sub(replace, html)


def _render_mermaid_diagrams(soup: Soup) -> None:
    """Render Mermaid code blocks to embedded diagram images, in place.

    A `<pre class="mermaid">` block - as produced by mkdocs-material's/`pymdownx.superfences`'
    Mermaid custom fence - is replaced with an `<img>` embedding the rendered diagram as a
    `data:image/png;base64,...` URI, using the optional `mermaidx` renderer (rendering happens
    locally; ClickUp does not render Mermaid source sent through its Page API, and - live-verified
    - fails to render Mermaid's own large, `<style>`-heavy SVG output too, hence PNG here as well).

    If `mermaidx` isn't installed, or a block's diagram source can't be rendered (invalid or
    unsupported Mermaid syntax), the block is left untouched: it still publishes as a plain
    fenced code block, just without becoming a diagram. This is a deliberate exception to this
    capability's usual "broken reference aborts the build" behavior for images - a renderer
    limitation is not treated as an authoring error.

    Parameters:
        soup: The soup to modify.
    """
    try:
        import mermaidx  # noqa: PLC0415 (optional dependency - imported lazily on purpose)
    except ImportError:
        return

    for pre in soup.find_all("pre", class_="mermaid"):
        code = pre.find("code")
        source = code.get_text() if code else pre.get_text()
        try:
            png_bytes = bytes(mermaidx.render(source).png())
        except Exception as error:  # noqa: BLE001 (any renderer failure falls back to the plain code block)
            _logger.debug(f"Could not render Mermaid diagram, publishing as plain code instead: {error}")
            continue
        replacement = soup.new_tag("img", src=_data_uri(png_bytes, "image/png"))
        pre.replace_with(replacement)


def _local_reference_path(src: str) -> str | None:
    """Return the unquoted local path portion of an `<img>`'s `src`, or `None` if it needs no local resolution.

    `None` means `src` is external (has a URL scheme, e.g. `http://`, `https://`, `data:`) or has no
    path component at all (e.g. an anchor-only reference) - either way, it should be left untouched.
    """
    parsed = urlsplit(src)
    if parsed.scheme or parsed.netloc:
        return None
    return unquote(parsed.path) or None


def _resolve_local_image_file(path: str, *, files: Files, page_dest_uri: str) -> File | None:
    """Resolve a local image path (relative to the current page, or site-root-relative) to its source `File`.

    Parameters:
        path: The unquoted local path portion of an `<img>`'s `src`, as rewritten by MkDocs' own
            relative-link resolution (relative to the current page's final URL, or site-root-relative
            if it starts with `/`).
        files: The collection of all files in the site.
        page_dest_uri: The current page's destination URI (`page.file.dest_uri`).

    Returns:
        The matching `File`, or `None` if no file in the site matches - the caller must treat this as
        a broken reference, not as "nothing to do" (that distinction is made by `_local_reference_path`).
    """
    if path.startswith("/"):
        target_dest_uri = posixpath.normpath(path.lstrip("/"))
    else:
        target_dest_uri = posixpath.normpath(posixpath.join(posixpath.dirname(page_dest_uri), path))
    return files.get_file_from_path(target_dest_uri)


def _data_uri(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _resolve_images(soup: Soup, *, files: Files, page_dest_uri: str) -> None:
    """Embed local images as inline `data:` URIs.

    An `<img>` whose `src` is already absolute/remote (or already a `data:` URI - including one
    produced by `_rasterize_content_svgs`/`_render_mermaid_diagrams` upstream) is left untouched.
    A local `<img>` has its source file read from disk and re-encoded as a `data:` URI.

    Parameters:
        soup: The soup to modify.
        files: The collection of all files in the site.
        page_dest_uri: The current page's destination URI (`page.file.dest_uri`).

    Raises:
        PluginError: When a local `<img>`'s source file cannot be resolved or read.
    """
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        src = str(src)
        local_path = _local_reference_path(src)
        if local_path is None:
            continue  # already absolute/remote/data URI - nothing to embed
        target_file = _resolve_local_image_file(local_path, files=files, page_dest_uri=page_dest_uri)
        if target_file is None or target_file.abs_src_path is None:
            raise PluginError(
                f"Could not embed image '{src}' referenced on page '{page_dest_uri}': "
                "no matching source file was found.",
            )
        try:
            content = target_file.content_bytes
        except OSError as error:
            raise PluginError(
                f"Could not read image '{src}' referenced on page '{page_dest_uri}': {error}",
            ) from error
        mime_type, _ = mimetypes.guess_type(target_file.src_uri)
        img["src"] = _data_uri(content, mime_type or "application/octet-stream")

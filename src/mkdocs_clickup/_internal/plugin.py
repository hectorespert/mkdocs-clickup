# MkDocs plugin that publishes documentation to ClickUp Pages.

from __future__ import annotations

import os
from itertools import chain
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import httpx
import mdformat
from bs4 import BeautifulSoup as Soup
from bs4 import Tag
from markdownify import ATX, MarkdownConverter
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.exceptions import PluginError
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from mkdocs_clickup._internal.config import _PluginConfig
from mkdocs_clickup._internal.logger import _get_logger
from mkdocs_clickup._internal.preprocess import _preprocess, autoclean

if TYPE_CHECKING:
    from typing import Any

    from mkdocs.config.defaults import MkDocsConfig
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

    _md_pages: dict[str, tuple[str, str, Section | None]]

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

    def on_page_content(self, html: str, *, page: Page, **kwargs: Any) -> str | None:  # noqa: ARG002
        """Convert page content into Markdown and store the result for later use.

        Hook for the [`on_page_content` event](https://www.mkdocs.org/user-guide/plugins/#on_page_content).

        Parameters:
            html: The rendered HTML.
            page: The page object.
        """
        page_md = _generate_page_markdown(
            html,
            should_autoclean=self.config.autoclean,
            preprocess=self.config.preprocess,
            path=page.file.dest_uri,
        )
        title = page.title if page.title is not None else page.file.src_uri
        self._md_pages[page.file.src_uri] = (str(title), page_md, page.parent)

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

        with httpx.Client() as client:
            existing_pages = _fetch_existing_pages(client, url, headers)
            page_by_sub_title = {page["sub_title"]: page for page in existing_pages if page.get("sub_title")}

            units = _build_publish_units(self._md_pages)
            _publish_units(client, url, headers, units, page_by_sub_title)

            current_identifiers = set(units)
            for page in existing_pages:
                sub_title = page.get("sub_title")
                if sub_title and sub_title not in current_identifiers:
                    _archive_orphaned_page(client, url, headers, page)


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
        response = client.get(url, headers=headers)
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


def _build_publish_units(
    md_pages: dict[str, tuple[str, str, Section | None]],
) -> dict[str, tuple[str, str, str | None]]:
    """Resolve every converted page and nav Section anchor into publish units.

    Each MkDocs `nav` Section resolves to an "anchor": a real `index.md`/
    `README.md` child page if one exists among the section's direct children,
    otherwise a synthetic placeholder page (empty content, matched across
    builds by a title-breadcrumb-derived `sub_title`). A page or placeholder's
    `parent_page_id` is the anchor of its own containing Section - except a
    page that *is* its Section's own anchor, which is parented to the
    Section's parent's anchor instead, to avoid a page being its own parent.

    Parameters:
        md_pages: Mapping of `src_uri` to `(title, markdown, section)`, where
            `section` is the page's nav parent (`None` for a top-level page).

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
        units[placeholder_key] = (section.title, "", parent_key)
        return placeholder_key

    for src_uri, (title, markdown, section) in md_pages.items():
        if section is None:
            parent_key = None
        elif anchor(section) == src_uri:
            parent_key = anchor(section.parent)
        else:
            parent_key = anchor(section)
        units[src_uri] = (title, markdown, parent_key)

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
                response = client.put(f"{url}/{matched['id']}", headers=headers, json=body)
            else:
                response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise PluginError(
                f"Failed to publish page '{key}' to ClickUp: {error.response.status_code} {error.response.text}",
            ) from error
        except httpx.HTTPError as error:
            raise PluginError(f"Failed to publish page '{key}' to ClickUp: {error}") from error
        _logger.debug(f"Published page '{key}' to ClickUp")
        page_id = matched["id"] if matched else response.json()["id"]
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
        response = client.put(f"{url}/{page_id}", headers=headers, json=body)
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
) -> str:
    """Convert HTML to Markdown.

    Parameters:
        html: The HTML content.
        should_autoclean: Whether to autoclean the HTML.
        preprocess: An optional path of a Python module containing a `preprocess` function.
        path: The output path of the relevant Markdown file.

    Returns:
        The Markdown content.
    """
    soup = Soup(html, "html.parser")
    if should_autoclean:
        autoclean(soup)
    if preprocess:
        _preprocess(soup, preprocess, path)
    return mdformat.text(
        _converter.convert_soup(soup),
        options={"wrap": "no"},
        extensions=("tables",),
    )

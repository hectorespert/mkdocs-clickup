# MkDocs plugin that publishes documentation to ClickUp Pages.

from __future__ import annotations

from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urljoin, urlparse

import mdformat
from bs4 import BeautifulSoup as Soup
from bs4 import Tag
from markdownify import ATX, MarkdownConverter
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from mkdocs_clickup._internal.config import _PluginConfig
from mkdocs_clickup._internal.logger import _get_logger
from mkdocs_clickup._internal.preprocess import _preprocess, autoclean

if TYPE_CHECKING:
    from typing import Any

    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.pages import Page


_logger = _get_logger(__name__)


class MkdocsClickUpPlugin(BasePlugin[_PluginConfig]):
    """The MkDocs plugin to publish documentation to ClickUp Pages.

    This is currently a bootstrap skeleton: it converts each page's rendered HTML
    into Markdown and stores it (`on_page_content`), but does not yet publish
    anything to ClickUp — that behavior will be added once the ClickUp Pages
    API integration is designed.

    Check the [Developing Plugins](https://www.mkdocs.org/user-guide/plugins/#developing-plugins) page of `mkdocs`
    for more information about its plugin system.
    """

    mkdocs_config: MkDocsConfig
    """The global MkDocs configuration."""

    _base_url: str
    _md_pages: dict[str, str]

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig | None:
        """Save the global MkDocs configuration.

        Hook for the [`on_config` event](https://www.mkdocs.org/user-guide/plugins/#on_config).
        In this hook, we save the global MkDocs configuration into an instance variable,
        to re-use it later.

        Arguments:
            config: The MkDocs config object.

        Returns:
            The same, untouched config.
        """
        if config.site_url is None:
            raise ValueError("'site_url' must be set in the MkDocs configuration to be used with the 'clickup' plugin")
        self.mkdocs_config = config
        self._md_pages = {}

        # Use `base_url` if it exists.
        if self.config.base_url is not None:
            self._base_url = cast("str", self.config.base_url)
        else:
            # Use `site_url`, which we assume to be always specified.
            self._base_url = cast("str", self.mkdocs_config.site_url)
        if not self._base_url.endswith("/"):
            self._base_url += "/"

        return config

    def on_page_content(self, html: str, *, page: Page, **kwargs: Any) -> str | None:  # noqa: ARG002
        """Convert page content into Markdown and store the result for later use.

        Hook for the [`on_page_content` event](https://www.mkdocs.org/user-guide/plugins/#on_page_content).

        Parameters:
            html: The rendered HTML.
            page: The page object.
        """
        # TODO(clickup-spike): replace unconditional conversion with real page-selection logic
        # once the ClickUp publishing config/behavior is designed.
        page_md = _generate_page_markdown(
            html,
            should_autoclean=self.config.autoclean,
            preprocess=self.config.preprocess,
            path=page.file.dest_uri,
            base_uri=self._base_url,
            page_uri=page.file.dest_uri,
        )
        self._md_pages[page.file.src_uri] = page_md

        return html


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
    base_uri: str,
    page_uri: str,
) -> str:
    """Convert HTML to Markdown.

    Parameters:
        html: The HTML content.
        should_autoclean: Whether to autoclean the HTML.
        preprocess: An optional path of a Python module containing a `preprocess` function.
        path: The output path of the relevant Markdown file.
        base_uri: The base URI of the site.
        page_uri: The destination URI of the page.

    Returns:
        The Markdown content.
    """
    soup = Soup(html, "html.parser")
    if should_autoclean:
        autoclean(soup)
    if preprocess:
        _preprocess(soup, preprocess, path)
    _convert_to_absolute_links(soup, base_uri, page_uri)
    return mdformat.text(
        _converter.convert_soup(soup),
        options={"wrap": "no"},
        extensions=("tables",),
    )


# NOTE: the link target format (URL vs. ClickUp internal page ID) will need
# revisiting once the ClickUp API spike clarifies ClickUp's addressing model
# (see README.md's "ClickUp API research" section). The resolution logic below —
# finding what a relative link points to within the doc tree — remains useful groundwork either way.
def _convert_to_absolute_links(soup: Soup, base_uri: str, page_uri: str) -> None:
    """Convert relative links to absolute ones in the HTML.

    Parameters:
        soup: The soup to modify.
        base_uri: The base URI of the site.
        page_uri: The destination URI of the page.
    """
    current_dir = Path(page_uri).parent.as_posix()

    # Find all anchor tags with `href` attributes.
    for link in soup.find_all("a", href=True):
        href = link.get("href")

        # Skip if `href` is not a string or is empty.
        if not isinstance(href, str) or not href:
            continue

        link["href"] = _convert_to_absolute_link(href, base_uri, current_dir)


def _convert_to_absolute_link(href: str, base_uri: str, current_dir: str) -> str:
    # Skip if it's an absolute path
    if href.startswith("/"):
        return href

    # Skip if it's an anchor link (starts with `#`).
    if href.startswith("#"):
        return href

    # Skip if it's an external link
    try:
        if urlparse(href).scheme:
            return href
    except ValueError:
        # Invalid URL, return as is
        return href

    # Relative path from current directory.
    relative_base = urljoin(base_uri, current_dir + "/") if current_dir else base_uri
    final_href = urljoin(relative_base, href)

    # Convert directory paths (ending with `/`) to point to `index.md` files.
    if final_href.endswith("/"):
        final_href = final_href + "index.md"

    return final_href

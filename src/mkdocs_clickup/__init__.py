"""mkdocs-clickup package.

MkDocs plugin to publish documentation to ClickUp Pages.
"""

from __future__ import annotations

from mkdocs_clickup._internal.plugin import MkdocsClickUpPlugin
from mkdocs_clickup._internal.preprocess import autoclean

__all__: list[str] = [
    "MkdocsClickUpPlugin",
    "autoclean",
]

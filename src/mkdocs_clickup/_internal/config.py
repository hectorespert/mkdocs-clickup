# Configuration options for the MkDocs ClickUp plugin.

from __future__ import annotations

from mkdocs.config import config_options as mkconf
from mkdocs.config.base import Config as BaseConfig


class _PluginConfig(BaseConfig):
    """Configuration options for the plugin."""

    autoclean = mkconf.Type(bool, default=True)
    preprocess = mkconf.Optional(mkconf.File(exists=True))
    workspace_id = mkconf.Optional(mkconf.Type(str))
    doc_id = mkconf.Optional(mkconf.Type(str))
    token = mkconf.Optional(mkconf.Type(str))
    publish = mkconf.Type(bool, default=False)
    default = mkconf.Choice(("all", "none"), default="all")
    include = mkconf.ListOfItems(mkconf.Type(str), default=[])
    exclude = mkconf.ListOfItems(mkconf.Type(str), default=[])

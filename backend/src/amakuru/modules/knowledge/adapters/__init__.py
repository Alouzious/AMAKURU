"""Knowledge ingestion adapters."""

from amakuru.modules.knowledge.adapters.base import KnowledgeAdapter, MappedRow
from amakuru.modules.knowledge.adapters.rest_json import RestJsonAdapter
from amakuru.modules.knowledge.adapters.spreadsheet import SpreadsheetAdapter
from amakuru.modules.knowledge.adapters.sql_db import SqlDbAdapter
from amakuru.modules.knowledge.adapters.website import WebsiteAdapter

__all__ = [
    "KnowledgeAdapter",
    "MappedRow",
    "RestJsonAdapter",
    "SpreadsheetAdapter",
    "SqlDbAdapter",
    "WebsiteAdapter",
]

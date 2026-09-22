"""Named SQL from ``db/queries`` (``QGATE_QUERIES_DIR`` in containers), loaded once per file."""

import os
from functools import cache
from pathlib import Path
from typing import Any

import aiosql


@cache
def queries(name: str) -> Any:
    """Return the aiosql ``Queries`` object for ``db/queries/<name>.sql``."""
    return aiosql.from_path(
        Path(os.environ.get("QGATE_QUERIES_DIR", "db/queries")) / f"{name}.sql", "psycopg"
    )

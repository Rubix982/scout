# src/db/init.py
"""DuckDB connection ownership and schema bootstrap.

One connection for the process, created on first use. Nothing here runs at
import time: importing this module must never touch the filesystem, so that
tests and tooling can import it without side effects (E-001).

Schema creation is delegated to `src.db.migrations` (E-009).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import duckdb

from src import config
from src.db.migrations import Migration, apply_pending, current_version

_con: Optional[duckdb.DuckDBPyConnection] = None


def db_path() -> Path:
    """Resolve the database path, creating its parent directory on demand.

    A function rather than a module constant so that nothing is created merely
    by importing this module. Honours ``SCOUT_DB_PATH`` via the config layer, so
    tests never touch the developer's real database.
    """
    return config.db_path()


def get_con() -> duckdb.DuckDBPyConnection:
    """Return the process-wide DuckDB connection, opening it on first call.

    Previously `src/db/init.py`, `src/db/insert.py`, and the enrichment client
    each opened their own connection at module scope against the same file.
    DuckDB's instance cache made that mostly survivable, which is precisely why
    it was worth removing: it was coincidence, not design, and it meant three
    modules each owned a fraction of the storage layer.
    """
    global _con
    if _con is None:
        _con = duckdb.connect(str(db_path()))
    return _con


def close_con() -> None:
    """Close and drop the cached connection. Used by tests between cases."""
    global _con
    if _con is not None:
        _con.close()
        _con = None


def init_tables() -> List[Migration]:
    """Bring the database up to the latest schema version. Idempotent."""
    return apply_pending(get_con())


def schema_version() -> int:
    return current_version(get_con())


if __name__ == "__main__":
    applied = init_tables()
    print(
        f"Schema at version {schema_version()} in {db_path()} "
        f"({len(applied)} migration(s) applied)"
    )

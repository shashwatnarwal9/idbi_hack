"""Shared DuckDB helpers used by every pipeline layer."""

from __future__ import annotations

from pathlib import Path
from string import Template

import duckdb

from aayai.paths import SQL_DIR


def hive_read(directory: Path) -> str:
    """Return a read_parquet() expression for a year=/month= hive layout.

    hive_types_autocast=0 pins both partition keys to VARCHAR ('2025', '01')
    instead of letting DuckDB guess BIGINT for year, so every reader sees the
    same schema.

    Args:
        directory: root of the partitioned table (contains year=*/month=*).

    Returns:
        A SQL expression usable in a FROM clause.
    """
    glob = directory.as_posix() + "/*/*/*.parquet"
    return f"read_parquet('{glob}', hive_partitioning=1, hive_types_autocast=0)"


def run_sql_file(con: duckdb.DuckDBPyConnection, sql_file: str, **params: str) -> None:
    """Execute a templated SQL file from sql/.

    Placeholders use string.Template ($name) with safe_substitute, so regex
    '$' anchors inside the SQL are not mistaken for placeholders.

    Args:
        con: open DuckDB connection.
        sql_file: file name under sql/.
        **params: placeholder values substituted into the template.
    """
    sql = Template((SQL_DIR / sql_file).read_text(encoding="utf-8"))
    con.execute(sql.safe_substitute(params))

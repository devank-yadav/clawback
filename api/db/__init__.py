"""Postgres on Tiger Data (TimescaleDB): the schema in migrations/ and the seed (python -m api.db.seed).

The pipeline still reads data/ through api/rows.py and api/documents.py; the seed copies the same rows in.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
# Everything after this line in a migration needs the timescaledb extension; the seed skips it on plain Postgres.
TIMESCALE_MARKER = "-- @timescaledb"


def migration(name: str = "001_init.sql") -> tuple[str, str]:
    """(plain Postgres part, TimescaleDB part) of one migration file."""
    text = (MIGRATIONS / name).read_text()
    plain, _, timescale = text.partition(TIMESCALE_MARKER)
    return plain, timescale

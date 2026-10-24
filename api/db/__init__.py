"""Postgres on Tiger Data (TimescaleDB): the schema in migrations/, the seed (python -m api.db.seed), and what the
running app reads and writes there: the seeded rows (reads.py, through api/rows.py), every run's events
(events.py) and the cap query (GET /db/cap). conn.py decides whether the database is on and connects.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
# Everything after this line in a migration needs the timescaledb extension; the seed skips it on plain Postgres.
TIMESCALE_MARKER = "-- @timescaledb"


def migrations() -> list[str]:
    """Every migration file, in the order they run."""
    return sorted(p.name for p in MIGRATIONS.glob("*.sql"))


def migration(name: str = "001_init.sql") -> tuple[str, str]:
    """(plain Postgres part, TimescaleDB part) of one migration file."""
    text = (MIGRATIONS / name).read_text()
    plain, _, timescale = text.partition(TIMESCALE_MARKER)
    return plain, timescale

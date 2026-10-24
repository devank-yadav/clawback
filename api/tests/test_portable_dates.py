"""Dates in evidence and logs must format the same on every OS: strftime's %-d raises on Windows."""

import pathlib
from datetime import date, datetime

from api.evidence import day

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_day_matches_the_old_format():
    assert day(date(2026, 3, 7)) == "Mar 7"
    assert day(date(2026, 3, 14)) == "Mar 14"
    assert day(datetime(2026, 3, 11, 9, 30), year=True) == "Mar 11, 2026"


def test_no_platform_specific_strftime_flags():
    offenders = [str(p.relative_to(ROOT)) for d in ("api", "eval", "scripts") for p in (ROOT / d).rglob("*.py")
                 if p.name != "test_portable_dates.py" and "%-" in p.read_text(encoding="utf-8")]
    assert offenders == []

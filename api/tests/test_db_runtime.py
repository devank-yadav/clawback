"""The app on Postgres: rows read back from the database, every event saved off the run's thread, a run replayed
after a restart, and GET /db/cap.

The pure tests need no database: the files when it's off, unreachable or failing, the URL never printed, and an event
queue that never makes a run wait. The rest run only when TEST_DATABASE_URL points at a throwaway Postgres (ideally
TimescaleDB); each seeds its own schema and drops it after. .env isn't read in tests, so set it in the shell:
    TEST_DATABASE_URL=postgresql://postgres:pw@localhost:5432/clawback_test python -m pytest -q api/tests/test_db_runtime.py
"""

import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import accounts, pipeline, rows
from api.contracts import EventAdapter
from api.db import conn, events, reads, seed
from api.integrations import replay
from api.main import app
from api.tests.test_pipeline import ScenarioClaude

client = TestClient(app)
D = Decimal
UNREACHABLE = "postgresql://clawback:hunter2-not-a-key@127.0.0.1:9/clawback"  # nothing listens on port 9
RUNNING = [1200, 2180, 5000, 6540]  # weeks 1 to 4 of March, Original + Chocolate (data/CLAUDE.md)
FROM_FILES = ("charges_from_files", "sales_from_files", "prior_payments_from_files", "promo_plan_from_files")


def _loaded():
    """What the pipeline's loaders return, as repr: Decimal('1.50') and Decimal('1.5000') differ there."""
    return repr([rows.charges("march"), rows.charges("april"), rows.sales(), rows.prior_payments(), rows.promo_plan()])


def _files():
    return repr([rows.charges_from_files("march"), rows.charges_from_files("april"), rows.sales_from_files(),
                 rows.prior_payments_from_files(), rows.promo_plan_from_files()])


def _event(n=1, run_id="run-march-test"):
    return EventAdapter.validate_python({"id": n, "run_id": run_id, "at": datetime.now().astimezone(), "type": "log",
                                         "data": {"text": f"line {n}"}})


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "clawback.db" and r.levelno == logging.WARNING]


def _sse(text):
    lines = text.splitlines()
    return [int(x[len("id: "):]) for x in lines if x.startswith("id: ")], [x[len("data: "):] for x in lines if x.startswith("data: ")]


def _totals(run):
    t = [e.data for e in run.events if e.type == "totals"][-1]
    return t.disputed, t.accepted, t.questions


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    """No runs, a new event writer, no shared connection or remembered outage, nothing recorded to data/fixtures."""
    pipeline.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setattr(conn, "RETRY_AFTER", 0)
    monkeypatch.setattr(events, "_writer", events.Writer())
    monkeypatch.setattr(events, "_seen", set())
    monkeypatch.setattr(events, "_forgotten", set())
    monkeypatch.setattr(events, "_reset_at", None)
    conn.reset()
    yield
    events._writer.stop()
    conn.reset()
    pipeline.reset()


# --- No database -------------------------------------------------------------------------------------------

def test_without_a_database_the_rows_are_the_files_and_nothing_connects(monkeypatch):
    def connect(*_a, **_k):
        raise AssertionError("connected to a database")

    monkeypatch.setattr(conn.psycopg, "connect", connect)
    files = _files()
    assert _loaded() == files  # DATABASE_URL unset
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setenv("DEMO_MODE", "true")  # the demo never depends on the network
    assert _loaded() == files
    events.record(_event())
    assert events._writer.thread is None
    assert client.get("/db/cap").status_code == 503


def test_an_unreachable_database_means_the_files_logged_once_without_the_url(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    attempts, real = [], conn.psycopg.connect
    monkeypatch.setattr(conn.psycopg, "connect", lambda *a, **k: attempts.append(1) or real(*a, **k))
    files = _files()
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        assert _loaded() == files
        assert _loaded() == files
        cap = client.get("/db/cap")
    assert len(attempts) == 2  # one retry; then it counts as down and the other loaders don't wait on it
    (warning,) = _warnings(caplog)
    assert "can't connect" in warning and "rows come from data/" in warning
    assert cap.status_code == 503
    for text in (caplog.text, cap.text):
        assert "hunter2-not-a-key" not in text and UNREACHABLE not in text


def test_scrub_takes_out_the_url_and_its_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    said = conn.scrub(RuntimeError(f"bad {UNREACHABLE}, and the password hunter2-not-a-key\nsecond line"))
    assert said == "RuntimeError: bad DATABASE_URL, and the password ***"


@pytest.mark.parametrize("answer", [RuntimeError('column "source_file" does not exist'), []])
def test_a_failing_or_empty_table_means_the_files_logged_once(monkeypatch, caplog, answer):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)

    def run(_fn):
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(conn.shared, "run", run)
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        for _ in range(3):
            assert repr(rows.charges("march")) == repr(rows.charges_from_files("march"))
    (warning,) = _warnings(caplog)
    assert warning.startswith("Postgres charges: ") and "reading data/ instead" in warning


def test_a_data_directory_of_its_own_always_reads_its_files(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setattr(reads, "load", lambda *_: pytest.fail("asked the database for a test's own data"))
    data = tmp_path / "peak-bar"
    shutil.copytree(accounts.get("peak-bar").dir, data)
    assert [c.id for c in rows.charges("march", data)] == ["C1", "C2", "C3", "C4", "C5", "C6"]


def test_recording_events_never_waits_on_the_database(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    hung = threading.Event()

    def connect():
        hung.wait(10)  # a database that doesn't answer
        raise conn.Unavailable("no answer")

    monkeypatch.setattr(conn, "connect", connect)
    monkeypatch.setattr(events, "_writer", events.Writer(max_queued=100))
    try:
        with caplog.at_level(logging.WARNING, logger="clawback.db"):
            started = time.monotonic()
            for n in range(1, 5001):
                events.record(_event(n))
            took = time.monotonic() - started
        assert took < 1.0, f"5,000 events took {took:.2f} s to queue"
        assert _warnings(caplog) == ["events: 100 events already wait for the database; newer ones aren't saved"]
        assert not events.flush(timeout=0.1)  # still waiting on the database, and the caller went on
    finally:
        hung.set()


def test_a_failed_write_is_logged_once_kept_and_written_later(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setattr(events, "PAUSE", 0.01)

    class Db:
        closed = False

        def close(self):
            self.closed = True

    written, failures = [], [3]

    def write(_db, batch):
        if failures[0]:
            failures[0] -= 1
            raise RuntimeError('relation "events" does not exist')
        written.extend(batch)

    monkeypatch.setattr(conn, "connect", Db)
    monkeypatch.setattr(events, "_write", write)
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        for n in range(1, 11):
            events.record(_event(n))
        assert events.flush(timeout=5)
    assert [e.id for e in written] == list(range(1, 11))
    assert _warnings(caplog) == [
        'events: saving to Postgres: RuntimeError: relation "events" does not exist; trying again every 0.01 s',
        "events: saving to Postgres: working again",
    ]


def test_a_connection_that_broke_is_reopened_without_a_warning(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setattr(events, "PAUSE", 0.01)
    opened, written = [], []

    class Db:
        closed = broken = False

        def close(self):
            self.closed = True

    def connect():
        opened.append(Db())
        return opened[-1]

    def write(db, batch):
        if len(opened) == 1:
            db.broken = True  # the server restarted under this connection
            raise conn.psycopg.OperationalError("terminating connection due to administrator command")
        written.extend(batch)

    monkeypatch.setattr(conn, "connect", connect)
    monkeypatch.setattr(events, "_write", write)
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        events.record(_event())
        assert events.flush(timeout=5)
    assert len(opened) == 2 and [e.id for e in written] == [1] and _warnings(caplog) == []


def test_a_run_with_an_unreachable_database_still_gets_the_demo_numbers(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        run = pipeline.start("march", ScenarioClaude(), background=False)
    assert _totals(run) == (D(4120), D(1530), 1)  # C6 waits on the owner's answer
    assert len(_warnings(caplog)) == 1  # the outage, once, for the rows and the events together


def test_no_saved_runs_without_a_database():
    assert client.get("/runs/latest").status_code == 404
    assert client.get("/runs/run-march-gone/events", params={"keepalive": False}).status_code == 404


# --- A real database (TEST_DATABASE_URL) -------------------------------------------------------------------

@pytest.fixture
def database(monkeypatch):
    """A seeded schema of its own, with the app's connections pointed at it."""
    psycopg = pytest.importorskip("psycopg")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to a throwaway Postgres to run the database tests")
    name = f"runtime_test_{uuid.uuid4().hex[:8]}"
    options = f"-c search_path={name},public"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {name}")
        try:
            with psycopg.connect(url, autocommit=True, options=options) as db:
                seeded = seed.seed(db)
                monkeypatch.setenv("DATABASE_URL", url)
                monkeypatch.setenv("PGOPTIONS", options)  # libpq reads it, so the app's connections land here
                conn.reset()
                yield db, seeded
        finally:
            events._writer.stop()
            conn.reset()
            admin.execute(f"DROP SCHEMA {name} CASCADE")


def test_rows_from_the_database_are_the_files_exactly(database, monkeypatch):
    files = _files()
    for table, args, expected in [
        ("charges", (rows.charge_file("march"),), rows.charges_from_files("march")),
        ("charges", (rows.charge_file("april"),), rows.charges_from_files("april")),
        ("store_sales", (), rows.sales_from_files()),
        ("prior_payments", (), rows.prior_payments_from_files()),
        ("promo_plan", (), rows.promo_plan_from_files()),
    ]:
        assert repr(reads.load(table, "peak-bar", *args)) == repr(expected), table
        assert reads.load(table, "another-account", *args) is None, table  # no rows of its own: its files
    for name in FROM_FILES:  # the pipeline's loaders now read the database alone
        monkeypatch.setattr(rows, name, lambda *_: pytest.fail("read the files with the database on"))
    assert _loaded() == files
    db, _ = database
    db.execute("UPDATE charges SET description = 'Read from Postgres' WHERE id = 'C1'")
    assert rows.charges("march")[0].description == "Read from Postgres"


def test_a_run_on_the_database_sends_the_agents_what_a_run_on_the_files_does(database, monkeypatch):
    class Recording(ScenarioClaude):
        def __init__(self):
            super().__init__()
            self.requests = []

        def _parse(self, output_format, messages, **kw):
            self.requests.append((output_format.__name__, messages[0]["content"]))
            return super()._parse(output_format, messages, **kw)

    def march():
        fake = Recording()
        run = pipeline.start("march", fake, background=False)
        pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days", client=fake)
        return run, fake.requests

    with pytest.MonkeyPatch.context() as mp:
        for name in FROM_FILES:
            mp.setattr(rows, name, lambda *_: pytest.fail("read the files with the database on"))
        on_db, db_requests = march()
    monkeypatch.delenv("DATABASE_URL")  # the files again
    pipeline.reset()
    on_files, file_requests = march()
    assert db_requests == file_requests  # so DEMO_MODE fixture keys recorded on either replay on both
    assert _totals(on_db) == _totals(on_files) == (D(4120), D(2730), 1)
    assert {c: (d.decision, d.disputed, d.accepted) for c, d in on_db.shown.items()} == \
           {c: (d.decision, d.disputed, d.accepted) for c, d in on_files.shown.items()}


def test_events_are_saved_and_a_run_replays_after_a_restart(database):
    db, _ = database
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days", client=fake)
    assert events.flush(timeout=10)
    n = len(run.events)
    assert db.execute("SELECT count(*), min(id), max(id) FROM events WHERE run_id = %s", (run.id,)).fetchone() == (n, 1, n)
    original = [e.model_dump_json() for e in run.events]

    pipeline.RUNS.clear()  # the API restarted: nothing in memory
    assert client.get("/runs/latest").json() == {"run_id": run.id, "events_url": f"/runs/{run.id}/events"}
    ids, data = _sse(client.get(f"/runs/{run.id}/events", params={"keepalive": False}).text)
    assert ids == list(range(1, n + 1)) and data == original  # the same SSE lines the live run sent
    assert _sse(client.get(f"/runs/{run.id}/events", params={"keepalive": False, "after": 5}).text)[0][0] == 6
    resumed = client.get(f"/runs/{run.id}/events", params={"keepalive": False}, headers={"Last-Event-ID": str(n - 1)})
    assert _sse(resumed.text) == ([n], original[-1:])
    assert client.get("/runs/latest", params={"kind": "april"}).status_code == 404


def test_a_demo_reset_forgets_the_saved_runs(database):
    db, _ = database
    old = pipeline.start("march", ScenarioClaude(), background=False)
    assert events.flush(timeout=10)
    assert client.post("/demo/reset").status_code == 200
    assert client.get("/runs/latest").status_code == 404  # not the run from before the reset
    assert client.get(f"/runs/{old.id}/events", params={"keepalive": False}).status_code == 404
    old.log("a late line from the old run's thread")
    assert events.flush(timeout=10)
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0  # deleted, and nothing late saved
    new = pipeline.start("march", ScenarioClaude(), background=False)
    assert events.flush(timeout=10)
    pipeline.RUNS.clear()
    assert client.get("/runs/latest").json()["run_id"] == new.id


def test_db_cap_answers_from_the_database(database):
    _, seeded = database
    body = client.get("/db/cap").json()
    assert (body["promo_id"], body["cap"], body["source"]) == ("SPRING-26", 5000, seeded.weekly)
    assert [w["promo_units"] for w in body["weeks"]] == [1200, 980, 2820, 1540]
    assert [w["running_units"] for w in body["weeks"]] == RUNNING
    assert (body["weeks"][-1]["week_start"], body["weeks"][-1]["week_end"]) == ("2026-03-22", "2026-03-31")
    assert client.get("/db/cap", params={"promo_id": "SUMMER-26"}).status_code == 404


def test_a_database_seeded_before_002_reads_the_files_until_make_seed(database, caplog):
    db, _ = database
    for table in seed.KEYS.keys() - {"documents", "remittances"}:  # as 001_init.sql alone left them
        db.execute(f"ALTER TABLE {table} DROP COLUMN source_file, DROP COLUMN source_row")
    with caplog.at_level(logging.WARNING, logger="clawback.db"):
        assert _loaded() == _files()
    assert any('column "source_file" does not exist' in w for w in _warnings(caplog))
    again = seed.seed(db)  # make seed adds the columns and fills them in
    assert {t: again.updated[t] for t in ("charges", "prior_payments", "store_sales", "promo_plan")} == \
           {"charges": 8, "prior_payments": 2, "store_sales": 14, "promo_plan": 1}
    assert sum(again.inserted.values()) == 0 and set(seed.seed(db).updated.values()) == {0}
    assert repr(reads.load("store_sales", "peak-bar")) == repr(rows.sales_from_files())


def test_each_account_finds_its_own_runs_after_a_restart(two_accounts, database):
    from api.tests.test_accounts import OatClaude

    db, _ = database
    oat = pipeline.start(None, OatClaude(), background=False, account="test-oat")
    assert events.flush(timeout=10)
    saved = db.execute("SELECT DISTINCT account_id FROM events WHERE run_id = %s", (oat.id,)).fetchall()
    assert saved == [("test-oat",)]
    pipeline.RUNS.clear()  # the API restarted
    assert client.get("/runs/latest", params={"account": "test-oat"}).json()["run_id"] == oat.id
    assert client.get("/runs/latest").status_code == 404  # Peak Bar has no run of its own
    assert repr(rows.charges("june", account="test-oat")) == \
        repr(rows.charges_from_files("june", account="test-oat"))

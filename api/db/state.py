"""Saved rules, the admin's auto-post limits and the audit chain, kept in Postgres so a restart forgets none of them
(the rules, auto_post_limits and audit_log tables).

- Every rule saved or undone (api/pipeline.answer) is upserted into `rules` with its account. At startup restore()
  brings them all back, undone ones too, so a new rule keeps the next number and only active ones ever match.
- Every auto-post limit the admin sets (api/pipeline.decide_approval with auto_post) is upserted into
  `auto_post_limits`, one per account; restore() brings them back.
- Every audit entry (api/audit.py) is inserted into `audit_log`, and the head hash into `audit_head` by the same
  statement, so the two can't disagree. restore() rebuilds the chain and its head: /audit/verify still passes, and a
  row edited or cut off while the API was down still breaks it.
- Writes are queued on the events writer (api/db/events.write_later): in order, and never making a run wait.
- Only a process that read the saved state at startup writes to it; one that couldn't (the database was away) keeps
  everything in memory, so a new chain never lands on top of the old one. No database (tests, laptops): in memory,
  as before. A demo reset deletes both (reset()).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from api.contracts import AutoPost, Rule
from api.db import conn, events
from api.engine.audit_chain import GENESIS, AuditEntry

try:
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # conn.enabled() is False without psycopg, so nothing here runs
    dict_row = Jsonb = None

log = logging.getLogger("clawback.db")

RULE_COLUMNS = ("id", "label", "pattern_text", "term_type", "counterparty", "condition", "decision", "else_decision",
                "summary", "approver", "approver_role", "learned_at", "source_question_id", "status")
UPSERT_RULE = (f"INSERT INTO rules ({', '.join(RULE_COLUMNS)}, account_id) "
               f"VALUES ({', '.join(['%s'] * (len(RULE_COLUMNS) + 1))}) ON CONFLICT (id) DO UPDATE SET "
               + ", ".join(f"{c} = EXCLUDED.{c}" for c in (*RULE_COLUMNS[1:], "account_id")))
AUTO_POST_COLUMNS = ("limit_usd", "set_by", "approval_id", "set_at")
UPSERT_AUTO_POST = (f"INSERT INTO auto_post_limits (account_id, {', '.join(AUTO_POST_COLUMNS)}) "
                    f"VALUES ({', '.join(['%s'] * (len(AUTO_POST_COLUMNS) + 1))}) ON CONFLICT (account_id) DO UPDATE SET "
                    + ", ".join(f"{c} = EXCLUDED.{c}" for c in AUTO_POST_COLUMNS))
AUDIT_COLUMNS = ("id", "at", "actor", "action", "object_ref", "evidence", "prev_hash", "hash")
SAVE_AUDIT_ROW = (f"WITH saved AS (INSERT INTO audit_log ({', '.join(AUDIT_COLUMNS)}) "
                  f"VALUES ({', '.join(['%s'] * len(AUDIT_COLUMNS))}) RETURNING hash) "
                  "INSERT INTO audit_head (id, hash) SELECT 1, hash FROM saved "
                  "ON CONFLICT (id) DO UPDATE SET hash = EXCLUDED.hash")

_reading = conn.LogOnce("saved rules, auto-post limits and audit chain: reading from Postgres")
_on = False  # this process read the saved state at startup, so it may write to it


@dataclass
class Saved:
    rules: list[tuple[Rule, str]] = field(default_factory=list)  # (rule, account id), oldest first
    auto_post: dict[str, AutoPost] = field(default_factory=dict)  # account id -> the admin's auto-post limit
    entries: list[AuditEntry] = field(default_factory=list)  # the chain, in id order
    head: str = GENESIS


def enabled() -> bool:
    return _on and conn.enabled()


def _read(db) -> Saved:
    with db.cursor(row_factory=dict_row) as cur:
        rules = cur.execute(f"SELECT {', '.join(RULE_COLUMNS)}, account_id FROM rules ORDER BY learned_at, id").fetchall()
        limits = cur.execute(f"SELECT account_id, {', '.join(AUTO_POST_COLUMNS)} FROM auto_post_limits").fetchall()
        rows = cur.execute(f"SELECT {', '.join(AUDIT_COLUMNS)} FROM audit_log ORDER BY id").fetchall()
        head = cur.execute("SELECT hash FROM audit_head WHERE id = 1").fetchone()
    saved = [(Rule.model_validate({k: v for k, v in r.items() if k != "account_id"}), r["account_id"]) for r in rules]
    auto_post = {r["account_id"]: AutoPost(limit=r["limit_usd"], set_by=r["set_by"], approval_id=r["approval_id"],
                                           set_at=r["set_at"]) for r in limits}
    entries = [AuditEntry(**r) for r in rows]
    return Saved(saved, auto_post, entries, head["hash"] if head else (entries[-1].hash if entries else GENESIS))


def load() -> Saved | None:
    """The saved rules and chain, read once at startup. None: no database, or it couldn't be read (logged once);
    then this process saves nothing either."""
    global _on
    _on = False
    if not conn.enabled():
        return None
    try:
        saved = conn.shared.run(_read)
    except conn.Unavailable:
        return None
    except Exception as e:  # noqa: BLE001 - not migrated yet (make seed), or a bad row: keep it all in memory
        _reading.failed(f"{conn.scrub(e)}; rules and the audit chain stay in memory this run (make seed migrates)")
        return None
    _reading.ok()
    _on = True
    return saved


def restore() -> Saved | None:
    """At startup: put the saved rules back in the pipeline and the chain back in the audit log."""
    from api import audit, pipeline

    saved = load()
    if saved is not None:
        pipeline.restore_rules(saved.rules)
        pipeline.restore_auto_post(saved.auto_post)
        audit.restore(saved.entries, saved.head)
        if saved.rules or saved.entries:
            log.info("restored %d saved rules and %d audit rows from Postgres", len(saved.rules), len(saved.entries))
    return saved


def save_rule(rule: Rule, account_id: str) -> None:
    if enabled():
        events.write_later(UPSERT_RULE, (*(getattr(rule, c) for c in RULE_COLUMNS), account_id))


def save_auto_post(auto_post: AutoPost, account_id: str) -> None:
    if enabled():
        events.write_later(UPSERT_AUTO_POST, (account_id, auto_post.limit, auto_post.set_by, auto_post.approval_id,
                                              auto_post.set_at))


def save_audit(entry: AuditEntry) -> None:
    if enabled():
        events.write_later(SAVE_AUDIT_ROW, tuple(Jsonb(entry.evidence) if c == "evidence" else getattr(entry, c)
                                                 for c in AUDIT_COLUMNS))


def reset() -> None:
    """A demo reset: no saved rules or auto-post limits, and a new chain."""
    if enabled():
        for table in ("rules", "auto_post_limits", "audit_log", "audit_head"):
            events.write_later(f"DELETE FROM {table}")

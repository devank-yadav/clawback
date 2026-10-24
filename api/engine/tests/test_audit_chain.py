import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal

from api.engine.audit_chain import GENESIS, AuditChain, compute_hash, verify

T0 = datetime(2026, 10, 24, 17, 0, tzinfo=timezone.utc)


def demo_chain() -> AuditChain:
    chain = AuditChain()
    chain.append("gate", "decision", "charge:C1", {"decision": "split", "disputed": Decimal("600.00"),
                                                   "accepted": Decimal("1200.00"), "gate_row": 7}, at=T0)
    chain.append("gate", "decision", "charge:C6", {"decision": "ask", "gate_row": 4}, at=T0)
    chain.append("owner:Dana", "rule_saved", "rule:1", {"condition": "notice_days >= 14"}, at=T0)
    chain.append("negotiator", "dispute_filed", "dispute:D-0417", {"disputed": "4120.00"}, at=T0)
    chain.append("controller:Sam", "credit_memo_approved", "approval:1", {"amount": "2730.00"}, at=T0)
    return chain


def test_untouched_chain_verifies():
    chain = demo_chain()
    result = verify(chain.entries, expected_head=chain.head)
    assert result.ok and result.checked == 5


def test_rows_link_to_the_previous_hash():
    e = demo_chain().entries
    assert e[0].prev_hash == GENESIS
    assert all(e[i].prev_hash == e[i - 1].hash for i in range(1, len(e)))
    assert [x.id for x in e] == [1, 2, 3, 4, 5]
    assert len({x.hash for x in e}) == 5


def test_hash_is_deterministic():
    a, b = demo_chain(), demo_chain()
    assert a.head == b.head


def test_editing_a_past_row_breaks_the_chain():
    rows = [x.as_row() for x in demo_chain().entries]
    rows[1]["evidence"]["decision"] = "accept"  # someone flips C6 from ask to accept
    result = verify(rows)
    assert not result.ok
    assert result.broken_at == 2
    assert "edited" in result.reason


def test_editing_a_row_and_rehashing_it_still_breaks_the_next_link():
    rows = [x.as_row() for x in demo_chain().entries]
    rows[0]["evidence"]["disputed"] = "1800.00"
    rows[0]["hash"] = compute_hash(rows[0])  # forger fixes up the edited row's own hash
    result = verify(rows)
    assert not result.ok and result.broken_at == 2
    assert "prev_hash" in result.reason


def test_editing_actor_or_time_breaks_the_chain():
    entries = demo_chain().entries
    forged = list(entries)
    forged[4] = dataclasses.replace(entries[4], actor="negotiator")  # an agent can't approve a credit memo
    assert verify(forged).broken_at == 5
    forged = list(entries)
    forged[2] = dataclasses.replace(entries[2], at="2026-10-23T09:00:00+00:00")
    assert verify(forged).broken_at == 3


def test_deleting_or_reordering_rows_is_detected():
    entries = list(demo_chain().entries)
    assert verify(entries[:2] + entries[3:]).broken_at == 3
    assert verify([entries[1], entries[0], *entries[2:]]).broken_at == 1


def test_truncation_is_caught_only_with_the_saved_head():
    chain = demo_chain()
    short = chain.entries[:3]
    assert verify(short).ok
    result = verify(short, expected_head=chain.head)
    assert not result.ok and "head" in result.reason


def test_rows_survive_a_json_round_trip():
    # Rows as they come back from Postgres JSON columns.
    rows = json.loads(json.dumps([x.as_row() for x in demo_chain().entries]))
    assert verify(rows).ok


def test_append_copies_evidence_so_caller_edits_do_not_leak_in():
    chain = AuditChain()
    ev = {"lines": ["C2"]}
    chain.append("negotiator", "dispute_filed", "dispute:D-0417", ev, at=T0)
    ev["lines"].append("C4")
    assert chain.entries[0].evidence == {"lines": ["C2"]}
    assert verify(chain.entries).ok


def test_empty_chain_verifies_and_default_timestamp_is_utc_iso():
    assert verify([]).ok
    chain = AuditChain()
    e = chain.append("system", "run_started", "run:1")
    assert datetime.fromisoformat(e.at).tzinfo is not None
    assert verify(chain.entries).ok

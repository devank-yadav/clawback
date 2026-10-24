"""Rule memory on Moss (F16): each saved owner rule is indexed by its clause's wording, and a new discretion clause is
searched against them, so a differently worded clause still finds Rule #1 (docs/design.md, "Rules and matching").

SDK: Moss's official Python package, `pip install moss` (pinned in api/requirements.txt), per its PyPI page
https://pypi.org/project/moss/ and repo https://github.com/usemoss/moss (docs: https://docs.moss.dev). The calls, as
the package's README and docstrings (moss 1.21.0) give them:
    client = MossClient(project_id, project_key)
    await client.list_indexes()                                    # [IndexInfo] with .name
    await client.create_index(name, [DocumentInfo(id=, text=, metadata={str: str})])  # waits for the build
    await client.add_docs(name, docs, MutationOptions(upsert=True))  # returns a MutationResult with .job_id
    await client.delete_docs(name, [doc_id])
    await client.load_index(name)       # queries run on a local copy; loading again picks up a newer version
    result = await client.query(name, text, QueryOptions(top_k=5, alpha=1.0))  # alpha 1.0: by meaning only
    result.docs[i].id, result.docs[i].score                        # score 0 to 1, from vector similarity

Configured by MOSS_PROJECT_ID and MOSS_API_KEY (the project key from the Moss portal). Every call goes through
replay.call_outside: a timeout, one retry, recorded with RECORD_FIXTURES=1 and replayed in DEMO_MODE. No keys, or a
failed call, means no matches, and the gate uses the exact match on term type + counterparty instead
(api/engine/rules.find_rule). Moss only names candidate rules: the gate checks the similarity, the term type and
the counterparty itself, and only active rules can match.

`python -m api.integrations.moss` indexes Rule #1's clause and prints how similar other wordings are to it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol

from api.engine.types import RuleMatch
from api.integrations import replay

log = logging.getLogger("clawback.moss")

SERVICE = "moss"  # fixtures in data/fixtures/moss/
INDEX = "clawback-rules"
TOP_K = 5
TIMEOUT_S = 15.0  # queries run locally; only loading and writes reach Moss
JOB_WAIT_S = 10.0


class Backend(Protocol):
    """What Clawback needs from Moss. SdkBackend is the real one; tests pass a fake."""

    def upsert(self, doc_id: str, text: str, metadata: dict[str, str]) -> None: ...

    def delete(self, doc_ids: list[str]) -> None: ...

    def query(self, text: str, top_k: int) -> list[dict[str, Any]]: ...  # [{"id": ..., "score": ...}]


class SdkBackend:
    """The Moss SDK. Its methods are async; each call runs to completion in the calling thread."""

    def __init__(self, project_id: str, project_key: str, index: str = INDEX, sdk: Any = None):
        if sdk is None:
            import moss as sdk
        self.sdk, self.index = sdk, index
        self.client = sdk.MossClient(project_id, project_key)
        self._lock = threading.Lock()  # one call at a time on the shared client

    def _run(self, coro):
        with self._lock:
            return asyncio.run(coro)

    def upsert(self, doc_id: str, text: str, metadata: dict[str, str]) -> None:
        self._run(self._upsert(doc_id, text, metadata))

    def delete(self, doc_ids: list[str]) -> None:
        self._run(self.client.delete_docs(self.index, doc_ids))

    def query(self, text: str, top_k: int) -> list[dict[str, Any]]:
        return self._run(self._query(text, top_k))

    async def _upsert(self, doc_id: str, text: str, metadata: dict[str, str]) -> None:
        doc = self.sdk.DocumentInfo(id=doc_id, text=text, metadata=metadata)
        if self.index in {i.name for i in await self.client.list_indexes()}:
            result = await self.client.add_docs(self.index, [doc], self.sdk.MutationOptions(upsert=True))
            await self._settle(getattr(result, "job_id", ""))
        else:
            await self.client.create_index(self.index, [doc])
        await self.client.load_index(self.index)  # the next query sees the new rule

    async def _settle(self, job_id: str) -> None:
        """Wait briefly for add_docs to finish building. add_docs already stored the doc, so if the wait fails the
        next load_index picks it up once Moss is done; until then the exact match covers the rule."""
        if not job_id:
            return
        try:
            await self.client.wait_for_job(job_id, poll_interval_seconds=0.5, timeout_seconds=JOB_WAIT_S)
        except Exception as e:  # noqa: BLE001
            log.warning("Moss job %s not confirmed: %s: %s", job_id, type(e).__name__, e)

    async def _query(self, text: str, top_k: int) -> list[dict[str, Any]]:
        await self.client.load_index(self.index)
        result = await self.client.query(self.index, text, self.sdk.QueryOptions(top_k=top_k, alpha=1.0))
        return [{"id": d.id, "score": round(float(d.score), 4)} for d in result.docs]


@dataclass(frozen=True)
class Outcome:
    """How a call went, for the run's log. used=False: Moss is off, so nothing was asked."""

    used: bool = False
    error: str | None = None
    matches: tuple[RuleMatch, ...] = ()
    source: str | None = None  # live · fixture


class RuleMemory:
    """Saved rules in one Moss index. The backend is built on first use, so a missing SDK is a failed call."""

    def __init__(self, backend: Callable[[], Backend], index: str = INDEX):
        self._make, self.index = backend, index
        self._backend: Backend | None = None

    def _call(self, request: dict[str, Any], op: Callable[[Backend], Any], live_first: bool = False,
              read: Callable[[Any], tuple[RuleMatch, ...]] = lambda response: ()) -> Outcome:
        """op(backend) returns the JSON to record; read turns the (live or recorded) response into matches."""
        def fn(_request, _timeout):
            if self._backend is None:
                self._backend = self._make()
            return op(self._backend)

        try:
            r = replay.call_outside(SERVICE, {"index": self.index, **request}, fn, timeout=TIMEOUT_S,
                                    live_first=live_first)
            matches = read(r.response)
        except Exception as e:  # noqa: BLE001 - any failure means no matches; the exact match takes over
            return Outcome(used=True, error=_why(e, live_first))
        return Outcome(used=True, matches=matches, source=r.source)

    def index_rule(self, rule_id: str, text: str, term_type: str, counterparty: str, label: str = "") -> Outcome:
        meta = {"term_type": str(term_type), "counterparty": counterparty, "label": label}

        def upsert(b: Backend) -> dict[str, str]:
            b.upsert(rule_id, text, meta)
            return {"upserted": rule_id}

        return self._call({"op": "upsert", "id": rule_id, "text": text, "metadata": meta}, upsert)

    def drop_rule(self, rule_id: str) -> Outcome:
        def delete(b: Backend) -> dict[str, list[str]]:
            b.delete([rule_id])
            return {"deleted": [rule_id]}

        return self._call({"op": "delete", "ids": [rule_id]}, delete)

    def search(self, text: str, live_first: bool = False) -> Outcome:
        return self._call({"op": "query", "text": text, "top_k": TOP_K}, lambda b: b.query(text, TOP_K), live_first,
                          read=lambda response: tuple(RuleMatch(str(m["id"]), Decimal(str(m["score"])))
                                                      for m in response))


def _why(e: Exception, live_first: bool) -> str:
    if isinstance(e, replay.OutsideCallFailed):
        if replay.demo_mode() and not live_first:
            return "no recorded answer in DEMO_MODE"
        # "moss/<key>: live failed 2x (TimeoutError: ...); no fixture at <path>" -> the part people need
        return str(e).split(": ", 1)[-1].rsplit("; no fixture", 1)[0]
    return f"{type(e).__name__}: {e}"


MEMORY: RuleMemory | None = None  # tests set a RuleMemory over a fake backend
_built: dict[tuple[str, str], RuleMemory] = {}


def credentials() -> tuple[str, str]:
    return os.getenv("MOSS_PROJECT_ID", "").strip(), os.getenv("MOSS_API_KEY", "").strip()


def configured() -> bool:
    return all(credentials())


def recorded() -> bool:
    d = replay.FIXTURES / SERVICE
    return d.is_dir() and any(d.glob("*.json"))


def _sdk(creds: tuple[str, str]) -> Backend:
    if not all(creds):
        raise RuntimeError("MOSS_PROJECT_ID and MOSS_API_KEY aren't set")
    return SdkBackend(*creds)


def memory() -> RuleMemory | None:
    """Moss with the keys, or in DEMO_MODE once a run with Moss was recorded; None means Moss is off."""
    if MEMORY is not None:
        return MEMORY
    if not configured() and not (replay.demo_mode() and recorded()):
        return None
    creds = credentials()
    if creds not in _built:
        _built[creds] = RuleMemory(lambda: _sdk(creds))
    return _built[creds]


def index_rule(rule_id: str, text: str, term_type: str, counterparty: str, label: str = "") -> Outcome:
    m = memory()
    return m.index_rule(rule_id, text, term_type, counterparty, label) if m else Outcome()


def drop_rule(rule_id: str) -> Outcome:
    m = memory()
    return m.drop_rule(rule_id) if m else Outcome()


def search(text: str, live_first: bool = False) -> Outcome:
    m = memory()
    return m.search(text, live_first) if m else Outcome()


# ---------------------------------------------------------------- verify step (docs/design.md, Setup runbook row 10)

RULE_1_CLAUSE = ("Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice "
                 "to Supplier.")
REWORDED_CLAUSE = ("Northmart may, in its sole judgment, charge a display fee of up to $1,500 a month once it has told "
                   "Supplier in writing.")
CHECK_CLAUSES = [
    RULE_1_CLAUSE,
    REWORDED_CLAUSE,
    "Northmart may, at its discretion, charge a spoilage fee for damaged product that stores return.",
]


def main(argv: list[str] | None = None) -> int:
    """Index Rule #1's clause (deal §5.4) as the demo does (same id and text), then print how similar each clause
    is to it: by default the same sentence, a reworded one and an unrelated fee. Needs the Moss keys in .env."""
    from dotenv import load_dotenv

    load_dotenv()
    clauses = (argv if argv is not None else sys.argv[1:]) or CHECK_CLAUSES
    if not configured():
        print("Set MOSS_PROJECT_ID and MOSS_API_KEY in .env first.")
        return 2
    m = memory()
    saved = m.index_rule("rule-1", RULE_1_CLAUSE, "fee_discretion", "Northmart", "Rule #1")
    if saved.error:
        print(f"Couldn't index Rule #1: {saved.error}")
        return 1
    from api.engine.policy import load_policy

    floor = load_policy().rule_match_similarity
    for clause in clauses:
        found = m.search(clause)
        score = next((x.similarity for x in found.matches if x.rule_id == "rule-1"), None)
        verdict = found.error or ("no match" if score is None else f"{score:.2f} "
                                  + ("matches Rule #1" if score >= floor else f"below {floor}: exact match decides"))
        print(f"{verdict:<40} {clause}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

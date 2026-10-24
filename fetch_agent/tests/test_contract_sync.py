"""The recorded fixtures are real API shapes, and the agent's models only read fields the API has.

Runs wherever api/contracts.py imports (it needs only pydantic); skipped otherwise.
"""

import pytest

from fetch_agent import models
from fetch_agent.tests.conftest import FIXTURES, load

contracts = pytest.importorskip("api.contracts")

PAIRS = [(models.Summary, contracts.Summary), (models.Totals, contracts.Totals), (models.Dispute, contracts.Dispute),
         (models.DisputeLine, contracts.DisputeLine), (models.Question, contracts.Question),
         (models.Approval, contracts.Approval), (models.ApprovalLine, contracts.ApprovalLine),
         (models.AnswerResponse, contracts.AnswerResponse), (models.Answer, contracts.Answer),
         (models.Rule, contracts.Rule)]


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("*.json")))
def test_fixture_matches_the_contract(name):
    contract = contracts.Summary if name.startswith("summary-") else contracts.AnswerResponse
    contract.model_validate(load(name))


@pytest.mark.parametrize("ours, theirs", PAIRS)
def test_agent_models_read_only_contract_fields(ours, theirs):
    assert set(ours.model_fields) <= set(theirs.model_fields)


def test_api_fixture_summary_still_parses():
    fixtures = pytest.importorskip("api.stubs.fixtures")
    s = models.Summary.model_validate(fixtures.summary().model_dump(mode="json"))
    assert [d.id for d in s.open_disputes] == ["D-0417"]

"""Judge's scenario box (F14) and Deal Coach (F13), for one account (Peak Bar's by default)."""

from fastapi import APIRouter, Depends, Query

from api import accounts, pipeline, scenario as scenario_mod
from api.auth import limit
from api.agents import coach as coach_agent
from api.contracts import CoachResponse, ScenarioExample, ScenarioRequest, ScenarioResponse
from api.routes.runs import account_or_404
from api.stubs import fixtures

router = APIRouter(tags=["scenario"])


@router.post("/scenario", response_model=ScenarioResponse, dependencies=[Depends(limit("ai"))])
def scenario(req: ScenarioRequest, account: str = Query(default=accounts.DEFAULT)) -> ScenarioResponse:
    """A pasted clause and a charge, through the reader, engine and gate, against the account's deal
    (api/scenario.py)."""
    return scenario_mod.run(req, account=account_or_404(account))


@router.get("/scenario/examples", response_model=list[ScenarioExample])
def examples() -> list[ScenarioExample]:
    return scenario_mod.EXAMPLES


@router.post("/coach", response_model=CoachResponse, dependencies=[Depends(limit("ai"))])
def coach(refresh: bool = Query(default=False), account: str = Query(default=accounts.DEFAULT)) -> CoachResponse:
    """Redlines for the account's next deal in draft from its newest finished invoice-month run (Peak Bar's March);
    before one, Peak Bar gets the recorded fake run's and another account none."""
    found = account_or_404(account)
    run = next((r for r in reversed(list(pipeline.RUNS.values()))
                if r.account.id == found.id and r.kind == found.invoice.month and r.done), None)
    if run is None:
        return fixtures.coach() if found.id == accounts.DEFAULT else CoachResponse(draft_doc_id="", redlines=[])
    if run.coach is None or refresh:
        run.coach = coach_agent.coach(pipeline.coach_costs(run), account=found)
    return run.coach

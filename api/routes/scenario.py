"""Judge's scenario box (F14) and Deal Coach (F13)."""

from fastapi import APIRouter, Query

from api import pipeline, scenario as scenario_mod
from api.agents import coach as coach_agent
from api.contracts import CoachResponse, ScenarioExample, ScenarioRequest, ScenarioResponse
from api.stubs import fixtures

router = APIRouter(tags=["scenario"])


@router.post("/scenario", response_model=ScenarioResponse)
def scenario(req: ScenarioRequest) -> ScenarioResponse:
    """A pasted clause and a charge, through the reader, engine and gate (api/scenario.py)."""
    return scenario_mod.run(req)


@router.get("/scenario/examples", response_model=list[ScenarioExample])
def examples() -> list[ScenarioExample]:
    return scenario_mod.EXAMPLES


@router.post("/coach", response_model=CoachResponse)
def coach(refresh: bool = Query(default=False)) -> CoachResponse:
    """Redlines for next month's draft from the newest finished March run; the recorded fake run's otherwise."""
    run = next((r for r in reversed(list(pipeline.RUNS.values())) if r.kind == "march" and r.done), None)
    if run is None:
        return fixtures.coach()
    if run.coach is None or refresh:
        run.coach = coach_agent.coach(pipeline.coach_costs(run))
    return run.coach

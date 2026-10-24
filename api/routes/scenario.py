"""Judge's scenario box and Deal Coach."""

from fastapi import APIRouter

from api.contracts import CoachResponse, ScenarioRequest, ScenarioResponse
from api.stubs import fixtures

router = APIRouter(tags=["scenario"])


@router.post("/scenario", response_model=ScenarioResponse)
def scenario(req: ScenarioRequest) -> ScenarioResponse:
    return ScenarioResponse(stub=True, decision=None, finding=None, evidence=[],
                            message="Scenario box isn't built yet (F14). The request was valid.")


@router.post("/coach", response_model=CoachResponse)
def coach() -> CoachResponse:
    return fixtures.coach()

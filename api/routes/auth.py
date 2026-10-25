"""The admin's sign-in: an ID and password in, the access code the admin's actions carry out (api/auth.py)."""

from fastapi import APIRouter, Depends, HTTPException

from api import auth
from api.contracts import LoginRequest, LoginResponse

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(auth.limit("login"))])
def login(body: LoginRequest) -> LoginResponse:
    try:
        ok, code = auth.login(body.username, body.password)
    except auth.NotSetUp as e:
        raise HTTPException(503, str(e)) from e
    if not ok:
        raise HTTPException(401, "That ID and password don't match.")
    return LoginResponse(code=code)

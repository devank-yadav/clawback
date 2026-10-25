"""Sign-in (api/auth.py, api/users.py): POST /auth/login sets the session cookie, POST /auth/logout ends it, GET
/auth/me says who is signed in. The cookie is HttpOnly and SameSite=Lax, and Secure when PUBLIC_BASE_URL is https."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import auth, users
from api.contracts import LoginRequest, LoginResponse, MeResponse, SessionSupplier, SessionUser

router = APIRouter(tags=["auth"])


def _secure() -> bool:
    return (os.getenv("PUBLIC_BASE_URL") or "").lower().startswith("https://")


def _user(u: users.User) -> SessionUser:
    return SessionUser(id=u.id, email=u.email, name=u.name, role=u.role)


def _supplier(u: users.User) -> SessionSupplier:
    s = users.supplier(u.supplier_id)
    from api import accounts

    owned = [a.id for a in accounts.every() if (a.config.supplier or a.id) == u.supplier_id]
    return SessionSupplier(id=u.supplier_id, name=s.name if s else u.supplier_id, account_ids=owned)


@router.post("/auth/login", response_model=LoginResponse, dependencies=[Depends(auth.limit("login"))])
def login(body: LoginRequest, response: Response) -> LoginResponse:
    try:
        user, code = auth.login(body.login, body.password)
    except auth.NotSetUp as e:
        raise HTTPException(503, str(e)) from e
    if user is None:
        raise HTTPException(401, "That email and password don't match.")
    token, session = users.start_session(user)
    response.set_cookie(users.COOKIE, token, max_age=int(users.session_hours() * 3600), httponly=True,
                        samesite="lax", secure=_secure(), path="/")
    return LoginResponse(code=code, user=_user(user), supplier=_supplier(user))


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    users.end_session(request.cookies.get(users.COOKIE))
    response.delete_cookie(users.COOKIE, path="/", httponly=True, samesite="lax", secure=_secure())
    return {"ok": True}


@router.get("/auth/me", response_model=MeResponse)
def me(request: Request) -> MeResponse:
    user = users.user_for(request.cookies.get(users.COOKIE))
    if user:
        return MeResponse(user=_user(user), supplier=_supplier(user), auth_required=users.auth_required())
    if users.auth_required():
        raise HTTPException(401, "Not signed in.")
    return MeResponse(auth_required=False)

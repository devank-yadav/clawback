"""The only two calls the assistant makes: GET /summary and POST /questions/{id}/answer.

10-second timeout and one retry. GET /summary retries on any network error or 5xx. The answer POST retries only
when the request never left (connection refused or timed out while connecting): a lost reply to an UNDO that did
go through must not undo a second rule.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from fetch_agent.models import AnswerResponse, Summary

TIMEOUT_S = 10.0


class ClawbackError(Exception):
    """status is the HTTP status, or None when Clawback couldn't be reached at all."""

    def __init__(self, message: str, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


class ClawbackClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None):
        self.token = token
        self.http = http or httpx.Client(base_url=base_url.rstrip("/"), timeout=TIMEOUT_S)

    def summary(self) -> Summary:
        r = self._call("GET", "/summary", idempotent=True, headers={"Authorization": f"Bearer {self.token}"})
        return Summary.model_validate(r.json())

    def answer(self, question_id: str, text: str) -> AnswerResponse:
        r = self._call("POST", f"/questions/{quote(question_id, safe='')}/answer", idempotent=False,
                       json={"text": text, "from_role": "owner"})
        return AnswerResponse.model_validate(r.json())

    def _call(self, method: str, path: str, idempotent: bool, **kw) -> httpx.Response:
        for attempt in (1, 2):
            try:
                r = self.http.request(method, path, **kw)
            except httpx.TransportError as e:
                never_sent = isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout))
                if attempt == 1 and (idempotent or never_sent):
                    continue
                raise ClawbackError(f"{method} {path} failed: {e.__class__.__name__}") from e
            if r.status_code >= 500 and attempt == 1 and idempotent:
                continue
            if r.status_code >= 400:
                raise ClawbackError(f"{method} {path} returned {r.status_code}", r.status_code, _detail(r))
            return r
        raise AssertionError("unreachable")


def _detail(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail) if detail else r.text[:200]

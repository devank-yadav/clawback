"""The agents' system prompts (prompts/*.md), filled in for one account: render(name, account).

The files name the account through placeholders: {brand} ("Peak Bar Co."), {brand_kind} ("snack brand") and
{distributor} ("Northmart"). Nothing else in a file is touched, so a prompt renders for Peak Bar exactly as it read
before the placeholders: recorded AI answers are matched by model, system prompt and input, and
api/tests/test_prompts.py checks every prompt still renders byte for byte as recorded. A placeholder no account
fills is an error, never left in the text.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from api import accounts

DIR = Path(__file__).parent / "prompts"
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@cache
def _text(name: str) -> str:
    return (DIR / f"{name}.md").read_text()


def names() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.md"))


def values(account: accounts.Account | str | None = None) -> dict[str, str]:
    a = accounts.resolve(account)
    return {"brand": a.brand.name, "brand_kind": a.brand.kind, "distributor": a.distributor.name}


def render(name: str, account: accounts.Account | str | None = None, **extra: str) -> str:
    """prompts/<name>.md for this account (the current one by default). `extra` fills a prompt's own placeholders,
    e.g. the remittance reader's {products}."""
    fill = {**values(account), **extra}

    def one(m: re.Match[str]) -> str:
        if m.group(1) not in fill:
            raise KeyError(f"prompts/{name}.md: no account value for {{{m.group(1)}}}")
        return fill[m.group(1)]

    return _PLACEHOLDER.sub(one, _text(name))

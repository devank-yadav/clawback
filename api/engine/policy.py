"""Load the owner policy from config/policy.yaml."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml

from api.engine.types import Policy

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"


def load_policy(path: str | Path = DEFAULT_PATH) -> Policy:
    raw = yaml.safe_load(Path(path).read_text())
    return Policy(
        auto_dispute_limit=Decimal(str(raw["auto_dispute_limit_usd"])),
        controller_approval_over=Decimal(str(raw["controller_approval_over_usd"])),
        confidence_floor=Decimal(str(raw["confidence_floor"])),
        match_tolerance=Decimal(str(raw["match_tolerance_usd"])),
        rule_match_similarity=Decimal(str(raw["rule_match_similarity"])),
        reminder_after_minutes=int(raw["reminder_after_minutes"]),
        discretion_words=tuple(raw["discretion_words"]),
        approved_amendment_senders=tuple(s.lower() for s in raw["approved_amendment_senders"]),
    )

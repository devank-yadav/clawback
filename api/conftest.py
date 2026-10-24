"""Tests never reach a live service.

The app loads .env when it's imported, so real keys could reach the tests, and a background run that outlives its
test would use them. So for the whole test session every live key is set to "" (load_dotenv() never refills a
variable that's already set), each test starts with them unset, and building a real Claude client raises: a test
passes a fake (or patches anthropic.Anthropic), and a leftover thread fails fast instead of calling out.
"""

import os

import anthropic
import pytest

LIVE = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "MOSS_API_KEY",
    "QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "OWNER_PHONE", "CONTROLLER_PHONE", "SMS_CHANNEL",
    "NESSIE_API_KEY", "NESSIE_ACCOUNT_ID", "NESSIE_BASE_URL", "DATABASE_URL", "PUBLIC_BASE_URL",
    "CLAWBACK_READONLY_TOKEN", "AGENTVERSE_API_KEY", "ELASTIC_URL", "ELASTIC_API_KEY",
    "DEMO_MODE", "RECORD_FIXTURES",
)

for _name in LIVE:
    os.environ[_name] = ""


class _NoLiveClaude:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("tests don't call Claude: pass a fake client or patch anthropic.Anthropic")


anthropic.Anthropic = _NoLiveClaude


@pytest.fixture(autouse=True)
def _no_live_keys(monkeypatch):
    for name in LIVE:
        monkeypatch.delenv(name, raising=False)

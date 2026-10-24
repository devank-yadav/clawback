"""SMS_CHANNEL=whatsapp: the same texts and replies over Twilio's WhatsApp Sandbox. Offline; Twilio is faked."""

import sys
import types

import pytest
from fastapi.testclient import TestClient

from api.integrations import sms
from api.main import app

OWNER, FROM = "+15550100001", "+14155550100"  # fake numbers


@pytest.fixture
def keys(monkeypatch):
    for k, v in {"TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "test-token-not-real", "TWILIO_FROM": FROM,
                 "OWNER_PHONE": OWNER, "DEMO_MODE": "false"}.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def twilio(monkeypatch):
    """A stand-in for the twilio package that records messages.create calls."""
    sent: list[dict] = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.messages = types.SimpleNamespace(create=lambda **kw: sent.append(kw))

    modules = {"twilio": types.ModuleType("twilio"), "twilio.base": types.ModuleType("twilio.base"),
               "twilio.base.exceptions": types.ModuleType("twilio.base.exceptions"),
               "twilio.http": types.ModuleType("twilio.http"),
               "twilio.http.http_client": types.ModuleType("twilio.http.http_client"),
               "twilio.rest": types.ModuleType("twilio.rest")}
    modules["twilio.base.exceptions"].TwilioRestException = type("TwilioRestException", (Exception,), {})
    modules["twilio.http.http_client"].TwilioHttpClient = lambda **kw: None
    modules["twilio.rest"].Client = Client
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return sent


@pytest.mark.parametrize("value, expected", [(None, "sms"), ("sms", "sms"), ("WhatsApp", "whatsapp"), ("fax", "sms")])
def test_channel_defaults_to_sms(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("SMS_CHANNEL", raising=False)
    else:
        monkeypatch.setenv("SMS_CHANNEL", value)
    assert sms.channel() == expected


def test_address_adds_the_prefix_once(monkeypatch):
    monkeypatch.setenv("SMS_CHANNEL", "whatsapp")
    assert sms.address(OWNER) == f"whatsapp:{OWNER}"
    assert sms.address(f"whatsapp:{OWNER}") == f"whatsapp:{OWNER}"
    monkeypatch.setenv("SMS_CHANNEL", "sms")
    assert sms.address(f"whatsapp:{OWNER}") == OWNER


def test_sms_send_uses_plain_numbers(keys, twilio, monkeypatch):
    monkeypatch.delenv("SMS_CHANNEL", raising=False)
    assert sms.send("owner", "hello") == "sent"
    assert twilio == [{"to": OWNER, "from_": FROM, "body": "hello"}]


def test_whatsapp_send_prefixes_both_numbers(keys, twilio, monkeypatch):
    monkeypatch.setenv("SMS_CHANNEL", "whatsapp")
    assert sms.send("owner", "Approve credit memo of $2,730 (3 lines)?") == "sent"
    assert twilio == [{"to": f"whatsapp:{OWNER}", "from_": f"whatsapp:{FROM}",
                       "body": "Approve credit memo of $2,730 (3 lines)?"}]


def test_whatsapp_send_still_skipped_in_demo_mode(keys, twilio, monkeypatch):
    monkeypatch.setenv("SMS_CHANNEL", "whatsapp")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert sms.send("owner", "hello") == "not sent (DEMO_MODE)"
    assert twilio == []


def test_whatsapp_reply_reaches_the_owner(monkeypatch):
    """A WhatsApp From ("whatsapp:+1…") is recognized as the owner; a stranger on WhatsApp still gets nothing."""
    monkeypatch.setenv("SMS_CHANNEL", "whatsapp")
    monkeypatch.setenv("OWNER_PHONE", OWNER)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    client = TestClient(app)
    form = {"From": f"whatsapp:{OWNER}", "To": f"whatsapp:{FROM}", "Body": "accept"}
    owner = client.post("/webhooks/twilio/sms", data=form)
    assert owner.status_code == 200 and "<Message>" in owner.text
    stranger = client.post("/webhooks/twilio/sms", data={**form, "From": "whatsapp:+15559999999"})
    assert stranger.status_code == 200 and "<Message>" not in stranger.text

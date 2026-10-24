"""Tests never reach a live service.

The app loads .env when it's imported, so real keys could reach the tests, and a background run that outlives its
test would use them. So for the whole test session:
- .env is never read: load_dotenv() is a no-op and PYTHON_DOTENV_DISABLED is set. (Blanking keys alone wasn't
  enough: a test that first imported api.main after the fixture below unset them got them back from .env.)
- every live key is set to "", and each test starts with them unset;
- building a real Claude or Gemini client raises: a test passes a fake (or patches the class), and a leftover
  thread fails fast instead of calling out;
- sockets and DNS only reach this machine, and proxy settings are dropped (a local proxy would otherwise carry a
  request out), so anything that slips through fails at once instead of hanging.

A test marked @pytest.mark.live gets the real .env and the network, and runs only with `pytest --live`.
"""

import ipaddress
import os
import socket
from pathlib import Path

import anthropic
import dotenv
import dotenv.main
import pytest

ROOT = Path(__file__).resolve().parents[1]

LIVE = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "MOSS_API_KEY",
    "QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "OWNER_PHONE", "CONTROLLER_PHONE", "SMS_CHANNEL",
    "NESSIE_API_KEY", "NESSIE_ACCOUNT_ID", "NESSIE_BASE_URL", "NESSIE_POLL", "DATABASE_URL", "PUBLIC_BASE_URL",
    "CLAWBACK_READONLY_TOKEN", "AGENTVERSE_API_KEY", "ELASTIC_URL", "ELASTIC_API_KEY",
    "DEMO_MODE", "RECORD_FIXTURES",
)

for _name in LIVE:
    os.environ[_name] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
PROXIES = {k: os.environ.pop(k) for k in list(os.environ) if k.lower() in ("http_proxy", "https_proxy", "all_proxy")}

_real = {"load_dotenv": dotenv.load_dotenv, "Anthropic": anthropic.Anthropic}
dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *a, **k: False  # also for python-dotenv before 1.2


class _NoLiveClaude:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("tests don't call Claude: pass a fake client or patch anthropic.Anthropic")


class _NoLiveGemini:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("tests don't call Gemini: pass a fake gemini client")


anthropic.Anthropic = _NoLiveClaude
try:
    from google import genai

    _real["genai.Client"] = genai.Client
    genai.Client = _NoLiveGemini
except ImportError:
    pass

_network = {"open": False}
_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo


def _local(host) -> bool:
    if host in (None, "", "localhost") or isinstance(host, int):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _check(sock, address):
    if not _network["open"] and sock.family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        raise OSError(f"tests don't use the network (tried {address[0]}); mark the test @pytest.mark.live")


def _guarded_connect(self, address):
    _check(self, address)
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    _check(self, address)
    return _connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _network["open"] and not _local(host.decode() if isinstance(host, bytes) else host):
        raise socket.gaierror(f"tests don't use the network (tried to look up {host})")
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect, socket.socket.connect_ex = _guarded_connect, _guarded_connect_ex
socket.getaddrinfo = _guarded_getaddrinfo


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="also run @pytest.mark.live tests (real .env, network)")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: uses the real .env and the network; runs only with --live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test: run with pytest --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_live_keys(request, monkeypatch):
    for name in LIVE:
        monkeypatch.delenv(name, raising=False)
    if request.node.get_closest_marker("live") is None:
        yield
        return
    for name, value in [*PROXIES.items(), *dotenv.dotenv_values(ROOT / ".env").items()]:
        if value is not None:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(anthropic, "Anthropic", _real["Anthropic"])
    if "genai.Client" in _real:
        monkeypatch.setattr(genai, "Client", _real["genai.Client"])
    _network["open"] = True
    try:
        yield
    finally:
        _network["open"] = False

"""The assistant's tests never reach a live service (same idea as api/conftest.py, smaller).

.env is never read, the agent's keys are unset for every test, and sockets only reach this machine, so anything
that slips past a fake fails at once instead of calling Clawback, Agentverse or ASI:One.
"""

import ipaddress
import json
import os
import socket
from pathlib import Path

import pytest

KEYS = ("CLAWBACK_API_URL", "CLAWBACK_READONLY_TOKEN", "CLAWBACK_AGENT_SEED", "CLAWBACK_OWNER_ADDRESSES",
        "AGENTVERSE_API_KEY")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo


def _local(host) -> bool:
    if host in (None, "", "localhost") or isinstance(host, int):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        raise OSError(f"fetch_agent tests don't use the network (tried {address[0]})")
    return _connect(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _local(host.decode() if isinstance(host, bytes) else host):
        raise socket.gaierror(f"fetch_agent tests don't use the network (tried to look up {host})")
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guarded_connect
socket.getaddrinfo = _guarded_getaddrinfo


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    for name in KEYS:
        monkeypatch.delenv(name, raising=False)


def load(name: str) -> dict:
    """A response the API really gave, recorded in DEMO_MODE (see tests/fixtures/README.md)."""
    return json.loads((FIXTURES / name).read_text())

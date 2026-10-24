"""api/conftest.py keeps a filled .env and the network away from the tests."""

import os
import socket

import dotenv
import httpx
import pytest

from api.conftest import LIVE


def test_live_keys_are_unset_and_dotenv_is_off(tmp_path):
    assert not any(os.getenv(name) for name in LIVE)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=real-looking-key\nTWILIO_AUTH_TOKEN=real-looking-token\n")
    assert dotenv.load_dotenv(env) is False and not os.getenv("GEMINI_API_KEY") and not os.getenv("TWILIO_AUTH_TOKEN")


def test_the_network_fails_fast():
    with pytest.raises(OSError):
        socket.getaddrinfo("api.nessieisreal.com", 443)
    with pytest.raises(OSError):
        socket.create_connection(("8.8.8.8", 53), timeout=5)
    with pytest.raises(httpx.HTTPError):
        httpx.get("https://generativelanguage.googleapis.com/", timeout=5)


def test_real_clients_cant_be_built():
    import anthropic
    from google import genai

    for make in (lambda: anthropic.Anthropic(api_key="x"), lambda: genai.Client(api_key="x")):
        with pytest.raises(RuntimeError):
            make()

"""Deploy files stay in step with the API's routes (docs/deploy.md). Text checks only: no Docker, no network."""

import re
from pathlib import Path

import yaml

from api.main import app
from api.routes import webhooks

ROOT = Path(__file__).resolve().parents[2]
CADDY = (ROOT / "deploy" / "Caddyfile").read_text()
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
ENV_NAMES = {line.split("=", 1)[0] for line in (ROOT / ".env.example").read_text().splitlines()
             if "=" in line and not line.startswith("#")}


def paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_health_is_unprefixed_and_caddy_strips_api():
    # /api/health over HTTPS reaches the API's /health because Caddy strips /api.
    assert "/health" in paths()
    assert "handle_path /api/*" in CADDY


def test_twilio_webhook_is_proxied_unstripped():
    # Twilio signs PUBLIC_BASE_URL + PATH, so the public path must equal the API path.
    assert webhooks.PATH.startswith("/webhooks/") and webhooks.PATH in paths()
    assert re.search(r"handle /webhooks/\*\s*\{\s*reverse_proxy api:8000", CADDY)


def test_caddy_site_is_the_domain_and_rest_goes_to_web():
    assert CADDY.lstrip().splitlines()[0] != "" and "{$DOMAIN} {" in CADDY
    assert "reverse_proxy web:3000" in CADDY


def test_compose_has_the_three_services_and_only_caddy_is_public():
    s = COMPOSE["services"]
    assert set(s) == {"api", "web", "caddy"}
    assert "ports" not in s["api"] and "ports" not in s["web"]
    assert "80:80" in s["caddy"]["ports"] and "443:443" in s["caddy"]["ports"]
    assert s["api"]["build"]["dockerfile"] == "api/Dockerfile"
    assert (ROOT / "api" / "Dockerfile").exists() and (ROOT / "web" / "Dockerfile").exists()


def test_env_example_names_the_deploy_keys():
    assert {"DOMAIN", "PUBLIC_BASE_URL", "DATABASE_URL", "SMS_CHANNEL"} <= ENV_NAMES


def test_runtime_requirements_cover_policy_yaml():
    # api/engine/policy.py imports yaml at runtime; the image installs only api/requirements.txt.
    reqs = (ROOT / "api" / "requirements.txt").read_text().lower()
    assert "pyyaml" in reqs


def test_secrets_stay_out_of_the_image():
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    assert ".env" in ignore and ".git" in ignore

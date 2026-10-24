# Targets are wired up as each part lands. Keep target names stable; the guides and the demo checklist use them.
.PHONY: dev api web test acceptance seed db-check eval eval-agent publish-score record demo reset check-data \
	deploy-check fetch-agent fetch-agent-connect fetch-agent-test

# The repo's .venv when there is one (it has the packages), else python3 (Macs often have no "python").
# Override with: make test PYTHON=python
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
# The Clawback Assistant has its own venv (uagents pins its own packages): fetch_agent/README.md
FETCH_PYTHON ?= $(if $(wildcard fetch_agent/.venv/bin/python),fetch_agent/.venv/bin/python,$(PYTHON))

api:
	$(PYTHON) -m uvicorn api.main:app --reload --reload-dir api --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	$(PYTHON) -m pytest -q api

# The P0 acceptance tests (docs/design.md, Feature spec), offline and in DEMO_MODE, then the eval score.
# F1 seed and the app on Postgres: their database tests run only with TEST_DATABASE_URL set (api/tests/test_db_seed.py,
# test_db_runtime.py); `make seed` twice and `make db-check` are the real checks. Not covered here yet: the screens in
# web/ (F6, F7, F12 scoreboard).
acceptance:
	$(PYTHON) -m pytest -q api/tests/test_acceptance_p0.py api/tests/test_pipeline.py api/tests/test_reader.py \
		api/engine/tests/test_quote_check.py api/engine/tests/test_allowed.py api/engine/tests/test_gate.py \
		api/engine/tests/test_eval_harness.py api/tests/test_replay.py api/tests/test_routes.py api/tests/test_disputes.py \
		api/tests/test_books.py api/tests/test_coach_scenario.py \
		api/tests/test_readers.py api/tests/test_audit.py api/tests/test_sms_channel.py \
		api/tests/test_eval_agent.py api/tests/test_nessie.py api/tests/test_db_seed.py api/tests/test_moss.py \
		api/tests/test_db_runtime.py
	$(PYTHON) eval/run.py

seed:
	$(PYTHON) -m api.db.seed

# Read-only: the app's rows come from Postgres and equal data/, the newest saved runs, and the cap query.
db-check:
	$(PYTHON) -m api.db.check

eval:
	$(PYTHON) eval/run.py

# Readers and agents in the loop: about 111 AI calls live (see --estimate); free in DEMO_MODE once recorded.
eval-agent:
	RECORD_FIXTURES=1 $(PYTHON) eval/run.py --mode agent

# Copy the local scores (gitignored) into eval/published/, which is committed and ships in the API image.
publish-score:
	mkdir -p eval/published
	cp eval/latest-agent.json eval/published/agent.json
	cp eval/latest.json eval/published/engine.json

record:
	RECORD_FIXTURES=1 $(PYTHON) -m api.run_demo --portal --coach

demo:
	DEMO_MODE=true $(MAKE) dev

# Laptop: make reset. The deployed site: make reset API=https://clawback.biz/api CLAWBACK_ADMIN_TOKEN=<token>
reset:
	curl -s -X POST $(if $(CLAWBACK_ADMIN_TOKEN),-H "Authorization: Bearer $(CLAWBACK_ADMIN_TOKEN)") \
		$(or $(API),http://localhost:8000)/demo/reset

check-data:
	$(PYTHON) scripts/check_data.py && $(PYTHON) scripts/check_eval.py

# Clawback Assistant for ASI:One (Fetch.ai track): run it, connect its Agentverse mailbox with AGENTVERSE_API_KEY
# while it runs (same machine), and its offline tests. Runbook: fetch_agent/README.md.
fetch-agent:
	$(FETCH_PYTHON) -m fetch_agent

fetch-agent-connect:
	$(FETCH_PYTHON) -m fetch_agent.connect

fetch-agent-test:
	$(FETCH_PYTHON) -m pytest -q fetch_agent

# Offline deploy check (docs/deploy.md): compose file resolves, and the Caddyfile parses when caddy or a Docker daemon is around.
# Uses .env.example and a placeholder domain, so it needs no keys and no network (except pulling caddy:2 the first time).
deploy-check:
	$(PYTHON) -m pytest -q api/tests/test_deploy.py
	CLAWBACK_ENV_FILE=.env.example DOMAIN=clawback.example.com docker compose config -q && echo "compose ok"
	@if command -v caddy >/dev/null; then DOMAIN=clawback.example.com caddy validate --adapter caddyfile --config deploy/Caddyfile; \
	elif docker info >/dev/null 2>&1; then docker run --rm -e DOMAIN=clawback.example.com -v "$(CURDIR)/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile; \
	else echo "caddy validate skipped: no caddy binary and no Docker daemon"; fi

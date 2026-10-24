# Targets are wired up as each part lands. Keep target names stable; the guides and the demo checklist use them.
.PHONY: dev api web test acceptance seed eval record demo reset check-data

# Macs often have only python3. Override with: make test PYTHON=python
PYTHON ?= python3

api:
	$(PYTHON) -m uvicorn api.main:app --reload --reload-dir api --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	$(PYTHON) -m pytest -q api

# The P0 acceptance tests (docs/design.md, Feature spec), offline and in DEMO_MODE, then the eval score.
# Not covered here yet: F1 seed (needs api/db/seed.py) and the screens in web/ (F6, F7, F12 scoreboard).
acceptance:
	$(PYTHON) -m pytest -q api/tests/test_acceptance_p0.py api/tests/test_pipeline.py api/tests/test_reader.py \
		api/engine/tests/test_quote_check.py api/engine/tests/test_allowed.py api/engine/tests/test_gate.py \
		api/engine/tests/test_eval_harness.py api/tests/test_replay.py api/tests/test_routes.py api/tests/test_disputes.py \
		api/tests/test_books.py api/tests/test_coach_scenario.py \
		api/tests/test_readers.py api/tests/test_audit.py
	$(PYTHON) eval/run.py

seed:
	$(PYTHON) -m api.db.seed

eval:
	$(PYTHON) eval/run.py

record:
	RECORD_FIXTURES=1 $(PYTHON) -m api.run_demo --portal --coach

demo:
	DEMO_MODE=true $(MAKE) dev

reset:
	curl -s -X POST http://localhost:8000/demo/reset

check-data:
	$(PYTHON) scripts/check_data.py && $(PYTHON) scripts/check_eval.py

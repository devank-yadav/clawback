# Targets are wired up as each part lands. Keep target names stable; the guides and the demo checklist use them.
.PHONY: dev api web test seed eval record demo reset check-data

api:
	uvicorn api.main:app --reload --reload-dir api --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	pytest -q api

seed:
	python -m api.db.seed

eval:
	python eval/run.py

record:
	RECORD_FIXTURES=1 python -m api.run_demo

demo:
	DEMO_MODE=true $(MAKE) dev

reset:
	curl -s -X POST http://localhost:8000/demo/reset

check-data:
	python scripts/check_data.py && python scripts/check_eval.py

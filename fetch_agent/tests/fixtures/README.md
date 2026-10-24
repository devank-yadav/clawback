Real API responses, recorded offline on 2026-10-24 by running the API in `DEMO_MODE` (the committed
recordings in `data/fixtures/`) through FastAPI's test client:

- `summary-recorded-run.json`: GET /summary before any live run (the API's recorded demo run, `run_id` null)
- `summary-question.json`: GET /summary after the March run's first pass (Q-1 about C6 waits on Dana)
- `answer-rule.json`: POST /questions/Q-1/answer "accept if notice is at least 14 days" (Rule #1 saved)
- `summary-approval.json`: GET /summary after that answer (the $2,730 waits on Sam)
- `answer-undo.json`, `answer-undo-nothing.json`: "UNDO", then "UNDO" again (nothing left to undo)
- `answer-once.json`: "ACCEPT" on a later run's question (settled once, no rule)

`tests/test_contract_sync.py` validates every file against `api/contracts.py`, so a contract change that
breaks the agent shows up as a failing test. All names are fictional.

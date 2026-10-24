# Clawback

Clawback wins back the money distributors wrongly take from small brands' payments, and never fights a fair charge.
Built at Cal Hacks 13.0. All company names and numbers in the demo are fictional.

- Full plan: [docs/design.md](docs/design.md)
- Team brief: [docs/team/README.md](docs/team/README.md)
- Team guides: [Devank](docs/team/devank.md) · [Rishi](docs/team/rishi.md) · [Manasv](docs/team/manasv.md)
- Decisions log: [DECISIONS.md](DECISIONS.md)

## Setup (each teammate)

```bash
git clone <repo URL> clawback && cd clawback
git checkout -b <web|story|agents>
cp .env.example .env          # fill only the keys your part needs; never commit .env
npm install -g @anthropic-ai/claude-code   # if not installed
claude                        # then paste the first prompt from your guide in docs/team/
```

Python 3.11+ for `api/` and `scripts/` (`python3 -m venv .venv && source .venv/bin/activate`),
Node 20+ for `web/`. Exact dependencies are added as each part is built.

## Commands

`make dev` · `make test` · `make seed` · `make eval` · `make record` · `make demo` · `make reset` · `make check-data`

(Manasv's job 5 replaces this README with the full version; keep this setup section.)

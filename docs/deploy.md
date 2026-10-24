# Deploy runbook: clawback.biz on a Vultr VM (F19)

Goal: judges' phones open the board at `https://clawback.biz`. Tracks: MLH Vultr (hosting) and MLH GoDaddy Registry
(the `.biz` domain); the Devpost proof for both is the live URL.

Copy-paste from top to bottom. `<VM_IP>` is the VM's IPv4 address. Nothing here needs a key in the repo; Vultr,
Porkbun, GitHub and `.env` credentials never go in the repo, chat or Slack.

**State on 2026-10-24 ~05:00 PDT (checked from a laptop):** `clawback.biz` is registered at **Porkbun** (whois:
Registrar Porkbun, name servers `*.ns.porkbun.com`), so DNS is edited at Porkbun, not in a GoDaddy dashboard. It still
has Porkbun's parking records: an ALIAS on the bare domain and a wildcard `*` CNAME, both to `pixie.porkbun.com`
(today `clawback.biz` resolves to 207.207.210.107 and .229, `http://` shows the parking page, `https://` fails the TLS
handshake). No VM exists yet.

## What is in the repo

| File | Does |
| --- | --- |
| `docker-compose.yml` | `api` (FastAPI, port 8000 inside), `web` (Next.js, port 3000 inside), `caddy` (the only public ports: 80, 443, 443/udp). `api` reads `.env` through `env_file`; `restart: unless-stopped` on all three |
| `api/Dockerfile` | Python 3.11 with `api/`, `config/`, `data/` (fixtures included), `eval/`, `web/fixtures/`; one uvicorn worker, because runs, questions and rules live in memory |
| `web/Dockerfile` | `npm ci`, `npm run build` with `NEXT_PUBLIC_API_BASE=/api` and `NEXT_PUBLIC_DATA_SOURCE=live` baked in, `npm start` on 3000 |
| `deploy/Caddyfile` | `{$DOMAIN}` with automatic HTTPS. `/api/*` to the API with `/api` stripped (flushed per event), `/webhooks/*` to the API unchanged, everything else to Next.js (compressed). One access-log line per request |
| `deploy/smoke.sh` | Post-deploy check from any laptop: health, web page, http to https, HTTP/2, the event stream arriving frame by frame and uncompressed, the Twilio webhook route. Read-only: replays the recorded run, starts nothing |
| `make deploy-check` | Offline: route tests, `docker compose config`, and `caddy validate` when caddy or a Docker daemon is around |

**URL layout:**

- `https://clawback.biz/` and every screen (`/board/<run>`, and `/portal`, `/inbox`, ... once they land in `web/`) come from Next.js.
- `https://clawback.biz/api/<path>` is the API's `/<path>`: health is `/api/health` (route `/health`), the stream is `/api/runs/<id>/events`.
- `https://clawback.biz/webhooks/twilio/sms` is the Twilio webhook, not under `/api`, because the signature check rebuilds the URL as `PUBLIC_BASE_URL + /webhooks/twilio/sms`.
- The browser calls the API at `/api` on the same origin, so CORS never comes into play.

## 0. Decide first: what the VM runs

**Decided (Oct 24, 06:45): the VM runs `DEMO_MODE=false` and is the single live instance; laptops run `make demo`.**
What each setting means:

| | `DEMO_MODE=true` | `DEMO_MODE=false` |
| --- | --- | --- |
| Claude and Gemini | Replays `data/fixtures/` (free; a run takes about 6 s) | Live calls (API credits; up to about 60 s a run). The scenario box and portal replies try live first either way |
| Texts to Dana and Sam | Not sent; the question and approval wait in the app | Sent over the Twilio WhatsApp Sandbox |
| Replies from the phones | Handled (the webhook works either way) | Handled |
| "Northmart pays" | Starts the run directly | Posts a Nessie deposit; the poller starts the run |
| QuickBooks | Stand-in; ledger posts say "Simulated: DEMO_MODE is on" | Live sandbox writes, with the token caveat below |

**Only one live instance at a time.** With `DEMO_MODE=false` on the VM, every laptop runs `make demo` (DEMO_MODE on)
or has `NESSIE_POLL=off` and no Twilio or QuickBooks keys. Otherwise one Nessie deposit starts a run on every machine
that polls, Dana gets one WhatsApp question per machine, and each machine can post its own credit memo.

**QuickBooks token caveats** (only with `DEMO_MODE=false` and the four `QBO_*` keys set):

- *Access token:* Intuit's last an hour; a 401 makes the API fetch a new one once and retry.
- *Refresh token:* compose mounts `./state` into the api container and sets `QBO_TOKEN_FILE=/app/state/qbo.env`. A rotated refresh token is saved there, and a restarted or recreated container starts from it. Create the folder before the first start (step 6). If you ever paste a new refresh token into `.env` (after `invalid_grant`), delete `state/qbo.env` too, or the old saved one wins.
- The laptops and the VM share one token chain, so no QuickBooks commands from a laptop while the VM is live. Seed the database from a laptop with `DEMO_MODE=true make seed`, which skips QuickBooks.
- To keep the books simulated while texts go out live, leave the four `QBO_*` values empty in the VM's `.env`.

## 1. Accounts and access (before Sat noon)

- [ ] Vultr account verified, MLH credit on it, and Devank can log in (added as a user, or the login shared privately).
- [ ] The Porkbun login that registered `clawback.biz`.
- [ ] Admin on the GitHub repo `devank-yadav/clawback` (to add a read-only deploy key).
- [ ] Twilio console access (WhatsApp Sandbox settings).

If Vultr isn't verified by **Sat noon**, go to [Fallback](#fallback-laptop--tunnel-cut-rule).

## 2. Create the VM (Vultr dashboard)

Deploy → **Cloud Compute, Shared CPU, Regular Performance**:

- Location: **Silicon Valley** (closest to Berkeley). Image: **Ubuntu 24.04 LTS x64**.
- Plan: **2 vCPU / 4 GB / 80 GB, $20 a month ($0.03 an hour)**. Prices from vultr.com/pricing as checked on 2026-10-24: 1 vCPU / 2 GB $10, 2 vCPU / 2 GB $15, 2 vCPU / 4 GB $20. 4 GB because `npm ci` plus `next build` is the memory peak; the running stack fits in under 2 GB. If credit is tight: 1 vCPU / 2 GB plus the swap file in step 4.
- Turn **Automatic Backups off** (extra cost). Add your SSH public key under SSH Keys. Hostname `clawback`.
- About 48 hours × $0.03 ≈ **$1.50**. A stopped server still bills: destroy it after judging.

Write down the IPv4 address (`<VM_IP>`). Log the choice, e.g.
`- 2026-10-24 16:30 · Vultr VM: Regular 2 vCPU / 4 GB, Silicon Valley, Ubuntu 24.04, $0.03/h · Devank`.

## 3. DNS at Porkbun

porkbun.com → Account → Domain Management → `clawback.biz` → **DNS**:

1. **Delete** the `ALIAS` record for `clawback.biz` (value `pixie.porkbun.com`) and the `CNAME` for `*.clawback.biz` (value `pixie.porkbun.com`). Delete any `www` CNAME too. Turn off URL forwarding if it's on.
2. **Add** type `A`, host blank (the bare domain), answer `<VM_IP>`, TTL 600.
3. **Add** type `A`, host `www`, answer `<VM_IP>`, TTL 600 (optional; see step 6 for serving it).
4. Don't add `AAAA` records. Leave CAA empty (none today; that allows Let's Encrypt).

Check from a laptop; both must print only `<VM_IP>` before step 7 (Caddy needs it to get the certificate):

```bash
dig +short clawback.biz A @1.1.1.1
dig +short clawback.biz A @8.8.8.8
dig +short www.clawback.biz A @8.8.8.8     # only if you added www
```

## 4. Prepare the VM

```bash
ssh root@<VM_IP>

curl -fsSL https://get.docker.com | sh          # Docker Engine + compose plugin (official convenience script)
docker compose version
systemctl is-enabled docker                     # "enabled": containers come back after a reboot

# Vultr's Ubuntu images usually have ufw on with only SSH open. Docker-published ports bypass ufw, but be explicit:
ufw status
ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp

# Only on the 2 GB plan: swap, so the Next.js build doesn't run out of memory.
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 5. Code onto the VM

**Option A (recommended): read-only deploy key, then `git clone`.** Updates are `git pull`, rollback is
`git checkout <sha>`, and only committed code reaches the VM.

```bash
# On the VM
ssh-keygen -t ed25519 -C clawback-vultr -f ~/.ssh/clawback_deploy -N ""
cat ~/.ssh/clawback_deploy.pub
```

Devank: GitHub → `devank-yadav/clawback` → Settings → Deploy keys → **Add deploy key**, title `vultr`, paste the
`.pub` line, leave **Allow write access unchecked**.

```bash
# On the VM
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/clawback_deploy
  IdentitiesOnly yes
EOF
ssh -T git@github.com     # check the host key against GitHub's published SSH key fingerprints before typing yes;
                          # expect "Hi devank-yadav/clawback! You've successfully authenticated..."
git clone git@github.com:devank-yadav/clawback.git /opt/clawback
cd /opt/clawback && git log --oneline -1
```

**Option B: copy the tracked files from a laptop** (no GitHub setup; the VM gets no `.git`, so rollback is copying an
older checkout). Run from a clean checkout of `main`; only files git tracks are sent, so `.env`, `.venv`,
`node_modules` and `.next` never leave the laptop:

```bash
# On the laptop, repo root
git checkout main && git pull --ff-only && git status --short    # anything listed here would ship as is
make deploy-check
ssh root@<VM_IP> 'mkdir -p /opt/clawback'
git ls-files -z | rsync -az --from0 --files-from=- ./ root@<VM_IP>:/opt/clawback/
```

## 6. `.env` onto the VM

```bash
# On the laptop, repo root
scp .env root@<VM_IP>:/opt/clawback/.env
ssh root@<VM_IP> 'chmod 600 /opt/clawback/.env'
```

Then set the values that differ on the VM. Nothing below prints a secret:

```bash
# On the VM
cd /opt/clawback
setenv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
setenv DOMAIN clawback.biz                  # bare, no https://; Caddy gets the certificate for it
setenv PUBLIC_BASE_URL https://clawback.biz # exactly this: no www, no trailing slash (Twilio signature)
setenv DEMO_MODE false                      # step 0: the VM is the single live instance
setenv RECORD_FIXTURES 0                    # recordings inside a container never reach git
setenv NESSIE_POLL on                       # only matters with DEMO_MODE=false
setenv SMS_CHANNEL whatsapp
setenv CLAWBACK_ADMIN_TOKEN "$(openssl rand -hex 24)"  # locks POST /api/demo/reset; keep a copy for the presenter
mkdir -m 700 -p state                       # QuickBooks' saved refresh token lives here (step 0)
grep -E '^(DOMAIN|PUBLIC_BASE_URL|DEMO_MODE|RECORD_FIXTURES|NESSIE_POLL|SMS_CHANNEL)=' .env

# Which keys are filled, names only:
for k in ANTHROPIC_API_KEY GEMINI_API_KEY TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM OWNER_PHONE \
         CONTROLLER_PHONE NESSIE_API_KEY NESSIE_ACCOUNT_ID QBO_CLIENT_ID QBO_CLIENT_SECRET QBO_REALM_ID \
         QBO_REFRESH_TOKEN CLAWBACK_READONLY_TOKEN; do
  grep -qE "^$k=.+" .env && echo "set    $k" || echo "empty  $k"
done
```

- `TWILIO_AUTH_TOKEN` must be set on the VM: it turns on the webhook's signature check, which is all that stops anyone from posting fake replies.
- `CLAWBACK_READONLY_TOKEN` only if the Fetch.ai agent calls `/api/summary`.
- `DATABASE_URL` is not read by the running API yet (only `make seed`, which runs from a laptop: `scripts/` isn't in the image).
- Compose reads `.env` itself: if a value contains `$`, wrap it in single quotes so compose doesn't try to expand it.
- To serve `www` as well (step 3, item 3): `setenv DOMAIN '"clawback.biz www.clawback.biz"'`. Caddy then gets a certificate for both names; Twilio and `PUBLIC_BASE_URL` stay on the bare domain.

## 7. Start it

After step 3's `dig` shows `<VM_IP>`:

```bash
# On the VM
cd /opt/clawback
docker compose up -d --build        # first build takes a few minutes (npm ci + next build)
docker compose ps                   # api "(healthy)" after about 15 s; web and caddy "Up"
docker compose logs -f caddy        # wait for "certificate obtained successfully" for clawback.biz, then Ctrl-C
```

## 8. Verify

From a laptop, repo root:

```bash
bash deploy/smoke.sh https://clawback.biz      # every line PASS, ends with "smoke ok"
```

The same checks by hand:

```bash
curl -fsS https://clawback.biz/api/health                                 # {"ok":true,"demo_mode":...,"nessie_poller":...}
curl -s -o /dev/null -w '%{http_code}\n' https://clawback.biz/            # 200
curl -sI http://clawback.biz/ | head -3                                   # 308 to https://clawback.biz/
# The recorded run streams through Caddy one event at a time (about 67 lines over 20 s), then closes:
curl -sN "https://clawback.biz/api/runs/run-march-demo/events?keepalive=false&delay_ms=300" | cut -c1-100
```

A live run (press **Northmart pays** on `https://clawback.biz/` first; with `DEMO_MODE=false` this spends credits):

```bash
RID=$(curl -s https://clawback.biz/api/runs/latest | python3 -c 'import sys, json; print(json.load(sys.stdin)["run_id"])')
curl -sN "https://clawback.biz/api/runs/$RID/events" | cut -c1-120      # Ctrl-C to stop; ": keep-alive" lines are normal
```

Then by hand:

- [ ] Two phones on **cellular data** (not venue Wi-Fi) open `https://clawback.biz/`; a run fills the board; refresh mid-run keeps the state (F19).
- [ ] Owner beat: a WhatsApp reply from Dana's phone lands on the board (`docker compose logs caddy | grep webhooks` shows the POST with status 200), or the in-app fallback works.
- [ ] Controller beat: Sam's yes posts the credit memo (simulated in DEMO_MODE).
- [ ] `/portal` on the judge's tablet, once that screen is in `web/` (at `f55757a` the app has only `/` and `/board/<run>`).
- [ ] Scoreboard: `curl -s https://clawback.biz/api/eval/latest` says `not_run` on a fresh deploy, because `eval/latest*.json` are gitignored and kept out of the image. `curl -s -X POST https://clawback.biz/api/eval/run` fills it with the engine-mode score until the `api` container is recreated.
- [ ] Send Manasv the URL for `[LIVE URL]` in `docs/devpost.md`.

## 9. Twilio webhook

Owner and controller texts use the **Twilio WhatsApp Sandbox** (`SMS_CHANNEL=whatsapp`; US SMS is blocked by A2P
10DLC). Twilio Console → Messaging → Try it out → Send a WhatsApp message → **Sandbox settings** → "When a message
comes in": `https://clawback.biz/webhooks/twilio/sms`, method `POST` → Save.

- It must be exactly `PUBLIC_BASE_URL` + `/webhooks/twilio/sms`; any other spelling (www, `/api/webhooks/...`, a trailing slash) fails the signature check with 403.
- Each demo phone must have sent `join <code>` to the Sandbox number (lasts 3 days) and any message within the last 24 hours before it can be texted.
- Texts go out only with `DEMO_MODE=false` (step 0); replies are handled either way.
- Moving between the VM and a tunnel means changing this URL and `PUBLIC_BASE_URL` together.

## Update after a `git pull`

The `api` container keeps runs, questions, rules (Rule #1) and the audit chain in memory: recreating it wipes them.
Never redeploy the API between Dana's answer and the April replay; after a redeploy, run the March flow again.

```bash
# On the VM (Option A)
cd /opt/clawback
git fetch origin && git log --oneline HEAD..origin/main          # what's coming
git rev-parse HEAD > /root/clawback-prev                          # for rollback
docker tag clawback-api:latest clawback-api:prev; docker tag clawback-web:latest clawback-web:prev
git pull --ff-only origin main
docker compose up -d --build              # rebuilds what changed; recreates api only if its image or .env changed
docker compose restart caddy              # only if deploy/Caddyfile changed (see below)
bash deploy/smoke.sh https://clawback.biz # from a laptop
```

- Web-only change: `docker compose up -d --build web` rebuilds Next.js and leaves the API's state alone.
- `deploy/Caddyfile` change: `docker compose restart caddy`. The file is bind-mounted, and `git pull` replaces it with a new file, so `caddy reload` inside the container would still read the old one.
- `.env` change: `docker compose up -d --force-recreate api` (wipes the in-memory state).
- Option B: rerun step 5's `rsync` from the laptop, then the same `docker compose` commands.
- Reset between judge tables, from a laptop: `make reset API=https://clawback.biz/api CLAWBACK_ADMIN_TOKEN=<token>`. On the VM, `grep '^CLAWBACK_ADMIN_TOKEN=' .env` shows the token. Without it the reset answers 401, and so does the app's reset button on the live site: anyone with the URL could otherwise wipe the demo mid-pitch.

## Roll back

Fast, without a rebuild (images tagged `:prev` before the update):

```bash
cd /opt/clawback
docker tag clawback-api:prev clawback-api:latest && docker tag clawback-web:prev clawback-web:latest
docker compose up -d --no-build --force-recreate api web
```

Or to a known commit (Option A), with a rebuild:

```bash
cd /opt/clawback
git checkout "$(cat /root/clawback-prev)"     # detached HEAD on the last good commit
docker compose up -d --build
# back to main later: git checkout main && git pull --ff-only origin main && docker compose up -d --build
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| No certificate; the Caddy log shows challenge errors | `dig +short clawback.biz @1.1.1.1` shows only `<VM_IP>` (the old ALIAS and wildcard are gone); `curl -sI http://clawback.biz` from a laptop says `Server: Caddy`. Caddy retries by itself; after repeated failures Let's Encrypt limits retries for about an hour, and Caddy also tries ZeroSSL |
| `502` on `/api/...` | `docker compose ps` (api healthy?), `docker compose logs api --tail 50` |
| Board says "Can't reach the Clawback API" | `curl https://clawback.biz/api/health`; the web image bakes `NEXT_PUBLIC_API_BASE=/api` at build time |
| Phone replies don't land | `docker compose logs caddy \| grep webhooks`. 403: `PUBLIC_BASE_URL` and the Sandbox URL differ. 200 but nothing changes: the sender isn't `OWNER_PHONE` / `CONTROLLER_PHONE`, or nothing is waiting on them. No line at all: the Sandbox URL is wrong |
| Board stops updating mid-run | `deploy/smoke.sh`'s stream check; the API sends `: keep-alive` every few seconds and the browser reconnects with `Last-Event-ID` |
| QuickBooks writes fail an hour in (`DEMO_MODE=false`) | Step 0's token caveat: reset twice. `invalid_grant`: get a new refresh token from Intuit's OAuth Playground, put it in the VM's `.env`, delete `state/qbo.env`, `docker compose up -d --force-recreate api` |
| Disk filling up | `docker system df`; `docker image prune -f` removes old untagged builds |

## Fallback: laptop + tunnel (cut rule)

If Vultr can't be verified by **Sat noon**, run on the demo laptop with a tunnel and drop the Vultr track (log it in
`DECISIONS.md`). If DNS can't be pointed in time, the tunnel URL is the live URL and the GoDaddy track drops too.

Same compose file, plain HTTP behind the tunnel (the tunnel adds HTTPS). Docker Desktop must be running:

```bash
DOMAIN=:80 docker compose up -d --build
curl -fsS http://localhost/api/health
cloudflared tunnel --url http://localhost:80     # prints https://<random>.trycloudflare.com
```

Set `PUBLIC_BASE_URL=https://<random>.trycloudflare.com` in `.env`, run `docker compose up -d --force-recreate api`,
and put `https://<random>.trycloudflare.com/webhooks/twilio/sms` in the Twilio Sandbox settings. The quick-tunnel
URL changes every time `cloudflared` restarts, so repeat those two steps after a restart. Without Docker, `make dev`
runs the two apps on ports 3000 and 8000 and the tunnel can point at one of them only.

The demo laptop keeps `make demo` (DEMO_MODE) as the offline backup either way.

## After judging

Destroy the VM in the Vultr dashboard (stopped servers still bill). Remove the `vultr` deploy key on GitHub. Leave the
domain.

# Deploy runbook: Vultr VM + GoDaddy domain (F19)

Sat 4–8 PM, after the 4 PM checkpoint. Goal: judges' phones open the board at `https://<DOMAIN>`.
Tracks: MLH Vultr (hosting) and MLH GoDaddy (domain); the Devpost proof for both is the live URL.

Nothing here needs a key in the repo. Credentials for Vultr, GoDaddy and `.env` never go in the repo, chat or Slack.

## What is already in the repo

| File | Does |
| --- | --- |
| `docker-compose.yml` | Three services: `api` (FastAPI, port 8000 inside), `web` (Next.js, port 3000 inside), `caddy` (the only one with public ports, 80 and 443) |
| `api/Dockerfile` | Python 3.11 image with `api/`, `config/`, `data/`, `eval/` and `web/fixtures/`; one uvicorn worker, because runs and questions live in memory |
| `web/Dockerfile` | `npm ci`, `npm run build`, `npm start` on port 3000 |
| `deploy/Caddyfile` | `{$DOMAIN}` with automatic HTTPS. `/api/*` goes to the API with `/api` stripped, `/webhooks/*` goes to the API unchanged, everything else goes to the web app |
| `make deploy-check` | Offline check: route tests, `docker compose config`, and `caddy validate` when caddy or a Docker daemon is around |

**URL layout on the domain:**

- `https://<DOMAIN>/` and every screen (`/board/...`, `/portal`, `/inbox`, ...) come from Next.js.
- `https://<DOMAIN>/api/<path>` is the API's `/<path>`. So the health check is `https://<DOMAIN>/api/health` (the API route itself is `/health`, which settles the `/api` question from PR #24), and the event stream is `https://<DOMAIN>/api/runs/<id>/events`.
- `https://<DOMAIN>/webhooks/twilio/sms` is the Twilio webhook, not under `/api`, because the signature check rebuilds the URL as `PUBLIC_BASE_URL + /webhooks/twilio/sms`.

**For Rishi (web/):** the browser should call the API at `/api` on the same domain. `web/Dockerfile` sets `NEXT_PUBLIC_API_BASE=/api` at build time; in `npm run dev` the base is `http://localhost:8000`. URLs the API returns, such as `events_url: "/runs/<id>/events"`, need that base in front.

## Before the deploy: Manasv confirms

- [ ] Vultr account verified (yes or still pending), and how much MLH credit is on it.
- [ ] Access method: Devank added as a user on the Vultr account, or Manasv's login shared privately.
- [ ] The domain name registered on GoDaddy with the MLH code, and who can log in to its DNS settings.

If the Vultr account is not verified by **Sat noon**, skip to [Fallback](#fallback-laptop--tunnel-cut-rule).

## VM size and cost

Recommendation: **Cloud Compute, Regular Performance, 2 vCPU / 4 GB / 80 GB, $20.00 a month ($0.03 an hour)**, Ubuntu 24.04 LTS, location Silicon Valley (closest to Berkeley).

- Prices from [vultr.com/pricing](https://www.vultr.com/pricing/), checked 2026-10-24: Regular 1 vCPU / 2 GB is $10 ($0.015/h), 2 vCPU / 2 GB is $15 ($0.022/h), 2 vCPU / 4 GB is $20 ($0.03/h).
- Why 4 GB: the Next.js production build (`npm run build`) is the memory peak; 2 GB can run out of memory while building. The running app (uvicorn + Next.js + Caddy) fits in well under 2 GB.
- Cost for the weekend: about 48 hours × $0.03 = **about $1.50** of credit. Vultr bills a server until it is destroyed (a stopped server still bills), so destroy it after judging.
- Cheaper option if credit is tight: Regular 1 vCPU / 2 GB ($10) plus a 2 GB swap file (commands in step b).

Log the choice in `DECISIONS.md`, for example: `- 2026-10-24 16:30 · Vultr VM: Regular 2 vCPU / 4 GB, Silicon Valley, Ubuntu 24.04, $0.03/h · <name>`.

## Vultr: steps a–e

**a. Create the VM** (Vultr dashboard → Deploy → Cloud Compute → Regular Performance): pick the location, Ubuntu 24.04 LTS x64 and the plan above. Add your SSH public key under SSH Keys (or use the root password from the server page). Leave backups off. Write down the IPv4 address.

```bash
ssh root@<VM_IP>
```

**b. Install Docker** (on the VM):

```bash
curl -fsSL https://get.docker.com | sh
docker compose version

# Only if Ubuntu's firewall is on (ufw status says active): let web traffic in.
ufw status
ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp

# Only on the 2 GB plan: add swap so the Next.js build doesn't run out of memory.
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```

**c. Copy the repo** (from a laptop with the repo on latest `main`; the repo is private, so copy it rather than cloning on the VM):

```bash
git pull origin main
make deploy-check
rsync -az --delete --exclude .git --exclude .env --exclude 'web/node_modules' --exclude 'web/.next' \
  ./ root@<VM_IP>:/opt/clawback/
```

`docker-compose.yml`, `api/Dockerfile`, `web/Dockerfile` and `deploy/Caddyfile` are already in the repo; nothing to write here.

**d. Copy `.env`** (from the laptop), then set the two deploy values on the VM:

```bash
scp .env root@<VM_IP>:/opt/clawback/.env
ssh root@<VM_IP>
cd /opt/clawback
nano .env      # set DOMAIN=<DOMAIN> (bare, no https://) and PUBLIC_BASE_URL=https://<DOMAIN>
chmod 600 .env
```

The database stays on Tiger Data, so `DATABASE_URL` is the only database value. Keep `DEMO_MODE` as the team decided for the demo (`true` means no live AI or QuickBooks calls).

**e. Start it**, after the GoDaddy A record below points at the VM (Caddy needs DNS to get the certificate):

```bash
cd /opt/clawback
docker compose up -d --build
docker compose ps
docker compose logs -f caddy    # wait for "certificate obtained successfully", then Ctrl-C
curl -fsS https://<DOMAIN>/api/health
```

The health check answers `{"ok":true,"demo_mode":...}`.

**Later updates:** rerun the `rsync` from step c, then `docker compose up -d --build` on the VM. `make reset` only targets localhost; on the VM reset with `curl -X POST https://<DOMAIN>/api/demo/reset`. Restarting the `api` container also clears all runs, because state is in memory.

## GoDaddy DNS: steps a–e

**a. A record.** GoDaddy → My Products → the domain → DNS (DNS Records). Edit the existing `A` record for `@` (it usually says "Parked") so its value is `<VM_IP>`, TTL the lowest offered. Delete any other `A` or `AAAA` record for `@`, and turn off Domain Forwarding if it is on. A `www` CNAME can stay; only the bare domain gets a certificate unless you add `www.{$DOMAIN}` next to `{$DOMAIN}` on the first line of `deploy/Caddyfile`. Check from a laptop:

```bash
dig +short <DOMAIN> @8.8.8.8      # must print <VM_IP>; can take a few minutes
```

**b. HTTPS.** Nothing to set up: once DNS answers with the VM's IP, Caddy gets the certificate on `docker compose up` (Vultr step e). If the Caddy log shows certificate errors, check DNS first, then that ports 80 and 443 are open.

**c. PUBLIC_BASE_URL.** `PUBLIC_BASE_URL=https://<DOMAIN>` in `.env` on the VM, and on each laptop that should link to the live site. It is also what the Twilio signature check and the API's CORS list use.

**d. Twilio webhook.** Owner and controller texts go over the **Twilio WhatsApp Sandbox** now (PR #41, `SMS_CHANNEL=whatsapp`), because US SMS is blocked by A2P 10DLC (error 30034) and toll-free verification. So the webhook goes in the Sandbox settings, not in a phone number's Messaging settings: Twilio Console → Messaging → Try it out → Send a WhatsApp message → **Sandbox settings** → "When a message comes in" = `https://<DOMAIN>/webhooks/twilio/sms`, method `POST`, then Save. Each demo phone must have sent `join <code>` to the Sandbox number (the join lasts 3 days) and any message within 24 hours before it is texted. The in-app `/inbox` stays the fallback.

**e. Judges' phones (F19).** Open `https://<DOMAIN>/` on a phone on cellular data (not the venue Wi-Fi) and on a second phone. Then send Manasv the final URL so he can fill `[LIVE URL]` in `docs/devpost.md`.

## Verification checklist

- [ ] `make deploy-check` passes on the laptop before copying.
- [ ] `curl -fsS https://<DOMAIN>/api/health` answers `"ok":true` with a valid certificate (no `-k`).
- [ ] `http://<DOMAIN>/` redirects to `https://` (Caddy does this).
- [ ] `https://<DOMAIN>/` opens the payment screen; a run fills the board; refresh mid-run keeps the state.
- [ ] `curl -N https://<DOMAIN>/api/runs/<id>/events` streams events (no buffering).
- [ ] `/portal` opens on the judge's tablet.
- [ ] A WhatsApp reply from the owner phone reaches the board (or the `/inbox` fallback works).
- [ ] **F19:** two phones on cellular data open the board by URL.
- [ ] `DECISIONS.md` has the VM size line; Manasv has the live URL.

## Fallback: laptop + tunnel (cut rule)

Cut rule: if the Vultr account can't be verified by **Sat noon**, run on the demo laptop with a tunnel and drop the Vultr track (log it in `DECISIONS.md`). If GoDaddy DNS can't be pointed in time, the tunnel URL is the live URL and the GoDaddy track drops too.

The same compose file runs on the laptop, plain HTTP behind the tunnel (the tunnel provides HTTPS):

```bash
DOMAIN=:80 docker compose up -d --build
curl -fsS http://localhost/api/health
cloudflared tunnel --url http://localhost:80     # prints https://<random>.trycloudflare.com
```

Then set `PUBLIC_BASE_URL=https://<random>.trycloudflare.com` in `.env`, run `docker compose up -d` again so the API picks it up, and put `https://<random>.trycloudflare.com/webhooks/twilio/sms` in the Twilio Sandbox settings. The quick-tunnel URL changes every time `cloudflared` restarts, so repeat the last step after a restart. Without Docker, `make dev` runs the two apps on ports 3000 and 8000 and the tunnel can point at one of them only.

The demo laptop also keeps `make demo` (DEMO_MODE) as the offline backup either way.

## After judging

Destroy the VM in the Vultr dashboard (stopped servers still bill). Leave the domain.

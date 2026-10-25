#!/usr/bin/env bash
# Post-deploy smoke test (docs/deploy.md, step 8). Run from any laptop or the VM:
#   bash deploy/smoke.sh https://clawback.biz
# Read-only: it replays the recorded demo run, never starts a live run, sends no text and needs no keys.
# Exits non-zero if a check fails. API=<url> overrides the API base (default <site>/api), e.g. for a local API.
set -uo pipefail

SITE="${1:-https://clawback.biz}"
SITE="${SITE%/}"
API="${API:-$SITE/api}"
FIXTURE_RUN="run-march-demo"  # api/stubs/fixtures.py: the recorded fake run, always there, 67 events
fails=0

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }

# 1. API health through Caddy (/api is stripped, so this is the API's /health). Over https this also checks the cert.
if body=$(curl -fsS -m 10 "$API/health" 2>&1); then pass "health: $body"; else fail "GET $API/health: $body"; fi

# 2. The web app answers at the root.
code=$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$SITE/")
if [ "$code" = "200" ]; then pass "web: GET $SITE/ answered 200"; else fail "web: GET $SITE/ answered $code"; fi

# 3. Over https: plain http redirects to https, and the site speaks HTTP/2 (EventSource then shares one connection).
case "$SITE" in
https://*)
	host="${SITE#https://}"
	redirect=$(curl -s -m 10 -o /dev/null -w '%{http_code} %{redirect_url}' "http://$host/")
	case "$redirect" in
	30[18]" https://"*) pass "http redirects: $redirect" ;;
	*) fail "http://$host/ should redirect to https, got: $redirect" ;;
	esac
	version=$(curl -s -m 10 -o /dev/null --http2 -w '%{http_version}' "$SITE/")
	if [ "$version" = "2" ] || [ "$version" = "3" ]; then pass "HTTP/$version"; else warn "HTTP/$version (expected 2)"; fi
	;;
esac

# 4. The event stream: right content type, no compression, and events arrive one by one (not in a burst at the end).
stream="$API/runs/$FIXTURE_RUN/events?keepalive=false&delay_ms=150"
# With sign-in on (any password set, the deployed site), the stream answers 401 without a session: say so and skip.
status=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "${stream/delay_ms=150/delay_ms=0}")
if [ "$status" = "401" ]; then
	warn "stream: sign-in is on (401 without a session), so its content type and timing aren't checked from here"
else
	headers=$(curl -s -m 30 -D - -o /dev/null -H 'Accept-Encoding: gzip, zstd' "${stream/delay_ms=150/delay_ms=0}" | tr -d '\r')
	if printf '%s\n' "$headers" | grep -qi '^content-type: text/event-stream'; then pass "stream content type"; else fail "stream content type: $(printf '%s\n' "$headers" | head -1)"; fi
	if printf '%s\n' "$headers" | grep -qi '^content-encoding:'; then
		warn "stream is compressed ($(printf '%s\n' "$headers" | grep -i '^content-encoding:')); check deploy/Caddyfile"
	else
		pass "stream not compressed"
	fi
	timing=$(curl -sN -m 40 "$stream" | python3 -c '
import sys, time
t0, seen = time.monotonic(), []
for line in sys.stdin:
    if line.startswith("data:"):
        seen.append(time.monotonic() - t0)
print(len(seen), round(seen[0], 1) if seen else -1, round(seen[-1], 1) if seen else -1)
')
	read -r n first last <<<"$timing"
	if [ "${n:-0}" -ge 60 ] && python3 -c "import sys; f, l = float(sys.argv[1]), float(sys.argv[2]); sys.exit(0 if f < 3 and l - f > 5 else 1)" "$first" "$last"; then
		pass "stream: $n events, first after ${first}s, last after ${last}s (unbuffered)"
	else
		fail "stream: $n events, first after ${first}s, last after ${last}s (expected about 67, spread over about 10 s)"
	fi
fi

# 5. Twilio's webhook reaches the API unprefixed. An unsigned POST gets 403 while TWILIO_AUTH_TOKEN is set (good);
#    200 means the signature check is off. The From number is nobody's, so nothing changes either way.
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST -d 'From=%2B15550000000&Body=smoke' "$SITE/webhooks/twilio/sms")
case "$code" in
403) pass "webhook: unsigned POST refused (signature check on)" ;;
200) warn "webhook: reached the API, but the signature check is off (no TWILIO_AUTH_TOKEN in the VM's .env)" ;;
*) fail "webhook: POST $SITE/webhooks/twilio/sms answered $code" ;;
esac

# 6. Facts for the person deploying, not pass/fail.
printf 'INFO  latest live run: %s\n' "$(curl -s -m 10 "$API/runs/latest")"
printf 'INFO  eval score: %s\n' "$(curl -s -m 10 "$API/eval/latest")"

if [ "$fails" -eq 0 ]; then echo "smoke ok"; else echo "$fails check(s) failed"; fi
exit "$fails"

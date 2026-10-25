"""Send one SMS through Twilio to the admin (the owner), who gets the questions and the approvals.

Run: python scripts/send_sms.py owner "Test from Clawback"
     python scripts/send_sms.py owner "Approve credit memo of $2,730 (3 lines)?"
Keys (.env): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, OWNER_PHONE.
Trial accounts only text verified caller IDs.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 30
TO_KEYS = {"owner": "OWNER_PHONE"}


def require(*names):
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return [os.environ[n] for n in names]


def mask(phone):
    return f"...{phone[-4:]}" if len(phone) > 4 else "****"


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in TO_KEYS:
        sys.exit('Usage: python scripts/send_sms.py owner "message text"')
    who, text = sys.argv[1], sys.argv[2]
    load_dotenv(ROOT / ".env")
    sid, token, from_, to = require("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", TO_KEYS[who])

    client = Client(sid, token, http_client=TwilioHttpClient(timeout=TIMEOUT, max_retries=1))
    try:
        msg = client.messages.create(to=to, from_=from_, body=text)
    except TwilioRestException as e:
        sys.exit(f"Twilio error {e.code}: {e.msg}")
    print(f"Sent to {who} ({mask(to)}): sid={msg.sid} status={msg.status}")


if __name__ == "__main__":
    main()

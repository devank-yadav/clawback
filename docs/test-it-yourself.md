# Test it yourself: nothing is hardcoded

Hands-on checks anyone can run to see that Clawback's decisions follow the documents, the data and the owner's
answers, not a script. Each check says what to change, the exact commands, and what changes. The starting point is
the demo: **$4,120 disputed, $2,730 accepted, 1 question**. How each step works: [how-it-works.md](how-it-works.md).

## Before you start

- **Run it live.** Put your keys in `.env` (`ANTHROPIC_API_KEY`; `GEMINI_API_KEY` for the second reader) and
  start the API with `make api`. Clawback always runs live. An edited file changes what the AI is sent, so a
  saved answer could never match it anyway. A March run makes about 16 AI calls.
- **Read rows from the files.** Leave `DATABASE_URL` unset so the charges, sales and payments come from the CSV
  files you edit. With a database, run `make seed` after each edit.
- **Peak Bar's files** are under `data/accounts/peak-bar/`: `charges/<month>.csv`, `deals/`, `emails/`, `notices/`.
  (Until the multi-account change lands, the same files sit directly under `data/`, March's charges are
  `data/charges/northmart-march.csv`, and the button is `POST /payments/northmart`.)
- **Between checks:** `make reset` (clears runs, saved rules and the QuickBooks stand-in), and
  `git checkout -- data config` puts every file back.
- **No keys?** Each check names an offline test that does the same thing with a fake Claude:
  `.venv/bin/python -m pytest -q <test>`.

Paste these helpers into your shell (they need `curl` and `jq`):

```bash
API=http://localhost:8000
ACCOUNT=peak-bar
A=data/accounts/$ACCOUNT

pay()    { curl -s -X POST $API/payments/$ACCOUNT | jq -r .run_id; }        # "Northmart pays": starts a run
events() { curl -s "$API/runs/$1/events?keepalive=false" | sed -n 's/^data: //p'; }
settle() { until events $1 | jq -e 'select(.type=="run" and .data.status!="started")' >/dev/null; do sleep 2; done; }
board()  { events $1 | jq -sc '[.[] | select(.type=="decision") | .data] | group_by(.charge_id)
             | map(last | {charge_id, decision, disputed, accepted, gate_row, reason})[]'
           events $1 | jq -c 'select(.type=="totals") | .data | {taken, disputed, accepted, waiting, questions}' | tail -1
           events $1 | jq -c 'select(.type=="dispute" or .type=="approval") | {type, id: .data.id, total: (.data.total // .data.amount), status: .data.status}'; }
trace()  { curl -s "$API/runs/$1/trace${2:+?charge_id=$2}" | jq -c '.[] | {seq, agent, charge_id, status}'; }
answer() { curl -s -X POST $API/questions/$1/answer -H 'content-type: application/json' -d "{\"text\": \"$2\"}" \
             | jq -c '{rule: (.rule // {} | {label, condition, decision, else_decision, status})}'; }
question() { events $1 | jq -r 'select(.type=="question") | .data.id' | tail -1; }
```

Then the baseline, to compare against:

```bash
RUN=$(pay); settle $RUN; board $RUN
```

C1 Split ($600 disputed, $1,200 accepted), C2 Dispute $980, C3 Accept $330, C4 Dispute $1,540, C5 Dispute $1,000,
C6 Ask; taken $6,850, disputed $4,120, accepted $1,530, waiting $1,200, 1 question; D-0417 filed for $4,120.

## 1. Read a run's trace

What the AI was asked and what it answered, call by call.

```bash
trace $RUN                       # every call: both readers per document, then the Investigator and comebacks
trace $RUN C1                    # one charge: its Investigator and its comeback
curl -s "$API/runs/$RUN/trace?charge_id=C1" | jq '.[0].input.user | fromjson | .engine'   # what the Investigator was given
curl -s "$API/runs/$RUN/trace?charge_id=C1" | jq '.[0].output'                            # what it answered
curl -s $API/runs/$RUN/trace/summary | jq '{calls, input_tokens, output_tokens, ai_ms, wall_ms, cost_usd}'
```

**What to look for:** the Investigator's input already holds the engine's numbers (`allowed`, `taken`, `delta`,
its steps). Its output is a sentence, a type, evidence IDs and a confidence: no amount. `status` is `live` for a
call answered now, `recorded` for a saved answer, `failed` with its `error`; a live call's `usage` holds its
tokens, and the summary adds them up with the run's time and cost. Each reader's `output.terms` is what
it read, before the quote check. The readers' `input.user` holds the document itself.

A code check that sends an answer back shows as a second call for the same charge, with the reason at the end of
its input. In the recorded March run, C4's first comeback promised something "before Mar..." and the outbound
filter sent it back as a deadline the owner never set:
`curl -s "$API/runs/$RUN/trace?charge_id=C4" | jq -r '.[2].input.user' | sed -n '/Your previous answer/,$p'`.

Offline: `api/tests/test_trace.py`.

## 2. Change a charge's amount

Northmart charged week 1 at $1.50 a bar. Make it $1.25 (1,200 × $1.25 = $1,500):

```bash
sed -i 's/^C1,NM-2229,PA,Spring promo week 1,Original+Chocolate,1200,1.50,1800.00/C1,NM-2229,PA,Spring promo week 1,Original+Chocolate,1200,1.25,1500.00/' $A/charges/march.csv
make reset; RUN=$(pay); settle $RUN; board $RUN
```

**What changes:** C1 is now Split $300 disputed / $1,200 accepted (was $600 / $1,200). Taken drops to $6,550 and
D-0417 to $3,820. Nothing else moves. In `trace $RUN C1` the Investigator's input says `taken 1500.00`,
`delta 300.00`. Try any amount: the engine's `allowed` stays $1,200 (1,200 bars × the deal's $1.00), and the
disputed part is always the difference.

Offline: `api/engine/tests/test_allowed.py`.

## 3. Change the cap sentence in the deal

§3.2 caps the promotion at 5,000 bars. Raise it to 6,000:

```bash
sed -i 's/maximum of 5,000 units/maximum of 6,000 units/' $A/deals/spring-promo.md
make reset; RUN=$(pay); settle $RUN; board $RUN
curl -s $API/runs/$RUN/trace | jq -c '.[] | select(.agent | startswith("Deal reader")) | select(.input.doc_id=="spring-promo")
  | {agent, cap: [.output.terms[] | select(.type=="unit_cap") | .params.max_units]}'
```

**What changes:**

- **The readers:** both read `max_units: 6000`, quoting the new sentence word for word.
- **The engine:** weeks 1 to 3 used 5,000 bars, so 1,000 of week 4's 1,540 now fit under the cap.
- **The decision:** C4 is Split, $540 disputed and $1,000 accepted (was $1,540 disputed). D-0417 drops to $3,120.
  After the owner's answer the credit memo is $3,730. (The same $540 the portal concedes when the judge attaches
  the signed amendment.)

Variants: delete the §3.2 sentence and there is no cap, so C4 is Accept $1,540 (gate row 5) and D-0417 is $2,580.
If the two readers read the sentence differently, every charge that depends on it goes to the owner (gate
row 2): `docs/proof/gemini-vs-claude.md` has a real case.

## 4. Plant a fake quote

A term counts only if its sentence is in the document word for word, and every number in it is in that sentence.
Check it against the real deal:

```bash
.venv/bin/python - <<'EOF'
from api.engine.quote_check import check_quote
deal = open("data/accounts/peak-bar/deals/spring-promo.md").read()
def term(quote, cap): return {"type": "unit_cap", "params": {"max_units": cap}, "exact_quote": quote}
print(check_quote(deal, term("The promotional allowance applies to a maximum of 7,000 units in total.", 7000)))
print(check_quote(deal, term("The promotional allowance applies to a maximum of 5,000 units in total.", 7000)))
print(check_quote(deal, term("The promotional   allowance applies to a maximum of 5,000 units in total.", 5000)))
EOF
```

**What you see:** the invented sentence is rejected (`quote not found in source`); the real sentence with a
different number is rejected (`params numbers not in quote: 7000`); the real sentence with extra spaces passes,
with its position in the deal.

In a run, a charge that depends on a rejected term is skipped ("can't verify the deal", gate row 1), never
decided. Offline, a reader that plants a fake quote, and a scenario clause quoted wrong:

```bash
.venv/bin/python -m pytest -q api/engine/tests/test_quote_check.py api/tests/test_reader.py -k planted
.venv/bin/python -m pytest -q api/tests/test_coach_scenario.py -k quoted_wrong
.venv/bin/python -m pytest -q api/engine/tests/test_gate.py -k row_1
```

## 5. Send an email from a sender who isn't approved

The broker's email extends the promo through April 7, and that's why C3 ($330 for Apr 1 to 7) is fair. Make it
come from someone who isn't on the approved list:

```bash
sed -i 's/^From: Jordan Lee <jordan@peakbar-broker.example>/From: Jordan Lee <jordan@northmart.example>/' $A/emails/broker-2026-03-28.eml
make reset; RUN=$(pay); settle $RUN; board $RUN
events $RUN | jq -r 'select(.type=="log" and .data.actor=="reader") | .data.text'
```

**What changes:** the log says "jordan@northmart.example says: Northmart asked to extend Spring Promo through
April 7 ... That sender can't change the deal: shown as a claim, not applied." Both readers still read the
extension (the trace shows it), but the engine only uses terms from approved senders, so Apr 1 to 7 is outside
the deal. C3 becomes Dispute $330 (was Accept), D-0417 is $4,450, and accepted is $1,200 before the owner's
answer.

The same rule is why Northmart's own email ("the rate is $1.50", `northmart-2026-03-30.eml`) never changes C1.
Put Jordan's real address back, or add the new one to `approved_amendment_senders` in `config/policy.yaml`, and C3
is accepted again: the owner's policy decides who can change a deal, not the AI.

Offline: `api/tests/test_reader.py -k claim`.

## 6. Paste your own clause in the scenario box

Open `/scenario` on the site, or call it. Your clause replaces the matching part of the Spring deal for one
charge; the rest of the deal, the store sales and the saved rules still apply.

```bash
curl -s -X POST $API/scenario -H 'content-type: application/json' -d '{
  "clause": "The promotional allowance applies to a maximum of 5,500 units in total.",
  "charge": {"description": "Spring promo week 4", "amount": 1540.00, "units": 1540, "rate": 1.00,
             "period_start": "2026-03-22", "period_end": "2026-03-31"}}' \
  | jq '{message, decision: (.decision // {} | {decision, disputed, accepted, gate_row}), terms: [.terms[]? | {type, status, exact_quote}]}'
```

**What you see:** Split, $1,040 disputed and $500 accepted: weeks 1 to 3 already used 5,000 of the 5,500 bars.
Change the number and the answer follows: 7,000 → Accept, 4,000 → Dispute all $1,540. Other clauses to try:

- A rate: "Supplier will fund a promotional allowance of $0.80 per unit on Peak Bar Original and Peak Bar
  Chocolate sold between March 1 and March 31, 2026." with week 1 (`amount 1800`, `units 1200`, `rate 1.50`,
  `2026-03-01` to `2026-03-07`): allowed $960, Split $840 / $960.
- A fee at Northmart's discretion: "Northmart may charge a display fee of up to $900 per month at its discretion,
  with written notice to Supplier." with `{"description": "Display fee", "amount": 900, "code": "DF",
  "notice_date": "2026-03-25"}`: Ask (no rule yet), or Dispute $900 by Rule #1 once it's saved (6 days' notice is
  under 14).

A pasted clause has no saved answer, so it always runs live (up to 20 seconds a call). Offline:
`api/tests/test_coach_scenario.py`.

## 7. Run the eval

30 planted charges with an answer key written before the first run (`data/eval/`).

```bash
make eval
```

**What you see:** `30/30 correct · 6 asked · 0 wrong automatic actions`. The key is only used to score. Change a
planted case and the score drops. Make case E01 a $1.50 rate:

```bash
sed -i 's/^E01,EV-01,PA,Promo Original+Chocolate 2026-03-01 to 2026-03-07,Original+Chocolate,800,1.25,1000.00/E01,EV-01,PA,Promo Original+Chocolate 2026-03-01 to 2026-03-07,Original+Chocolate,800,1.50,1200.00/' data/eval/charges-30.csv
.venv/bin/python eval/run.py --no-save
```

`29/30 correct`, and the miss is named: `wrong_amount E01 ... amounts 400.00/800.00, key 200.00/800.00`. The
engine disputed what the edited data says; the old key no longer matches.

That's the engine and the gate on their own. With the readers and the agents in the loop:
`.venv/bin/python eval/run.py --mode agent --estimate` counts the AI calls (about 111), `make eval-agent` runs
them live, and `DEMO_MODE=true .venv/bin/python eval/run.py --mode agent` replays the recorded agent run for free.
To see whether a cheaper model would do for one agent, set it for that agent only and run the agents again:
`CLAWBACK_MODEL_INVESTIGATOR=claude-sonnet-5-5 make eval-agent` (`make eval-agent` also records the answers in
`data/fixtures/`).

## 8. Answer the owner's question differently

The owner's answer decides C6 and every later fee like it. Try each reply on a fresh run:

```bash
make reset; RUN=$(pay); settle $RUN
answer $(question $RUN) "accept if notice is at least 30 days"
board $RUN
APRIL=$(curl -s -X POST $API/replay/april | jq -r .run_id); settle $APRIL; board $APRIL
```

| Reply | Rule saved | March C6 (20 days' notice) | March totals | April (18 and 5 days' notice) |
| --- | --- | --- | --- | --- |
| "accept if notice is at least 14 days" (the demo) | `notice_days >= 14`: accept, else dispute | Accept $1,200 | $4,120 disputed, $2,730 accepted | A1 Accept $1,200, A2 Dispute $800, 0 questions |
| "accept if notice is at least 30 days" | `notice_days >= 30` | Dispute $1,200, filed as D-0418 | $5,320 disputed, $1,530 accepted | A1 and A2 Dispute ($2,000), 0 questions |
| "accept" | none: settles this charge only | Accept $1,200 | $4,120 disputed, $2,730 accepted | A1 and A2 Ask: 2 questions |
| "UNDO" (after a rule) | the rule is undone | keeps its decision | unchanged | A1 and A2 Ask again |

Plain code reads these replies (`api/replies.py`). A reply it can't read, such as "ok when the heads-up is a
fortnight or more", goes to Claude's rule writer: `trace $RUN C6` then shows a `Rule writer` entry with the reply
in its input and the condition it proposed in its output. Code builds the condition from that answer and checks
it before saving; if Claude doesn't understand the reply, the owner is asked again.

Offline: `api/tests/test_pipeline.py`, `api/tests/test_trace.py -k rule_writer`.

## One more: change the owner's policy

The limits are the owner's, set once in `config/policy.yaml`, and read on every run:

```bash
sed -i 's/^auto_dispute_limit_usd: 5000/auto_dispute_limit_usd: 4000/' config/policy.yaml
make reset; RUN=$(pay); settle $RUN; board $RUN
```

D-0417 ($4,120) is now over the limit, so it isn't filed: it's a draft held for the owner ("Dispute D-0417 is
$4,120, over the $4,000 limit: held for Dana."). Set `approval_over_usd: 3000` instead and, after the
owner's answer, the $2,730 credit memo posts on policy without asking.

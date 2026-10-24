# How Clawback works

For Devank and for judges. This follows one run from the short payment to QuickBooks. For each step it says who
does the work (**AI**, **code** or **a person**), which file does it, and which code checks every AI answer
before anything uses it. Every path is in this repo.

The short version: AI reads and writes words. Plain code computes every amount, decides with the owner's written
policy, and checks every AI answer. People approve money. To see the AI's part for yourself, read a run's
trace (the last section) or try the checks in [test-it-yourself.md](test-it-yourself.md).

## The run at a glance

| # | Step | Who | Where | What checks it |
| --- | --- | --- | --- | --- |
| 1 | The short payment arrives | code | `api/integrations/nessie.py`, `api/routes/payments.py` | — |
| 2 | Read the deal and the emails, twice | **AI** (Claude + Gemini) | `api/agents/reader.py`, `api/agents/reader_b.py` | quote found word for word, numbers in the quote, both readers agree, sender approved |
| 3 | Work out what the deal allows | code | `api/engine/allowed.py` | unit tests: `api/engine/tests/test_allowed.py` |
| 4 | Explain each charge | **AI** (Claude) | `api/agents/investigator.py` | every cited ID exists, no number the AI wasn't given |
| 5 | Predict Northmart's comeback | **AI** (Claude) | `api/agents/negotiator.py` (`rehearse`) | cited IDs exist, no new numbers, outbound filter |
| 6 | Decide each charge | code | `api/engine/gate.py` + `config/policy.yaml` | unit tests: `api/engine/tests/test_gate.py` |
| 7 | File the dispute, answer the portal | code + **AI** | `api/pipeline.py`, `api/disputes.py`, `api/agents/negotiator.py` | outbound filter on every message out |
| 8 | Ask the owner one question | code, then **a person** | `api/pipeline.py` (`_ask_owner`), `api/integrations/sms.py` | — |
| 9 | Turn the answer into a rule | code (AI only if code can't read it) | `api/replies.py`, `api/agents/rule_writer.py` | the condition must parse in `api/engine/rules.py` |
| 10 | Approve the credit memo | **a person** (the controller) | `api/pipeline.py` (`decide_approval`) | — |
| 11 | Write to QuickBooks | code | `api/integrations/qbo.py` | one write per approval id |
| 12 | Record every action | code | `api/audit.py`, `api/engine/audit_chain.py` | the hash chain (`GET /audit/verify`) |

The whole run is `api/pipeline.py`: `start` → `_guarded` → `_process` (steps 2 to 6) → `_after_decisions`
(steps 7, 8, 10). `answer` (steps 8 to 9) and `decide_approval` (steps 10 to 11) pick it up when people reply.
Every step streams to the board as an event (`GET /runs/{id}/events`).

## Rules every AI call follows

- **One way out.** Every outside call (Claude, Gemini, Moss, QuickBooks) goes through
  `api/integrations/replay.py` `call_outside`: a 30-second timeout (20 s for the scenario box and the portal),
  one retry, then a recorded answer if one exists. It also records the call in the run's trace.
- **Strict JSON.** `api/agents/claude.py` `ask` uses structured outputs, so Claude's answer must match a Pydantic
  schema. A refusal or a cut-off answer is a failed call. Gemini answers against the same schema
  (`reader_b.py`).
- **A code check after every answer.** Each agent passes `ask` a `check` function. If the check fails, the agent
  is asked once more with the problem appended ("Your previous answer failed validation: ..."). If it fails
  again, the charge goes to a person. The trace shows both tries.
- **Documents are data.** The prompts in `api/agents/prompts/` say so, but the real guard is code: only an
  approved sender or a document signed by both parties can change the deal (`api/documents.py`
  `can_change_deal`, senders listed in `config/policy.yaml`).

## Step by step

### 1. The short payment arrives (code)

Northmart's $41,350 deposit lands in the Capital One Nessie sandbox. `api/integrations/nessie.py` polls the
account every 5 seconds and starts a run for a new deposit (`pipeline.start_for_deposit`, once per deposit). The
"Northmart pays" button (`POST /payments/{account}`, `api/routes/payments.py`) posts the deposit, or starts the
run directly when there are no Nessie keys. The run loads the account's charges (`api/rows.py`: the
`charges/<month>.csv` file, or Postgres when `DATABASE_URL` is set) and says what was taken:
`api/engine/totals.py` `taken` adds the charge rows.

### 2. Reading the deal (AI, then code)

`api/agents/readers.py` `read_both` runs two readers side by side on each document: the signed deal
(`spring-promo`), the broker's email (`broker-2026-03-28`) and Northmart's email (`northmart-2026-03-30`).

- **Reader A** is Claude with `api/agents/prompts/reader.md`.
- **Reader B** is Gemini with `api/agents/prompts/reader_b.md` (`api/agents/reader_b.py`). If Gemini doesn't
  answer, a second Claude call with that prompt reads instead, and the run's log says so.

Each reader returns terms: a type (`promo_rate`, `product_scope`, `date_range`, `unit_cap`, `fee_discretion`,
`amendment`), its numbers (`params`), and the exact sentence it came from.

**Code checks each term** (`api/engine/quote_check.py`):

1. The quote must be found in the document word for word. Spaces, hyphens and curly quotes are normalized,
   nothing else. Not found → **rejected**.
2. Every number in `params` must appear in the quote. A cap of 7,000 read from a sentence that says 5,000 →
   **rejected**.
3. Both readers must find the same term with the same params (`readers.merge`, `quote_check.verify_term`). Only
   one found it, or they read it differently → **disputed**, and any charge that depends on it goes to a person
   (gate row 2).
4. Both agree and both quotes are found → **verified**.

Then `documents.can_change_deal` marks whether the term may change the deal. Northmart's email ("the rate is
$1.50") is read and verified like any other, but Northmart isn't an approved sender, so the engine never uses it.
The log shows it as a claim.

### 3. The math engine (code)

`api/engine/allowed.py` `compute_allowed` works out, for each charge, what the deal allows. It uses only
verified terms from approved sources, plus the store sales and prior payments from the data files. No AI is
involved; `api/engine/tests/test_allowed.py` reproduces every number in the demo.

- **Promo charges (code PA):** is the product covered (§3.1)? Walk the store sales week by week in date order
  and count promoted units against the cap (§3.2). Units after the deal's dates count only if an approved
  amendment (the broker's email) covers them, up to its extra units. Units a prior payment already paid
  (NM-2178) aren't owed again. Allowed = covered units × the deal's rate.
- **Fees (code DF):** allowed up to the stated maximum (§5.4). Days of notice = the fee period's end minus the
  notice date. Whether to accept a fee "at its discretion" is the gate's call, not the engine's.
- Delta = taken − allowed. Each step is written out as a sentence (`Allowance.steps`), and that is the math line
  on the evidence card.

### 4. The Investigator (AI, then code)

`api/agents/investigator.py` sends Claude (`prompts/investigator.md`) the charge, the engine's result
(`allowed`, `taken`, `delta`, steps, facts) and the evidence it may cite, each with an ID (`api/evidence.py`:
deal sentences, emails, notices, sales weeks, prior payments, charge rows). Claude returns a short sentence (the
prompt asks for 25 words or fewer), a type (`rate_over`, `duplicate`, `over_cap`, ...), the evidence IDs and its
confidence.

**Code checks:** at least one evidence ID; every ID is one it was given; no number in the sentence that isn't in
its input (`invented_numbers`). The Investigator never computes an amount: the trace shows the engine's numbers
in its input, and the check would reject a new one.

### 5. The comeback rehearsal (AI, then code)

For a charge the engine says is overcharged (and not a discretion fee), `negotiator.rehearse` asks Claude
(`prompts/rehearsal.md`) to predict Northmart's strongest comeback and write the answer.

**Code checks:** the answer cites at least one evidence ID it was given, adds no numbers, and passes the outbound
filter (`api/engine/outbound_filter.py`: every quote must be a verified term's sentence, every dollar figure an
engine or data number, and no promises, discounts or deadlines). No solid answer → the charge isn't filed
automatically; the gate sends it to a person.

### 6. The decision gate (code)

`api/engine/gate.py` `decide` applies the owner's policy (`config/policy.yaml`). The first row that matches wins:

| Row | When | Decision |
| --- | --- | --- |
| 1 | A term the charge depends on was rejected (quote not found) | Skip: "can't verify the deal" |
| 2 | The two readers disagree on that term | Ask the owner |
| 3 | The term leaves it to discretion ("may", "at its discretion", ...) and a saved rule covers it | Apply the rule |
| 4 | Discretion, and no rule covers it | Ask the owner |
| 5 | Taken is within $1 of allowed | Accept |
| 6 | Taken is less than allowed | Accept; never ask for more |
| 7 | Over by more than $1, up to $5,000, confidence ≥ 0.9, at least two kinds of evidence, comeback answered | Dispute (Split if part is allowed) |
| 8 | Same as 7, but over $5,000 | Ask the owner before filing |
| 9 | Anything else (including a required term missing) | Ask the owner |

Disputed and accepted amounts come straight from the engine's `allowed` and `delta`. For rows 3 and 4, a saved
rule covers the clause if Moss finds it by meaning (`api/integrations/moss.py`, similarity ≥ 0.85) with the
same clause type and counterparty (`api/engine/rules.py` `match_rule`), or else by an exact match on clause type
and counterparty (`find_rule`). Moss only names candidates; the gate checks them.

In the demo: C1 Split ($600 / $1,200), C2 Dispute $980, C3 Accept $330, C4 Dispute $1,540, C5 Dispute $1,000,
C6 Ask.

### 7. Disputes and the portal (code, and AI for replies)

`pipeline._file_dispute` puts every disputed line on one dispute (D-0417) with its clause quote, its math and its
evidence. If the total is within the $5,000 limit it's filed on the owner's policy; over it, the dispute waits for
the owner. D-0417 is $4,120.

Northmart (the judge) replies on the mock portal (`POST /portal/disputes/{id}/messages`, `api/disputes.py`):

- **A reply with a document attached** goes back through both readers (step 2). If the document can change the
  deal (signed by both parties, or from an approved sender), the engine recomputes and the gate decides again. The concession message ("we
  withdraw $1,000 of C4 and keep $540 disputed") is written by code from those numbers, not by AI.
- **A reply without a document** goes to Claude (`negotiator.answer_reply`, `prompts/portal_reply.md`), which
  classifies it and drafts an answer. **Code checks:** charge IDs on the dispute, evidence IDs it was given, no
  numbers that aren't ours (Northmart's own numbers don't count), and the outbound filter. Fails twice, or
  "other" → held for the owner.
- Every message out passes the outbound filter (`disputes._send`).

### 8. The owner's question (code, then a person)

A charge in Ask gets one question to the owner, never a second (`pipeline._ask_owner`). The text is built by code
from the clause and the facts ("Notice came 20 days ahead"). It goes by SMS when Twilio is set up, else it waits
in the inbox (`api/integrations/sms.py`, `GET /inbox`). The owner answers by text (`POST /webhooks/twilio/sms`) or
in the app (`POST /questions/{id}/answer`).

### 9. The answer becomes a rule (code first, AI only if needed)

`pipeline.answer` passes the reply to `api/replies.py` `parse_owner_reply` first. Plain code reads "accept if
notice is at least 14 days" (or "two weeks") as `notice_days >= 14 → accept, else dispute`. "ACCEPT" or "DISPUTE"
alone settles that one charge with no rule. "UNDO" cancels the newest rule.

Only a reply code can't read goes to Claude's rule writer (`api/agents/rule_writer.py`). **Code checks:** Claude
proposes a fact, an operator and a value; code builds the condition and it must parse in
`api/engine/rules.py`. Not understood → the owner is asked again.

The rule is saved (Rule #1), indexed in Moss, echoed back by text with an UNDO option, and every waiting charge is
decided again (step 6, row 3). C6 had 20 days' notice, so Rule #1 accepts it. In April the same rule decides both
fees with no question: 18 days' notice → accept $1,200, 5 days → dispute $800.

### 10. The controller's approval (a person)

When nothing is waiting on the owner, `pipeline._request_credit_memo` proposes one credit memo for every accepted
amount ($2,730, 3 lines). Over $1,000 it needs the controller, never the owner or an agent
(`gate.needs_controller`). Sam answers YES or NO by text, or in the app (`POST /approvals/{id}`). NO posts nothing
and the note shows on the card.

### 11. QuickBooks (code)

`pipeline._post_books` and `api/integrations/qbo.py` write the credit memo, apply it to INV-3102, and note the
disputed $4,120 on the invoice. Request ids come from the approval id, so a retry never posts twice. Without the
QuickBooks keys a stand-in answers with "sim-" ids and every ledger post says it was simulated.

### 12. The audit chain (code)

Every decision, question, answer, rule, approval, ledger post, dispute and portal message is appended to a hash
chain the moment it happens (`api/audit.py`, `api/engine/audit_chain.py`). Each row's hash covers the row and the
one before it, so editing, removing or reordering any past row breaks the chain. `GET /audit/verify` checks it.

## Where every number on screen comes from

| On screen | Comes from | Computed by |
| --- | --- | --- |
| Expected $48,200, received $41,350 | The invoice and the Nessie deposit | `api/pipeline.py` (the deposit's amount when Nessie sent one) |
| Taken $6,850 | The charge rows (`charges/<month>.csv`) | `engine/totals.py` `taken` |
| Disputing / accepted / waiting meters | The `totals` event | `engine/totals.py` `meters`, over the gate's decisions |
| A card's disputed and accepted amounts | The `decision` event | `engine/gate.py`, from the engine's allowed and delta |
| The math line ("1,200 units × $1.00 = $1,200") | `Allowance.steps`, each part linked to its evidence | `engine/allowed.py`, `api/evidence.py` `math_parts` |
| The highlighted deal sentence | The verified term's quote and its position in the document | `engine/quote_check.py` `find_quote` |
| Days of notice | The notice date and the fee period | `engine/allowed.py` `notice_days` |
| Dispute total ($4,120) | The disputed lines | `engine/totals.py` `total_of` |
| Credit memo ($2,730) | The accepted amounts | `engine/totals.py` `total_of` |
| The $1,000 concession, $540 kept | The engine recomputed with the amendment | `engine/gate.py` `concession` |
| Deal Coach "this clause cost $X" | The disputed or questioned amounts the redline cites | `agents/coach.py` check, `total_of` |
| Moss similarity (0.85+) | Moss's score for the clause | Moss; the gate checks it |
| Investigator confidence | **The Investigator's own estimate** | AI; used only to send a charge below 0.9 to a person, never as an amount |
| Eval score (30/30) | The 30 planted cases against `data/eval/answer-key.csv` | `eval/run.py` |
| Questions asked | The run's questions | `api/pipeline.py` |

The words on a card come from AI: the finding sentence, the comeback and its answer, portal replies, redlines and
the rule's summary. Every number inside them was checked against the numbers the AI was given.

## Seeing it for yourself: the trace

Every AI call a run makes is recorded (`api/trace.py`) and served at `GET /runs/{run_id}/trace`; add
`?charge_id=C1` for one charge. The "How Clawback decided" panel reads it. Each entry is one call:

| Field | Meaning |
| --- | --- |
| `seq`, `at` | Order (as calls finish) and start time |
| `agent` | Deal reader (Claude), Deal reader (Gemini), Deal reader (second Claude read), Investigator, Negotiator: comeback, Negotiator: portal reply, Deal Coach, Rule writer, Rule memory (Moss), QuickBooks |
| `charge_id`, `model`, `prompt` | The charge, the model (the one that answered a live call), the prompt file and its first line |
| `input` | The request exactly as sent: the system prompt and the user content (for the Investigator, a JSON payload holding the engine's numbers) |
| `output` | The parsed answer, before the code check |
| `status` | `live` (answered now), `recorded` (a saved answer replayed) or `failed` |
| `attempts`, `error`, `latency_ms` | Tries, what went wrong, how long it took |
| `usage` | A live call's tokens (`input_tokens`, `output_tokens`, cache tokens; Gemini's thinking tokens); none for a recorded answer |

`GET /runs/{run_id}/trace/summary` adds it up: calls by agent and model, tokens, the AI calls' time, the run's
wall time from its first event to the decided board, and the cost of the live calls at the prices in
`config/pricing.yaml` (copied from the providers' pricing pages, with the links; a model with no price there shows
its tokens and no cost). Each Claude agent can run on another model for a test, set by `CLAWBACK_MODEL_<AGENT>`
(`READER`, `INVESTIGATOR`, `REHEARSAL`, `PORTAL_REPLY`, `COACH`, `RULE_WRITER`); unset, every agent uses Claude
Opus 5.5.

A first March run makes 16 calls, more if one is retried: both readers on each of the 3 documents, then for each
charge the Investigator, and the comeback for the 4 charges the engine says are overcharged. Answering the owner's question adds the rule
writer only if code couldn't read the answer, and Moss when it's set up. Approving the memo adds the QuickBooks
calls. Keys never appear: any value of a secret setting is replaced by `[redacted]`.

The trace is in memory: the newest 100 runs, gone after a restart. Until the pipeline enters the run context
(`api/trace.py` says where), a run's trace is empty.

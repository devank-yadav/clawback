# Two models read the deal: a real disagreement (MLH Gemini proof)

Every deal is read twice, by Claude (Reader A, `claude-opus-5-5`) and Gemini (Reader B). A term is used only when both
readers return the same term and its quote is found word for word in the document. If they read a term differently,
the term is marked disputed and every charge that depends on it goes to the owner as a question (decision gate row 2).

Recorded live on Oct 24, 2026 on the two "vague wording" cases of our 30-case eval. Reader B was
`gemini-3.5-flash-lite`; our first-choice Gemini model didn't answer these two calls, so the fallback in the chain
read them.

## E29: the readers disagree, so Clawback asks

Deal clause (§3.1):

> Supplier will fund a promotional allowance of $1.00 per unit on its core bars sold in March 2026.

Charge: Peak Bar Chocolate, 1,200 bars × $1.00 = $1,200, Mar 8–14.

| Term | Claude (Reader A) | Gemini (Reader B) |
| --- | --- | --- |
| Rate | $1.00 per unit | $1.00 per unit |
| Dates | Mar 1–31, 2026 | Mar 1–31, 2026 |
| Products | Left out as unclear: "Product scope in 3.1 is given only as 'its core bars' without naming specific products" | `["core bars"]` |

Result: the product term is **disputed** ("product_scope: Reader A read nothing; Reader B read products ['core
bars']"). Gate row 2 applies: "The two deal readers disagree on a term this charge depends on." Clawback **asks the
owner** whether Chocolate counts as a core bar, instead of accepting or disputing the $1,200 on its own. That matches
the answer key.

## E28: the readers agree the clause is too vague

> Supplier will support promotional activity at a reasonable per-unit rate during the spring period.

Neither model invents a rate. Claude: "3.1 refers to a 'reasonable per-unit rate' but states no amount". Gemini: "Section 3.1 mentions a reasonable per-unit rate and spring period without specifying exact numerical rate
values or dates". Both return only the 5,000-unit cap. With no rate, products or dates in the deal, the gate asks
the owner (row 9: "Deal is missing: promo_rate, product_scope, date_range").

## Where this sits in the score

The agent-mode eval (readers and agents in the loop, all 30 planted cases) scores **30/30 correct, 6 asked, 0 wrong
automatic actions**. It replays offline with these two Gemini readings included.

On the demo's own documents (the spring deal, both emails and the signed amendment), Gemini and Claude agree on
every term (DECISIONS.md, Oct 24 03:59).

## Reproduce

Offline, from the recordings:

```bash
DEMO_MODE=true python eval/run.py --mode agent --cases E28,E29
```

The recordings themselves:
- `data/fixtures/gemini-reader/807477f04c9f6195.json` (E29) and `2a61123f578744c3.json` (E28);
- `data/fixtures/claude-reader/dacd07987b24da7b.json` (E29) and `5cdd46c085381d18.json` (E28).

Live again (6 AI calls): `RECORD_FIXTURES=1 python eval/run.py --mode agent --cases E28,E29` with `GEMINI_API_KEY` and
`ANTHROPIC_API_KEY` set.

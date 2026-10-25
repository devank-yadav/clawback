// The public landing page (/), in billow's design language: one claim, the product doing it, the problem in public
// court records, how it works in four steps, why it can be trusted, and a request-access form. Facts about the cases
// come from the cited filings and trade press; the hero's explainer shows one payment with the demo's own figures.

import Link from "next/link";
import { ArrowRight, BadgeCheck, Calculator, FileCheck2, Landmark, MessageSquareReply, Scale, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/console/ui";
import RequestAccess from "./RequestAccess";
import { HeroExplainer } from "./HeroExplainer";

const STEPS = [
  {
    icon: <Landmark />,
    title: "A payment arrives",
    body: "Your bank, QuickBooks or the remittance email shows a payment that came in short. Clawback lists every deduction taken out of it.",
  },
  {
    icon: <Scale />,
    title: "Agents check every charge against your contract",
    body: "Two AI readers must agree on each term, quoted word for word. Tested code does the math: the rate, the dates, the caps, the repeats.",
  },
  {
    icon: <FileCheck2 />,
    title: "Disputes go out with proof, after your OK",
    body: "Each wrong charge is disputed with the clause, the sales rows and the math. Fair ones are accepted. When the contract leaves it to judgment, you’re asked once.",
  },
  {
    icon: <MessageSquareReply />,
    title: "Replies are handled, and you’re kept up to date",
    body: "Clawback answers the distributor’s replies, concedes when shown a signed change, and tells you what moved. Credit memos over $1,000 wait for your approval.",
  },
];

const TRUST = [
  {
    icon: <BadgeCheck />,
    title: "Your real contracts",
    body: "Every decision cites the sentence it rests on. Signed contracts are locked: only a document signed by both sides, or a sender you approved, changes a term.",
  },
  {
    icon: <Calculator />,
    title: "Tested math, not AI math",
    body: "AI reads and writes. Every amount comes from code with unit tests, scored against an answer key written before the agents ran.",
  },
  {
    icon: <ShieldCheck />,
    title: "You approve the large credit memos",
    body: "No AI agent moves money or posts to QuickBooks. Credit memos over $1,000 wait for your approval, and every action lands in an audit log that shows any edit.",
  },
];

/** Sources for two supplier suits against UNFI. The figures on the page are as reported (Omaha's own numbers; the
 * 82% is Omaha's). Allegations, not findings: both cases are open. The NYSM timeline is a schematic, with no dates. */
type Source = { label: string; href: string };
const NYSM_SOURCES: Source[] = [
  { label: "Grocery Dive", href: "https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/" },
  { label: "New Hope", href: "https://www.newhope.com/industry-news/massachusetts-organic-food-supplier-accuses-unfi-deceptive-practices-breach-of-contract" },
  { label: "UNFI 10-Q, Nov 2025", href: "https://www.sec.gov/Archives/edgar/data/1020859/000102085925000065/unfi-20251101.htm" },
];
const OMAHA_SOURCES: Source[] = [
  { label: "Grocery Dive", href: "https://www.grocerydive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/705044/" },
  { label: "Supply Chain Dive", href: "https://www.supplychaindive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/704810" },
];

function Sources({ list }: { list: Source[] }) {
  return <p className="st-sources">Sources: {list.map((s, i) => <span key={s.href}>{i > 0 && " · "}<a href={s.href} target="_blank" rel="noreferrer">{s.label}</a></span>)}</p>;
}

function TopNav() {
  return (
    <header className="st-top">
      <Link href="/" className="st-logo" aria-label="Clawback home"><Logo /> clawback</Link>
      <nav className="st-top-links" aria-label="Page">
        <a href="#problem">The problem</a>
        <a href="#how">How it works</a>
        <a href="#trust">Trust</a>
      </nav>
      <div className="st-top-right">
        <a href="#access" className="st-btn is-ghost">Request access</a>
        <Link href="/signin" className="st-btn is-dark">Sign in</Link>
      </div>
    </header>
  );
}

export default function Landing() {
  return (
    <div className="st-page">
      <TopNav />
      <main>
        <section className="st-hero">
          <h1 className="display">Get paid what the contract says.</h1>
          <p className="st-sub">Clawback checks every deduction your distributors take against the contract you signed, disputes the wrong ones with proof, and accepts the fair ones.</p>
          <div className="st-actions">
            <Link href="/signin" className="st-btn is-blue is-glow">Sign in <ArrowRight aria-hidden="true" /></Link>
            <a href="#access" className="st-textlink">Request access <ArrowRight aria-hidden="true" /></a>
          </div>
          <HeroExplainer />
        </section>

        <section id="problem" className="st-section">
          <div className="st-head is-center">
            <h2 className="display">Distributors take money <br />out of every payment</h2>
            <p>Small brands rarely have the hours to check each deduction.<br />Two suppliers took theirs to court.</p>
          </div>
          <div className="st-cases">
            <article className="st-case">
              <div className="st-vig" aria-hidden="true">
                <div className="st-vig-sheet">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div key={i} className={`st-vig-row ${i === 2 ? "is-hot" : ""}`}><i /><i /><i /><i /></div>
                  ))}
                </div>
                <span className="st-vig-chip is-red">$268,816.94 charged back</span>
                <div className="st-vig-bar"><span style={{ width: "82%" }} /></div>
                <span className="st-vig-cap">About 82% of $326,780 in sales</span>
              </div>
              <div className="st-case-body">
                <h3 className="display">Chargebacks on most of the sale</h3>
                <p>Omaha Industries says UNFI charged back $268,816.94 on more than $326,780 of pet food it sold to Giant Food, citing broad language in the supply agreement.</p>
                <p className="st-case-when">Omaha Industries v. United Natural Foods · filed January 2024</p>
                <Sources list={OMAHA_SOURCES} />
              </div>
            </article>
            <article className="st-case">
              <div className="st-vig" aria-hidden="true">
                <div className="st-vig-sheet is-invoice">
                  <div className="st-vig-row is-head"><i /><i /></div>
                  <div className="st-vig-tl">
                    <span className="st-vig-window" />
                    <b className="is-start" style={{ left: "0%" }} />
                    <b style={{ left: "40%" }} />
                    <b className="is-paid" style={{ left: "82%" }} />
                  </div>
                  <div className="st-vig-tl-labels"><span>Invoice</span><span>Window closes</span><span className="is-paid">Paid</span></div>
                  <div className="st-vig-row"><i /><i /><i /></div>
                </div>
                <span className="st-vig-chip is-amber">Discount taken after the window</span>
              </div>
              <div className="st-case-body">
                <h3 className="display">Paid late, discount kept</h3>
                <p>A natural-foods supplier says UNFI takes prompt-pay discounts on invoices it pays after the window, among “opaque and constant deductions”. The case is pending.</p>
                <p className="st-case-when">NYSM Organics v. United Natural Foods · filed Nov 3, 2024</p>
                <Sources list={NYSM_SOURCES} />
              </div>
            </article>
          </div>
          <p className="st-fine">Allegations as reported in public filings and the trade press; neither case has been decided.</p>
        </section>

        <section id="how" className="st-section">
          <div className="st-head">
            <h2>How it works.<span>Four steps, and you only step in where the contract leaves it to you.</span></h2>
          </div>
          <ol className="st-steps">
            {STEPS.map((s, i) => (
              <li key={s.title} className="st-step">
                <span className="st-step-n">{i + 1}</span>
                <span className="st-icon" aria-hidden="true">{s.icon}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="trust" className="st-section">
          <div className="st-head">
            <h2>Built to be trusted with money.<span>The contract decides. Code counts. You approve.</span></h2>
          </div>
          <div className="st-trust">
            {TRUST.map((t) => (
              <article key={t.title} className="st-card">
                <span className="st-icon" aria-hidden="true">{t.icon}</span>
                <h3>{t.title}</h3>
                <p>{t.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="access" className="st-section st-access">
          <div className="st-head">
            <h2>Request access.<span>We’re bringing on a few brands at a time.</span></h2>
          </div>
          <RequestAccess />
        </section>
      </main>
      <footer className="st-foot">
        <span className="st-logo is-small"><Logo size={18} /> clawback</span>
        <span>Get paid what the contract says.</span>
        <Link href="/signin">Sign in</Link>
      </footer>
    </div>
  );
}

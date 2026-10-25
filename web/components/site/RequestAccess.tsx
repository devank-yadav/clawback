"use client";

// The request-access form on the landing page. Not live yet: nothing is sent or stored anywhere; submitting it only
// thanks the visitor. Wire it to a real endpoint before collecting anyone's details.

import { useState } from "react";
import { Check } from "lucide-react";

export default function RequestAccess() {
  const [sent, setSent] = useState(false);
  if (sent) {
    return (
      <div className="st-form-card st-thanks" role="status">
        <span className="st-icon" aria-hidden="true"><Check /></span>
        <h3>Thanks. We’ll be in touch.</h3>
      </div>
    );
  }
  return (
    <form className="st-form-card st-form" onSubmit={(event) => { event.preventDefault(); setSent(true); }}>
      <div className="st-form-grid">
        <div>
          <label htmlFor="ra-name">Your name</label>
          <input id="ra-name" name="name" autoComplete="name" required />
        </div>
        <div>
          <label htmlFor="ra-email">Work email</label>
          <input id="ra-email" name="email" type="email" autoComplete="email" required />
        </div>
        <div>
          <label htmlFor="ra-company">Brand</label>
          <input id="ra-company" name="company" autoComplete="organization" required />
        </div>
        <div>
          <label htmlFor="ra-distributors">Distributors you sell through <span>(optional)</span></label>
          <input id="ra-distributors" name="distributors" placeholder="UNFI, KeHE, Walmart…" />
        </div>
      </div>
      <button className="st-btn is-dark" type="submit">Request access</button>
    </form>
  );
}

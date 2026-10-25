"use client";

// The admin's sign-in page (/signin): the top bar's "Sign in" opens it, and it returns to the page you came from.
// The same form also opens in place when an action needs the admin (SessionDialogs).

import { useRouter, useSearchParams } from "next/navigation";
import TopBar from "@/components/shell/TopBar";
import { SignInForm, roleName } from "@/components/shell/SessionDialogs";
import { useRun } from "@/components/console/RunProvider";
import { HeroPill, PageHero } from "@/components/ui/kit";
import { signOut, useSession } from "@/lib/session";
import { withAccount } from "@/lib/accounts";

export default function SignInPage() {
  const { account } = useRun();
  const { role } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const back = next && next.startsWith("/") && !next.startsWith("//") ? next : withAccount("/", account?.id);
  const name = roleName("owner", account);

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main signin-page">
        <PageHero
          pill={<HeroPill>{account ? `${account.brand.name} · admin` : "Clawback · admin"}</HeroPill>}
          title={<>Sign in as <em>{name}.</em></>}
          sub="The admin answers the questions your agents can’t settle from the deal, and approves what posts to QuickBooks. Nothing else needs a sign-in."
        />
        <section className="signin-card" aria-label="Sign in">
          {role ? (
            <div className="signin-done">
              <strong>You’re signed in as {name}.</strong>
              <div className="signin-actions">
                <button className="cx-btn" onClick={() => router.push(back)}>Continue</button>
                <button className="cx-btn is-ghost" onClick={signOut}>Sign out</button>
              </div>
            </div>
          ) : (
            <SignInForm role="owner" onDone={() => router.push(back)} />
          )}
        </section>
      </main>
    </div>
  );
}

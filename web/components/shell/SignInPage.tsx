"use client";

// /signin: an email and password in, the API's session cookie back (POST /auth/login), then on to where you were
// going (?next=, else /app). Every signed-out visit to the app and every action that needs a sign-in comes here.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { BrandMark } from "@/components/console/ui";
import { ApiError } from "@/lib/api";
import { signIn, signOut, useSession } from "@/lib/session";
import { safeNext } from "@/lib/signin-route";

const WHY: Record<string, string> = {
  expired: "Your session ended. Sign in again to carry on.",
  needed: "Sign in to carry on.",
};

/** The words for a failed sign-in: wrong details, too many tries, or a server without sign-in set up. */
function problemFor(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return "That email or username and password don’t match.";
    if (e.status === 429) return "Too many tries. Wait a few minutes, then try again.";
    if (e.status === 503) return "Sign-in isn’t set up on this server yet.";
    if (e.detail) return e.detail;
  }
  return `Couldn’t reach Clawback (${(e as Error).message}). Try again in a moment.`;
}

export default function SignInPage() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const why = WHY[params.get("why") ?? ""] ?? null;
  const { status, user } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit() {
    if (!email.trim() || !password) {
      setProblem("Enter your email or username, and your password.");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await signIn(email.trim(), password);
      router.replace(next);
    } catch (e) {
      setProblem(problemFor(e));
      setBusy(false);
    }
  }

  return (
    <div className="st-auth">
      <header className="st-auth-top">
        <Link href="/" className="st-logo" aria-label="Clawback home"><BrandMark size="lg" /></Link>
      </header>
      <main className="st-auth-main">
        <section className="st-auth-card" aria-labelledby="signin-title">
          <h1 id="signin-title" className="display">Sign in</h1>
          {status === "in" ? (
            <div className="st-auth-done">
              <p>You’re signed in as <strong>{user?.name}</strong> ({user?.email}).</p>
              <button className="st-btn is-dark is-wide" onClick={() => router.replace(next)}>Continue</button>
              <button className="st-btn is-ghost is-wide" onClick={() => void signOut()}>Sign out</button>
            </div>
          ) : (
            <form className="st-form" onSubmit={(event) => { event.preventDefault(); void submit(); }} noValidate>
              <p className="st-auth-sub">See what your distributors took, and what your agents did about it.</p>
              {(problem ?? why) && <p className={problem ? "st-alert" : "st-note"} role={problem ? "alert" : "status"}>{problem ?? why}</p>}
              <label htmlFor="signin-email">Email or username</label>
              <input id="signin-email" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus value={email}
                onChange={(event) => { setEmail(event.target.value); setProblem(null); }} />
              <label htmlFor="signin-password">Password</label>
              <input id="signin-password" type="password" autoComplete="current-password" value={password}
                onChange={(event) => { setPassword(event.target.value); setProblem(null); }} />
              <button className="st-btn is-dark is-wide" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          )}
        </section>
        <p className="st-auth-foot">New to Clawback? <Link href="/#access">Request access</Link></p>
      </main>
    </div>
  );
}

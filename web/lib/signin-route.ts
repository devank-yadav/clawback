// Where a signed-out visitor goes: /signin, and back to the page they were on once signed in. No imports, so the API
// client (a 401 on any data route) and the session store can both use it.

/** The sign-in page's address for coming back to `next` (this page when omitted). */
export function signInHref(next?: string, why?: "expired" | "needed"): string {
  const here = next ?? (typeof window === "undefined" ? "/app" : `${window.location.pathname}${window.location.search}`);
  const params = new URLSearchParams({ next: here });
  if (why) params.set("why", why);
  return `/signin?${params}`;
}

/** Off to /signin, unless this page is the sign-in page or the landing page (both public). */
export function goSignIn(why: "expired" | "needed" = "needed") {
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  if (path === "/signin" || path === "/") return;
  window.location.assign(signInHref(undefined, why));
}

/** A `next` that stays on this site (no //host or full URLs), else the app's start. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && next !== "/signin" ? next : "/app";
}

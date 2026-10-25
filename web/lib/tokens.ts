// The presenter's admin token, kept in sessionStorage (gone when the tab closes). The sign-in itself is the API's HttpOnly
// session cookie, which this code never sees; the admin token (CLAWBACK_ADMIN_TOKEN) is sent as Authorization: Bearer
// on the demo reset and on the calls the site limits per visitor.
// No imports, so both the API client and the session store can use it.

const ADMIN_KEY = "clawback-admin-token";
let adminMemory: string | null = null;

export function adminToken(): string | null {
  try {
    return window.sessionStorage.getItem(ADMIN_KEY) ?? adminMemory;
  } catch {
    return adminMemory;
  }
}

export function setAdminToken(token: string | null) {
  adminMemory = token;
  try {
    if (token) window.sessionStorage.setItem(ADMIN_KEY, token);
    else window.sessionStorage.removeItem(ADMIN_KEY);
  } catch {
    /* kept in memory only */
  }
}

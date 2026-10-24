// The two secrets this browser tab may hold, kept in sessionStorage (gone when the tab closes):
// the signed-in role's access code (sent as X-Clawback-Role-Token) and the presenter's admin token
// (sent as Authorization: Bearer on resets and on the calls the site limits per visitor).
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

/** What the server sends before the account (from the URL) is known: the frame, no data. */
export default function ShellFallback() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-hidden />
      <div className="main-shell">
        <header className="topbar" />
        <main className="main-content"><p className="muted" role="status">Loading…</p></main>
      </div>
    </div>
  );
}

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // `/` is the public landing page; the app lives under /app. Every older address (the agents' flow at /?account=,
  // the list pages, the tools, the console pages, the workspace's /?view= links) keeps working: the query string
  // carries over, so emails, texts and portal links sent before the move still open the right screen.
  async redirects() {
    const moved = ["distributors", "history", "saved", "contracts", "connections", "review", "approval", "activity", "upload"];
    // Screens folded into others: next month's run is a row in History, a run's audit trail opens from its result,
    // the workspace's charges are the run's result, and the old console home is Home.
    const folded: [string, string][] = [
      ["april", "/app/history"], ["results", "/app/history"], ["audit", "/app/history"],
      ["workspace", "/app/agents"], ["coach", "/app"], ["scenario", "/app"], ["home", "/app"],
    ];
    return [
      { source: "/board/:path*", destination: "/app/agents", permanent: false },
      { source: "/", has: [{ type: "query", key: "view" }], destination: "/app/agents", permanent: false },
      { source: "/", has: [{ type: "query", key: "charge" }], destination: "/app/agents", permanent: false },
      ...folded.flatMap(([from, to]) => [
        { source: `/${from}`, destination: to, permanent: false },
        { source: `/app/${from}`, destination: to, permanent: false },
      ]),
      ...["account", "run", "home"].map((key) => ({ source: "/", has: [{ type: "query" as const, key }], destination: "/app/agents", permanent: false })),
      ...moved.map((m) => ({ source: `/${m}`, destination: `/app/${m}`, permanent: false })),
      { source: "/welcome", destination: "/", permanent: false },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

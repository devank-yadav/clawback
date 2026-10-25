import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // `/` is the public landing page; the app lives under /app. Every older address (the agents' flow at /?account=,
  // the list pages, the tools, the console pages, the workspace's /?view= links) keeps working: the query string
  // carries over, so emails, texts and portal links sent before the move still open the right screen.
  async redirects() {
    const moved = ["distributors", "history", "saved", "contracts", "connections", "home", "review", "approval", "activity",
      "workspace", "results", "april", "coach", "scenario", "upload", "audit"];
    return [
      { source: "/board/:path*", destination: "/app/workspace?view=payments", permanent: false },
      { source: "/", has: [{ type: "query", key: "view" }], destination: "/app/workspace", permanent: false },
      { source: "/", has: [{ type: "query", key: "charge" }], destination: "/app/workspace", permanent: false },
      ...["account", "run", "home"].map((key) => ({ source: "/", has: [{ type: "query" as const, key }], destination: "/app", permanent: false })),
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

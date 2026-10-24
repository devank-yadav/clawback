import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // `/` is the agents' flow; the workspace moved to /workspace, so its old links (/?view=…, /?charge=…) follow it.
  // The earlier fixture board was folded into the workspace's Payments view, and the console intro into the flow.
  async redirects() {
    return [
      { source: "/board/:path*", destination: "/workspace?view=payments", permanent: false },
      { source: "/", has: [{ type: "query", key: "view" }], destination: "/workspace", permanent: false },
      { source: "/", has: [{ type: "query", key: "charge" }], destination: "/workspace", permanent: false },
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

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Five places: Run (/), Charges, Overview, Records (/saved), Results. Every older address lands on the one that has
  // its content now; the query (?account=, ?charge=) comes along.
  async redirects() {
    const to = (source: string, destination: string, view?: string) =>
      ({ source, destination, permanent: false, ...(view ? { has: [{ type: "query" as const, key: "view", value: view }] } : {}) });
    return [
      to("/workspace", "/charges", "payments"),
      to("/workspace", "/charges", "approvals"),
      to("/workspace", "/saved", "rules"),
      to("/workspace", "/overview"),
      { source: "/", has: [{ type: "query", key: "view" }], destination: "/overview", permanent: false },
      { source: "/", has: [{ type: "query", key: "charge" }], destination: "/charges", permanent: false },
      to("/board/:path*", "/charges"),
      to("/review", "/charges"),
      to("/home", "/overview"),
      to("/history", "/overview"),
      to("/audit", "/saved"),
      to("/activity", "/"),
      to("/approval", "/"),
      to("/upload", "/"),
      to("/welcome", "/"),
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

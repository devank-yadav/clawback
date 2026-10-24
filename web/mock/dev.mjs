// npm run dev:mock — the mock API (web/mock/server.mjs) on :8010 and `next dev` pointed at it, in one terminal.
// Cross-platform (no shell env syntax). Ctrl+C stops both.

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const port = process.env.MOCK_PORT ?? "8010";
const env = { ...process.env, MOCK_PORT: port };
const mock = spawn(process.execPath, [fileURLToPath(new URL("./server.mjs", import.meta.url))], { env, stdio: "inherit" });
const next = spawn(process.platform === "win32" ? "npx.cmd" : "npx", ["next", "dev"], {
  env: { ...env, NEXT_PUBLIC_API_BASE: `http://localhost:${port}` },
  stdio: "inherit",
  shell: process.platform === "win32",
});

const stop = () => {
  mock.kill();
  next.kill();
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
mock.on("exit", stop);
next.on("exit", stop);

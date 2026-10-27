import {spawn} from "node:child_process";
import {resolve} from "node:path";
import {root} from "./python.mjs";

// Frontend readiness alone cannot establish that its API proxy target is ready.
const deadline = Date.now() + 120000;
let ready = false;
while (Date.now() < deadline) {
  try {
    ready = (await fetch("http://127.0.0.1:8001/health", {signal: AbortSignal.timeout(1000)})).ok;
  } catch { /* API is still starting. */ }
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 200));
}
if (!ready) throw new Error("Test backend did not become healthy");
const child = spawn(process.execPath, [resolve(root, "node_modules/next/dist/bin/next"), "dev", "--hostname", "localhost", "--port", "3001"], {
  cwd: resolve(root, "frontend"), stdio: "inherit", env: process.env,
});
child.on("exit", (code) => {process.exitCode = code ?? 1;});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));

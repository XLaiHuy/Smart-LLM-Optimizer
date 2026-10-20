import {spawnSync} from "node:child_process";
import concurrently from "concurrently";
import {resolve} from "node:path";
import {python, root} from "./python.mjs";
import {temporary} from "./temp.mjs";

const owned = temporary("smartllm-e2e-");
const env = {...process.env, APP_ENV: "test", DATABASE_PATH: resolve(owned.directory, "e2e.db"),
  ALLOWED_ORIGINS: '["http://localhost:3001"]', PROVIDER_MODE: "mock", COOKIE_SECURE: "false",
  E2E_PASSWORD: process.env.E2E_PASSWORD || "e2e-isolated-test-only", BACKEND_URL: "http://127.0.0.1:8001"};
const bootstrap = spawnSync(python, ["-m", "app.cli", "test-accounts"], {cwd: root, env, stdio: "inherit"});
if (bootstrap.status !== 0) {owned.cleanup(); process.exit(bootstrap.status || 1);}
const {result} = concurrently([
  {command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`, name: "api", env},
  {command: `"${process.execPath}" "${resolve(root, "node_modules/next/dist/bin/next")}" dev --hostname localhost --port 3001`, cwd: resolve(root,"frontend"), name: "web", env}
], {killOthersOn: ["failure", "success"]});
try {await result;} catch {process.exitCode = 1;} finally {owned.cleanup();}

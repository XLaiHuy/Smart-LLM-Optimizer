import {spawnSync} from "node:child_process";
import {existsSync} from "node:fs";
import {resolve} from "node:path";
import {python, root} from "./python.mjs";
let failed = false;
for (const [label, ok] of [
  ["Node 24", Number(process.versions.node.split(".")[0]) === 24],
  [".env configured", existsSync(resolve(root, ".env"))],
  ["frontend dependencies", existsSync(resolve(root, "node_modules/next"))],
]) {console.log(`${ok ? "OK" : "MISSING"} ${label}`); if (!ok) failed = true;}
const result = spawnSync(python, ["-c", "import sys, fastapi, sqlalchemy; assert sys.version_info[:2] == (3, 11); print('OK Python 3.11 / backend dependencies')"], {cwd: root, stdio: "inherit"});
if (result.status !== 0) failed = true;
process.exitCode = failed ? 1 : 0;

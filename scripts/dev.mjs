import concurrently from "concurrently";
import {python, root} from "./python.mjs";
const {result} = concurrently([
  {command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app`, name: "api", prefixColor: "blue"},
  {command: "npm run dev:frontend", name: "web", prefixColor: "cyan"}
], {cwd: root, killOthersOn: ["failure", "success"]});
result.catch(() => {process.exitCode = 1;});

import {spawnSync} from "node:child_process";
import {readFileSync, mkdirSync} from "node:fs";
import {join, resolve} from "node:path";
import {temporary} from "./temp.mjs";
import {python, root} from "./python.mjs";
const check = process.argv.includes("--check");
const owned = temporary("smartllm-contracts-");
const temp = owned.directory;
// Schema generation must not load local live keys or download optional models.
const env = {...process.env, APP_ENV: "test", PROVIDER_MODE: "mock",
  DATABASE_PATH: join(temp, "schema.db"), UPLOAD_DIRECTORY: join(temp, "uploads"),
  ADAPTIVE_PROMPT_ENABLED: "false", HYBRID_CONTEXT_ENABLED: "false", MEMORY_RETRIEVAL_ENABLED: "false",
  HF_HUB_OFFLINE: "1", TRANSFORMERS_OFFLINE: "1",
  OPENAI_API_KEY: "", GROQ_API_KEY: "", OPENROUTER_API_KEY: "", HUGGINGFACE_API_KEY: "", GEMINI_API_KEY: "",
  RESEARCH_LIVE_ENABLED: "false", ML_ROUTER_LIVE_APPROVED: "false", TOOLS_LIVE_APPROVED: "false",
  ML_ROUTER_ARTIFACT_PATH: join(temp, "no-live-artifact.json"),
  ROUTER_TRAINING_MANIFEST_PATH: join(temp, "manifest.json"), ROUTER_TRAINING_DIRECTORY: join(temp, "training")};
try {
  const schema = check ? join(temp, "openapi.json") : resolve(root, "docs/openapi.json");
  const types = check ? join(temp, "api.d.ts") : resolve(root, "frontend/src/lib/generated/api.d.ts");
  mkdirSync(resolve(root, "frontend/src/lib/generated"), {recursive: true});
  for (const [command, args] of [
    [python, ["-m", "app.cli", "openapi", "--output", schema]],
    [process.execPath, [resolve(root, "node_modules/openapi-typescript/bin/cli.js"), schema, "-o", types]]
  ]) {
    const run = spawnSync(command, args, {cwd: root, env, stdio: "inherit"});
    if (run.status !== 0) process.exit(run.status || 1);
  }
  if (check) {
    for (const [a,b] of [[schema, "docs/openapi.json"], [types, "frontend/src/lib/generated/api.d.ts"]]) {
      if (readFileSync(a, "utf8").replaceAll("\r\n", "\n") !== readFileSync(resolve(root,b), "utf8").replaceAll("\r\n", "\n")) {
        throw new Error(`Contract drift: ${b}. Run npm run contracts:generate.`);
      }
    }
    console.log("OpenAPI / TypeScript contracts match.");
  }
} finally {owned.cleanup();}

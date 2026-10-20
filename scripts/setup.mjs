import {copyFileSync, existsSync} from "node:fs";
import {resolve} from "node:path";
import {root} from "./python.mjs";
const target = resolve(root, ".env");
if (!existsSync(target)) {copyFileSync(resolve(root, ".env.example"), target); console.log("Created .env with mock defaults.");}
else console.log("Kept existing .env.");
console.log("Create/install .venv and npm dependencies using README, then npm run db:migrate and npm run account:create -- --username <name>.");

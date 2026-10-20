import {existsSync} from "node:fs";
import {resolve} from "node:path";
export const root = resolve(import.meta.dirname, "..");
export const python = existsSync(resolve(root, ".venv", "Scripts", "python.exe"))
  ? resolve(root, ".venv", "Scripts", "python.exe")
  : existsSync(resolve(root, ".venv", "bin", "python")) ? resolve(root, ".venv", "bin", "python") : "python";

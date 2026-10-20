import {mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {basename, dirname, join, resolve} from "node:path";

export function temporary(prefix) {
  const directory = mkdtempSync(join(tmpdir(), prefix));
  return {directory, cleanup() {
    const target = resolve(directory);
    if (dirname(target) !== resolve(tmpdir()) || !basename(target).startsWith(prefix)) throw new Error("Unsafe temporary cleanup path");
    rmSync(target, {recursive: true, force: true, maxRetries: 20, retryDelay: 100});
  }};
}

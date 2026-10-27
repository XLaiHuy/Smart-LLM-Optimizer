import { readFileSync } from "node:fs";

// `next start` loads runtime config separately from build metadata. Keep the
// proxy deadline from the reviewed build without loading build-only plugins.
const { config } = JSON.parse(
  readFileSync(
    new URL("./.next/required-server-files.json", import.meta.url),
    "utf8",
  ),
);

export default {
  poweredByHeader: config.poweredByHeader,
  experimental: { proxyTimeout: config.experimental.proxyTimeout },
};

// Call one product function and print its ledger result.

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const modulePath = process.argv[2];
const functionName = process.argv[3];
const imported = await import(pathToFileURL(modulePath).href);
const fn = imported[functionName];
if (typeof fn !== "function") {
  process.stdout.write(JSON.stringify({ ok: false, error: `${functionName} is not exported` }));
  process.exit(1);
}
let result;
try {
  result = await fn(...JSON.parse(readFileSync(0, "utf8")));
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  process.stdout.write(JSON.stringify({ ok: false, error: message }));
  process.exit(1);
}
const payload = result && typeof result === "object" ? result : { ok: false, error: "surface recorded nothing" };
process.stdout.write(JSON.stringify(payload));
if (payload.ok !== true) process.exit(1);

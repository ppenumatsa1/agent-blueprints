import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const html = readFileSync("dist/index.html", "utf8").replace(/\r\n?/g, "\n");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 1) throw new Error("Expected one inline theme script.");
const hash = createHash("sha256").update(scripts[0][1]).digest("base64");
const config = readFileSync("nginx.conf", "utf8");
const policy = config.match(/add_header\s+Content-Security-Policy\s+"([^"]+)"/)?.[1];
const scriptSources = policy?.split(";").map((part) => part.trim())
  .find((part) => part.startsWith("script-src "))?.split(/\s+/);
if (!scriptSources?.includes(`'sha256-${hash}'`)) {
  throw new Error("Update the nginx CSP hash for the built inline theme script.");
}
console.log("Inline theme script matches the nginx CSP.");

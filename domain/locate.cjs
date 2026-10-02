// Find the supply-chain hub, ledger, and sibling checkouts from domain data.
// Stage owners load this module. Search roots and the ledger path stay in the
// domain JSON files.

const { existsSync, readFileSync } = require("node:fs");
const { dirname, join, resolve } = require("node:path");

const MARKER_FILES = ["package.json", "pyproject.toml", "requirements.txt", "README.md"];

function isHub(path) {
  return existsSync(join(path, "domain", "org-ecosystem.json"))
    && existsSync(join(path, "domain", "supply-chain.json"));
}

function moduleHub() {
  let dir = __dirname;
  while (dir !== dirname(dir)) {
    if (isHub(dir)) return dir;
    dir = dirname(dir);
  }
  return null;
}

function hubRoot() {
  const override = process.env.SKINTWIN_HUB_ROOT;
  if (override && isHub(override)) return resolve(override);
  return moduleHub();
}

function readJson(hub, name) {
  return JSON.parse(readFileSync(join(hub, "domain", name), "utf8"));
}

function ledgerRelative(hub) {
  const relative = readJson(hub, "supply-chain.json").ledger;
  if (typeof relative !== "string" || relative === "" || relative.startsWith("/") || relative.startsWith("\\")) {
    throw new Error("supply-chain ledger must be a relative path");
  }
  if (relative.split(/[\\/]/).includes("..")) {
    throw new Error("supply-chain ledger must stay inside the hub");
  }
  return relative;
}

function searchRoots(hub) {
  const override = process.env.CLOUD_AGENT_REPO_ROOTS;
  if (override !== undefined) {
    return override.split(":").filter(Boolean).map((root) => resolve(root));
  }
  const listed = readJson(hub, "org-ecosystem.json").searchRoots;
  if (!Array.isArray(listed) || listed.length === 0 || listed.some((item) => typeof item !== "string" || item === "")) {
    throw new Error("searchRoots must be a non-empty list of strings");
  }
  const roots = listed.map((root) => resolve(root));
  const parent = dirname(resolve(hub));
  if (!roots.includes(parent)) roots.push(parent);
  return roots;
}

function ledgerFile(hub) {
  const root = hub || moduleHub();
  if (!root) return null;
  return join(root, ledgerRelative(root));
}

function bindLedger() {
  const hub = hubRoot();
  if (!hub) return null;
  process.env.SKINTWIN_HUB_ROOT ||= hub;
  process.env.SKINTWIN_CHAIN_LEDGER ||= ledgerFile(hub);
  return hub;
}

function checkout(name) {
  if (!name || name === "." || name === ".." || name.includes("/") || name.includes("\\")) return null;
  const hub = hubRoot();
  if (!hub) return null;
  const registry = readJson(hub, "org-ecosystem.json");
  if (name === registry.hub?.name) return hub;
  for (const root of searchRoots(hub)) {
    const directory = join(root, name);
    if (MARKER_FILES.some((marker) => existsSync(join(directory, marker)))) return directory;
  }
  return null;
}

function stageEntry(stageId) {
  const hub = hubRoot();
  if (!hub) return null;
  const stage = readJson(hub, "supply-chain.json").stages.find((item) => item.id === stageId);
  if (!stage || typeof stage.owner !== "string" || typeof stage.entry !== "string") return null;
  const root = checkout(stage.owner);
  if (!root) return null;
  const entry = join(root, stage.entry);
  return existsSync(entry) ? entry : null;
}

module.exports = {
  bindLedger,
  checkout,
  hubRoot,
  ledgerFile,
  moduleHub,
  stageEntry,
};

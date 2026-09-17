# Agent notes for skintwin-ecosystem-design

This hub is the Cloud Agent entry for **org-wide skintwin-ai work**. Start those runs from a `skintwin-ecosystem-design` revision so `.cursor/environment.json` loads. A sibling used as the primary repository does not load this environment.

## Sibling layout

Search roots (override with `CLOUD_AGENT_REPO_ROOTS`, colon-separated):

- `/agent/repos/<name>`
- `/workspace/repos/<name>`
- `/workspace/<name>`

Listing a repo in `repositoryDependencies` grants GitHub token scope so it can be cloned. It does **not** mean dependencies are installed.

Do not bulk-read sibling trees outside the current task. The token covers all 40 siblings, including GPU/Julia/PHP repos that install never bootstraps.

## CPU-core install vs checkout-only

`scripts/cloud-agent-install.sh` installs a CPU-core subset when present:

- Node: `skintwinnector` (yarn), `skinport` (pnpm), `skintwin-customer-portal` (pnpm), `cognitive-architecture` (`npm ci`), `regima-platform` (pnpm, do not add `pnpm-workspace.yaml`), `skintwin-bot` (prefer pnpm lock)
- Python: `org-skin` (`-e ".[dev]"`), `skintwin-integrations` (`requirements.txt`), `neuro-symbolic-core` (nettica + hybrid + pytest **package**)
- Presence only: `pcsdbx`

All other siblings are **checkout-only**. Missing `node_modules` or `.venv` there is expected.

Missing CPU-core checkouts log `[skip] <name>: not present` and do not fail install.

Install does **not** start servers, write secrets, or run application tests. Agents run tests later.

`skintwin-bot` install success does not mean a runnable `dist/entry.js`. Do not fix that, org-skin aggregator imports, or skintwinnector TypeScript asset errors in hub work.

Do not commit `.venv` directories or credential files created in sibling trees. Do not commit snapshot IDs.

## Config precedence

The committed `.cursor/environment.json` replaces dashboard environment documents for this git revision. Omitted keys follow schema and team policy defaults, not leftover dashboard fields.

Do not add `start` or `terminals` unless a later plan owns secret-backed services.

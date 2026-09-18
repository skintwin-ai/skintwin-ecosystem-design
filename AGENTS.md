# Agent notes for skintwin-ecosystem-design

This hub is the Cloud Agent entry for **org-wide skintwin-ai work**. Start those runs from a `skintwin-ecosystem-design` revision so `.cursor/environment.json` loads. A sibling used as the primary repository does not load this environment.

The canonical domain model is [`domain/org-ecosystem.json`](domain/org-ecosystem.json). Install kind, CPU-core vs checkout-only, skip-missing, frozen lockfiles, and hub-only constraints live there. Do not re-encode those decisions as new if/else in scripts or docs.

## Sibling layout

Search roots (override with `CLOUD_AGENT_REPO_ROOTS`, colon-separated):

- `/agent/repos/<name>`
- `/workspace/repos/<name>`
- `/workspace/<name>`

Listing a repo in `repositoryDependencies` grants GitHub token scope so it can be cloned. It does **not** mean dependencies are installed.

Do not bulk-read sibling trees outside the current task. The token covers all 40 siblings, including GPU/Julia/PHP repos that install never bootstraps.

## CPU-core install vs checkout-only

`scripts/cloud-agent-install.sh` reads the registry and bootstraps the CPU-core subset when present. Checkout-only siblings, including GPU/Julia/PHP stacks, stay uninstalled.

Missing CPU-core checkouts log `[skip] <name>: not present` and do not fail install.

Install does **not** start servers, write secrets, or run application tests. Agents run tests later.

`skintwin-bot` install success does not mean a runnable `dist/entry.js`. Do not fix that, org-skin aggregator imports, or skintwinnector TypeScript asset errors in hub work.

Do not commit `.venv` directories or credential files created in sibling trees. Do not commit snapshot IDs.

Do not add `pnpm-workspace.yaml` to `regima-platform`. Do not add `$schema` to `.cursor/environment.json`. Do not add `start` or `terminals` unless a later plan owns secret-backed services.

## Config precedence

The committed `.cursor/environment.json` replaces dashboard environment documents for this git revision. Omitted keys follow schema and team policy defaults, not leftover dashboard fields. Keys stay exactly `name`, `install`, `repositoryDependencies`.

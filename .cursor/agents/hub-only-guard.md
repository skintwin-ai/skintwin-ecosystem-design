---
name: hub-only-guard
description: Hub-only shipping guard for skintwin-ecosystem-design. Use proactively before commits, branch switches, or any change that might touch a sibling repository.
---

You keep Cloud Agent and domain work **inside this hub**.

When invoked:

1. Confirm the git repo is `skintwin-ecosystem-design`.
2. Do not switch other repos' branches. Do not stash. Do not create sibling worktrees.
3. Commit only hub files: `domain/`, `scripts/`, `tests/`, `.cursor/`, `AGENTS.md`, `README.md`, and hub docs that describe this environment.
4. Do not add `pnpm-workspace.yaml` to `regima-platform`.
5. Do not fix pre-existing sibling bugs:
   - org-skin aggregator imports
   - skintwinnector TypeScript asset errors
   - skintwin-bot missing `dist/entry.js`
6. Do not install GPU, Julia, or PHP toolchains as default Cloud Agent bootstrap.
7. Do not put live secrets, tokens, phone numbers, or snapshot IDs in committed files.
8. Do not add `start` or `terminals` to environment.json unless a later plan owns secret-backed services.

If a task seems to require editing a sibling to make hub tests pass, stop. Hub tests are hermetic via `CLOUD_AGENT_REPO_ROOTS` and must not require sibling mutation.

---
name: agents-memory-updater
description: Continual-learning memory updater for this hub. Use proactively when asked to mine prior chats, maintain AGENTS.md learned sections, or run the continual-learning loop. Parent flows must delegate rather than mining transcripts themselves.
---

Own the full memory update flow for continual learning in `skintwin-ecosystem-design`.

When invoked:

1. Read existing `AGENTS.md` first. Keep the operational hub notes (Cloud Agent entry, registry pointer, CPU-core vs checkout-only). If the learned sections are missing, add only:
   - `## Learned User Preferences`
   - `## Learned Workspace Facts`
2. Load the incremental index if present at `.cursor/hooks/state/continual-learning-index.json`.
3. Inspect only transcript files under `~/.cursor/projects/<workspace-slug>/agent-transcripts/` that are new or have newer mtimes than the index.
4. Pull out only durable, reusable items:
   - recurring user preferences or corrections
   - stable workspace facts
5. Update `AGENTS.md` carefully:
   - update matching bullets in place
   - add only net-new bullets
   - deduplicate semantically similar bullets
   - keep each learned section to at most 12 bullets
   - use plain bullet points only
6. Refresh the incremental index for processed transcripts and remove entries for files that no longer exist.
7. If the merge produces no `AGENTS.md` changes, leave `AGENTS.md` unchanged but still refresh the index.
8. If no meaningful updates exist, respond exactly: `No high-signal memory updates.`

Guardrails:

- Keep only the two learned sections plus the existing operational notes. Do not replace the operational Cloud Agent / registry sections with learned bullets.
- Do not write evidence/confidence tags.
- Do not write process instructions, rationale, or metadata blocks into `AGENTS.md`.
- Exclude secrets, private data, one-off instructions, and transient details.
- Do not mine transcripts by scattering grep through the parent flow; this subagent owns that work.

Known durable workspace facts that already belong in operational notes (do not duplicate unless the learned section is empty and the operational section is gone):

- Org-wide Cloud Agent env starts from this hub
- Skip-missing CPU-core bootstrap
- Hub-only files
- Frozen lockfiles
- No GPU/Julia/PHP default install
- No start/terminals/daemons
- No live secrets
- No `$schema` in environment.json
- Do not add `pnpm-workspace.yaml` to `regima-platform`
- Do not fix pre-existing sibling bugs

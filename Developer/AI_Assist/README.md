# DGBlocks AI Assist — Memory Bank Index

This folder contains the **Memory Bank**: a small set of Markdown files that
together describe the DGBlocks template at every scope from naming
conventions to overall architecture. The Memory Bank is the canonical
context to give an AI assistant (or a new contributor) before asking it to
write or edit a block.

---

## Read Order

For a new contributor / new chat session, read in this order:

1. **`Memory_Bank/projectBrief.md`** — *what* DGBlocks is and *why* it exists.
2. **`Memory_Bank/productContext.md`** — lifecycle, two-tier data model,
   inter-block communication, DX/UX goals.
3. **`Memory_Bank/systemPatterns.md`** — the standards reference. Naming,
   comments, imports, the Wrapper-Record pattern, the three standard enums,
   registration boilerplate, hooks, logging, RTC, sync, UI, error handling,
   and the "where does my code go?" decision matrix.
4. **`Memory_Bank/techContext.md`** — Blender/Python version targets,
   stdlib usage, Blender APIs touched, file-by-file roles.
5. **`Memory_Bank/activeContext.md`** — *current focus, recent changes, open
   inconsistencies, next steps.* **Update this file every session.**
6. **`Memory_Bank/progress.md`** — per-block status board.
7. **`Memory_Bank/blockAuthoringGuide.md`** — step-by-step recipe for
   authoring a new block, with copy-pasteable skeletons.

---

## Reference Blocks

Three blocks under `native_blocks/` are intended as canonical examples. Read
their source alongside the Memory Bank:

- `block_core/` — every framework primitive lives here.
- `block_debug_console_print/` — the model for hook *subscription* and for
  drawing developer-facing debug UI.
- `block_onscreen_drawing/` — the model for managing many RTC instances + GPU
  resources.

---

## Conventions for Editing the Memory Bank

- **Source of truth = the code.** If a Memory Bank file disagrees with the
  current state of the reference blocks, the code wins. Update the doc.
- **Don't duplicate.** A pattern lives in exactly one of these files. Cross-
  reference instead of copying.
- **`activeContext.md` and `progress.md` are living docs.** The other four
  files change rarely.
- **One commit per Memory Bank update.** Don't bundle Memory Bank edits with
  feature work — it makes the history harder to read.

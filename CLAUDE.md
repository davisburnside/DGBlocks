# DGBlocks — Claude Code entry point

DGBlocks is a modular block-based framework for Blender addons: each feature is a
self-contained `block_<name>` folder (bpy classes, properties, runtime cache, hooks,
loggers, registration) that plugs into a shared lifecycle manager. `external_blocks/`
holds only *links* to consumer block repos that live beside this checkout; today that is
**Flatypus**, a separate addon built *on top of* DGBlocks with its own `CLAUDE.md` — don't
assume its conventions from this file alone. Dev-environment setup (worktrees, links,
Blender profiles) lives in the sibling `devkit/` folder, not in this repo.

This file is a router, not a reference. Read only the doc(s) a task actually needs —
don't preload the whole Developer/ tree.

## Repo layout

```
__init__.py            addon entry point (bl_info, register/unregister)
addon_config/           addon_name, addon_bl_type_prefix, active block list, prefs
addon_helpers/          generic utilities + ALL declaration dataclasses (data_structures.py)
                        never imports from a block
native_blocks/          shipped blocks; block_core is required by every other block
unfinished_blocks/      WIP/stub blocks — READ-ONLY reference unless told otherwise
external_blocks/        links to sibling block repos (Flatypus: own CLAUDE.md — see below)
Developer/              docs (see routing table)
```

Every `block_<name>/` follows: `__init__.py` (`_BLOCK_DECLARATION`), `constants.py`
(`Block_Hook_Sources` / `Block_Loggers` / `Block_RTC_Members` / `Block_Data_Mirrors`),
`feature_*.py` (one Feature Wrapper Class each), optional `helper_functions.py`, `README.md`.

## Hard rules (apply regardless of task)

- **Code is truth.** If any doc disagrees with the current reference blocks, the code
  wins — fix the doc, don't fight the code.
- **Don't touch `unfinished_blocks/`** unless the user explicitly asks. Read-only reference.
- **One-directional dependencies.** A block may only import a block listed in its own
  `_BLOCK_DECLARATION.block_dependencies`. Never the reverse.
- **No magic strings** for hook names / RTC keys / logger IDs — use the enum members in
  `constants.py`. No `print()` — use `get_logger(...)`.
- Inspect the target block **and** its closest canonical reference block before writing
  or editing anything. Prefer extending an existing pattern over inventing a new one.

## Task routing — "I need to do X, what do I read?"

| Task | Read |
|---|---|
| Author/edit a native block, need the full pattern set (declarations, FWCs, hooks, RTC, data mirrors, naming) | `Developer/AI_Assist/Summarized_Memory_Bank.md` (dense, ~700 lines, self-contained) |
| Same, but want prose explanations / lifecycle rationale instead of just patterns | `Developer/Structural_Standards/Block_Structure_Overview.md` |
| Step-by-step recipe + skeleton code for a brand-new block | `Developer/AI_Assist/Memory_Bank/blockAuthoringGuide.md` |
| What's currently in-flight / recently changed in this repo | `Developer/AI_Assist/Memory_Bank/activeContext.md`, then `progress.md` |
| Why DGBlocks exists, lifecycle & DX goals, two-tier data model | `Developer/AI_Assist/Memory_Bank/projectBrief.md`, `productContext.md` |
| Blender/Python version targets, stdlib & Blender API surface used | `Developer/AI_Assist/Memory_Bank/techContext.md` |
| Full naming/comment/import/hook/logging standards reference | `Developer/AI_Assist/Memory_Bank/systemPatterns.md` |
| Working inside one specific block | that block's own `README.md` first |
| Depsgraph / msgbus triggers, property update events, data persistence, threading, git | `Developer/Cheatsheets/*.md` (one topic per file) |
| Writing or running tests for a block | `Developer/Structural_Standards/Unit_Testing_Framework.md` |
| Backlog / requested cleanups not yet actioned | `Developer/Wants_and_Needs/*.txt` |
| Working in `external_blocks/` (Flatypus) | its own `CLAUDE.md`, then its `MODULE_MAP.md` |
| Setting up worktrees / Blender profiles / block links | `../devkit/README.md` (sibling folder, not in this repo) |

`Developer/AI_Assist/README.md` has the full "fresh contributor" read order if you ever
need the whole picture at once; the table above is the fast path for a single task.

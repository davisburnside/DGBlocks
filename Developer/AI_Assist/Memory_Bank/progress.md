# DGBlocks — Progress

> Per-block status. The Memory Bank's "where things stand". Update when a
> block changes status. Always cross-check against `activeContext.md`.

---

## Status Legend

| Status | Meaning |
|---|---|
| 🟢 **Stable** | Reference-quality. Pattern is settled. Safe to copy from. |
| 🟡 **Working** | Functional but pre-canonical. May still get refactored. |
| 🟠 **In progress** | Partially built, in `unfinished_blocks/` or marked WIP. |
| 🔴 **Stub** | Skeleton only. Don't trust the patterns inside it yet. |
| ⚫ **Deprecated** | Replaced by another block; do not use. |

---

## Native Blocks (`native_blocks/`)

| Block | Status | Notes |
|---|---|---|
| `block_core` | 🟢 Stable | Hard dep of every other block. The reference for the Wrapper-Record + RTC + Hooks + Logging patterns. Has small cleanups outstanding (see `activeContext.md` items #3, #4, #7). |
| `block_debug_console_print` | 🟢 Stable | Reference block for hook *subscription*. Uses every core hook source. Has the registration-guard bug noted in `activeContext.md` item #2. |
| `block_onscreen_drawing` | 🟡 Working | Reference for managing many RTC instances + GPU resources. Owns its own draw/shader hook sources. Needs `register_block(event)` arg added (item #1). |
| `block_pip_library_manager` | 🟠 In progress | Pip install/uninstall + dependency tracking. UI scaffolding present; install/uninstall flow under construction. |
| `block_stable_modal` | 🟠 In progress | Single reentrant modal operator. Most of the lifecycle exists; reentrancy guarantees still being verified. |
| `block_timers` | 🟠 In progress | Wrapper around `bpy.app.timers`. Useful as the first non-trivial block to author against the new guide. |

---

## Unfinished Blocks (`unfinished_blocks/`)

| Block | Status | Notes |
|---|---|---|
| `block_data_enforcement` | 🔴 Stub | Was the original home of pip-import logic; superseded by `block_pip_library_manager`. Likely to be deleted once everything useful is moved. |
| `block_event_listeners` | 🔴 Stub | Intended generic event-listener registry. Not started in earnest. |
| `block_numba_accelerate` | 🔴 Stub | Optional numba JIT integration — depends on `block_pip_library_manager`. |
| `block_stable_timers` | 🔴 Stub | Earlier attempt at timer wrapping; subsumed by `block_timers`. |
| `block_ui_display_modal` | 🔴 Stub | Modal-driven popover/HUD; depends on `block_stable_modal`. |
| `block_unit_tests` | 🔴 Stub | Goal: per-block unit tests runnable from inside Blender. |

---

## Memory Bank

| File | Status | Last verified |
|---|---|---|
| `projectBrief.md` | 🟢 Current | This pass |
| `productContext.md` | 🟢 Current | This pass |
| `systemPatterns.md` | 🟢 Current | This pass |
| `techContext.md` | 🟢 Current | This pass |
| `activeContext.md` | 🟢 Current | This pass |
| `progress.md` | 🟢 Current | This pass |
| `blockAuthoringGuide.md` | 🟢 Current | This pass |

---

## What Works End-to-End Today

- Addon installs; `block_core` registers; `Wrapper_Runtime_Cache`,
  `Wrapper_Loggers`, `Wrapper_Hooks`, `Wrapper_Control_Plane` all bootstrap.
- A block declared in `_ordered_blocks_list` gets validated, its bpy classes
  registered, its FWCs init'd, its loggers/hooks/RTC slots created.
- BL↔RTC sync round-trips on file-load and on undo/redo.
- Hooks dispatch with kwargs, `@hook_data_filter` bypasses, and metadata
  collection.
- Per-feature loggers writable to via the dev-only Loggers UIList.
- Onscreen GPU drawing of arbitrary shader instances per draw phase.
- Debug console-print of any block's RTC + scene properties.
- Runtime enable/disable of blocks — verified to work, clears disabled and invalid blocks (due to a dependency now missing)
- Automatic syncronization between Blender Data & RTC on undo/redo events.
---

## What Doesn't Work Yet (or Is Brittle)

 End-to-end on/off has not been thoroughly tested. The signature
  mismatch in `activeContext.md` item #1 actively breaks it for
  `block_onscreen_drawing`.
- **Pip dependency installs** — gated on `block_pip_library_manager` finishing.
- **Modal stability** — `block_stable_modal` has the patterns but hasn't been
  hammered.
- **Unit tests** — none. `block_unit_tests` is a stub.
- **Extension manifest** — not wired. Addon ships as a classic `bl_info` addon.

# DGBlocks — Product Context

> *Why* the system is shaped this way, from the perspective of a developer
> using the template. For *what* the patterns are, see `systemPatterns.md`.
> For a step-by-step recipe, see `blockAuthoringGuide.md`.

---

## 1. Lifecycle Overview

A DGBlocks-based addon goes through five distinct phases. Understanding which
phase you're in is critical when deciding *where* a piece of logic should live.

### Phase A — Module Reload (top of `__init__.py`)
Blender's "Reload Scripts" only reloads top-level modules. DGBlocks walks every
already-loaded submodule and `importlib.reload`s each one, deepest-first, so a
single reload propagates everywhere.

### Phase B — `register()` (pre-bpy)
The main `__init__.py` calls `register()`. At this point `bpy.context` is *not*
fully usable. We can register classes and PropertyGroups, but not read scene
data. Steps in order:

1. **Bootstrap core feature wrappers** that are needed before any logger/RTC
   call: `Wrapper_Runtime_Cache`, then `Wrapper_Loggers`.
2. **Bootstrap `Wrapper_Control_Plane`.**
3. **Validate the ordered block list.** A block is rejected if it's missing
   `_BLOCK_ID`, `_BLOCK_VERSION`, `_BLOCK_DEPENDENCIES`, `register_block`, or
   `unregister_block`, or if a declared dependency isn't already registered.
4. **For each valid block, call `block.register_block(event)`.** Inside, the
   block calls `Wrapper_Control_Plane.create_instance(...)`, which:
   - Registers all `bpy.types.*` classes
   - Calls `init_pre_bpy()` on each Feature Wrapper Class (FWC)
   - Caches the block's metadata in the RTC
   - Creates the block's RTC member slots, loggers, and hook sources
   - Attaches the block's PropertyGroup to `bpy.types.Scene` (or wherever).

### Phase C — Post-Register (post-bpy, deferred)
We can't read scene data during `register()`, so DGBlocks defers a second init
pass. Two paths trigger it; whichever fires first wins, and a flag in the RTC
prevents the second from running:

- `bpy.app.handlers.load_post` — fires when a `.blend` is opened.
- `bpy.app.timers.register(...)` polled every 0.1s — fires for "new file"
  startup, where `load_post` doesn't run.

Once `bpy.context` is ready, `Wrapper_Control_Plane.init_post_bpy()`:

1. Performs the initial RTC↔Blender two-way sync (Blender is source of truth).
2. Calls `init_post_bpy(event)` on every registered FWC, in deterministic
   order.
3. Fires the `hook_post_register_init` hook so individual blocks can do
   their own post-context-ready work.
4. Marks the addon "started successfully" in the RTC.

### Phase D — Final init hook (optional)
After 'post_bpy_init' runs for all blocks & their components are registered & the addon is fully ready, the hook function ** will run for any block that subscribes to it.

### Phase E — Runtime
The addon is alive. Most logic runs through:
- **Operators** → user-driven actions.
- **Property update callbacks** → re-sync RTC from Blender, sometimes propagate
  via hooks.
- **Hook callbacks** → cross-block reactions, all flowing through
  `Wrapper_Hooks.run_hooked_funcs(...)`.
- **`bpy.app.handlers`** for undo/redo/load — all consolidated in core-block,
  which fans them out via hooks.

During runtime, blocks can still be added & removed, just like during registration/unregistration
This includes all hook/logger/RTC components of a block. 

### Phase F — `unregister()`
Blocks unregister in **reverse order** of registration. Each block calls
`Wrapper_Control_Plane.destroy_instance(...)`, which:

1. Unregisters all bpy classes.
2. Calls `destroy_wrapper()` on each FWC.
3. Removes the block's loggers, hooks, and RTC members.

Core-block destroys itself last, including the RTC itself.

---

## 2. The Two-Tier Data Model

This is the single most important mental model in the codebase.

| Layer | Where it lives | Persisted? | Undo/Redo aware? | Holds |
|---|---|---|---|---|
| **Source of truth** | `bpy.props` on PropertyGroups attached to `bpy.types.Scene` (or `Object`, `WindowManager`, `AddonPreferences`...) | Yes — saved in `.blend` | Yes | User-editable, primitive-typed data only |
| **Runtime Cache (RTC)** | `Wrapper_Runtime_Cache._cache` (a thread-safe dict) | No — rebuilt on register/load | No | Python-only data: dataclasses, callables, numpy arrays, raw json, registries… |

**Rules of thumb:**
- A user clicks a checkbox → write to the PropertyGroup → an `update=` callback
  syncs the change into the RTC.
- A python-only fact (e.g., "this draw handler's `_generated_handle` is X") →
  RTC only.
- After a load/undo/redo, the RTC is **rebuilt from Blender**, never the other
  way around.
- Blender data references (`bpy.types.ID`) **must not** be cached in the RTC.
  Cache identifiers (names/paths) and re-resolve on use.

A wrapper that needs both layers inherits from
`Abstract_BL_RTC_List_Syncronizer` and implements
`update_RTC_with_mirrored_BL_data` and `update_BL_with_mirrored_RTC_data`.

---

## 3. Communication Between Blocks

Direct cross-block imports are allowed for **type/enum/wrapper-class
references** but discouraged for *triggering behavior*. Behavioral coupling goes
through the **Hook System**:

1. **The publisher block** declares a hook *source* in its `Block_Hook_Sources`
   enum. The enum value is a tuple `(hook_func_name, expected_kwargs_dict)`.
2. **The publisher block** calls `Wrapper_Hooks.run_hooked_funcs(...)` at the
   appropriate time.
3. **Subscriber blocks** define a top-level function with the matching name in
   their `__init__.py`. No registration call needed — discovery is by name.
4. **Subscribers may filter** with `@hook_data_filter(predicate)` to bypass
   their own callback when a runtime condition isn't met.

Why a name-based hook system instead of, say, a pub/sub registry call? Because
a subscriber block can be **completely deleted from the project**, and the
publisher needs zero changes. That's the whole modularity guarantee.

---

## 4. Developer Experience Goals

- **Editing one block doesn't break others.** Blocks are independently
  testable. A typo in `block-onscreen-drawing` should not crash
  `block-debug-console-print`.
- **Console-printing data is a first-class debugging tool.** Every block
  contributes a `hook_debug_get_state_data_to_print` so a single button can
  dump that block's state.
- **Loggers are per-feature, not per-addon.** When a bug shows up in
  `Wrapper_Draw_Handlers`, you set the `DRAWHANDLER_LIFECYCLE` logger to DEBUG
  and *only* that subsystem becomes verbose.
- **Magic strings are forbidden.** Anything that would otherwise be a string
  literal — hook names, RTC keys, logger ids — lives in an `Enum` so the IDE
  autocompletes it.
- **Comments tell you the *role* of the file.** Section banners
  (`# === BLOCK DEFINITION ===`, etc.) appear in the same order in every
  block, so a developer scrolling a new block recognizes the layout
  immediately.

---

## 5. End-User Experience Goals

- Users never read the word "block" in the UI. They see panels with feature
  names.
- Debug panels are gated by `should_show_developer_ui_panels` in
  `my_addon_config.py` and turned off in release builds.
- A user with no Python knowledge can install the addon, click a checkbox to
  enable it, and have it Just Work — even if some block declared a dependency
  on a missing pip library, in which case the UI surfaces an actionable alert
  rather than a stack trace.

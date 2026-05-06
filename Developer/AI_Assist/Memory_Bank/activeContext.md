# DGBlocks — Active Context

> The "what we are working on right now" doc. **Update this every session.**
> When in doubt, this is the file an AI assistant should read first to know
> what's wet paint vs. dried.

---

## Current Focus

Stabilizing the three reference blocks (`block_core`,
`block_debug_console_print`, `block_onscreen_drawing`) so they can act as the
canonical examples for all future block authoring. Expanding the Memory Bank
to support that.

---

## Recent Changes

- Memory Bank fully rewritten (`projectBrief`, `productContext`,
  `systemPatterns`, `techContext`) from the current state of the reference
  blocks. The previous Memory Bank described an older API
  (`register_block_components`, `Block_Logger_Config`, etc.) and is no longer
  accurate.
- New file `blockAuthoringGuide.md` added to the Memory Bank as the
  recipe/skeleton for authoring a new block.
- New file `progress.md` added as the per-block status board.

---

## Open Inconsistencies (resolve before treating any block as "done")

These came up while comparing the three reference blocks against each other.
The author should pick a single canonical form and propagate it.

1. **`register_block` / `unregister_block` signatures**
   - `block_core` and `block_debug_console_print` accept
     `event: Enum_Sync_Events`.
   - `block_onscreen_drawing` accepts no args.
   - `Wrapper_Block_Management.evaluate_and_update_block_statuses` calls
     `block.register_block(event)`, so the no-arg version will break runtime
     enable/disable.
   - **Resolution:** all `register_block` / `unregister_block` should accept
     `event: Enum_Sync_Events`. Update `block_onscreen_drawing`.

2. **PropertyGroup deletion guard**
   - `block_debug_console_print` does
     `if hasattr(block_core.DGBLOCKS_PG_Core_Props, "dgblocks_debug_console_print_props"):`
     which checks the *wrong* class (the core PG, not `bpy.types.Scene`).
     Should be `if hasattr(bpy.types.Scene, "dgblocks_debug_console_print_props"):`.

3. **`feature_block_manager.func_t1`** — leftover debug stub at the bottom of
   `block_core/__init__.py`. Should be deleted.

4. **`DGBLOCKS_OT_Debug_Clear_And_Restore_Caches`** has the same `bl_idname`
   as `DGBLOCKS_OT_Force_Reload_Scripts` (`"dgblocks.debug_force_reload_scipts"`).
   This will fail registration. Need to give it a unique idname and fix the
   `scipts` typo (should be `scripts`).

5. **Documentation_URLs is a placeholder** — every block currently uses
   `Documentation_URLs.MY_PLACEHOLDER_URL_2`. Real URLs need to be wired
   per-block before release.

6. **`hook_post_register_init` is missing from
   `Core_Block_Hook_Sources.value[1]` arg dict** but is documented as
   parameter-less. Convention says hooks with no kwargs declare an empty dict
   — this is fine, just noting it for the authoring guide.

7. **`Wrapper_Block_Management.is_block_enabled` calls `cls.get_block_instance(block_id)`
   which raises** instead of returning `None` for unknown blocks. The verb
   table in `systemPatterns.md` §4.3 says `get_*` should return `None`.
   Either rename to `determine_block_instance` (raising) or change the
   behavior to return `None`.

8. **Older doc still in the repo:** `Developer/Structural_Standards/Block_Structure_Overview.md`
   uses `Block_Hooks` and `Block_Runtime_Cache_Members` as enum names; the
   actual code uses `Block_Hook_Sources` and `Block_RTC_Members`. The Memory
   Bank uses the current names. Either update the older doc or delete it in
   favor of `systemPatterns.md`.

---

## Next Three Logical Steps

1. **Resolve the inconsistencies above** so the reference blocks match the
   Memory Bank's standards. Without that, AI-authored blocks will inherit
   whichever form they happen to be shown.
2. **Author one new "trivial" block** end-to-end against the
   `blockAuthoringGuide.md` skeleton (e.g. a no-op block that just defines a
   logger and a hook source). Use it as the smoke test for the guide and
   amend whatever the guide gets wrong.
3. **Promote one `unfinished_blocks/` block** through the same checklist —
   probably `block_timers`, since a working bpy.app.timer wrapper unblocks
   several other features.

---

## Decisions Pending

- **Should `external_blocks/` be a sibling of `native_blocks/` or a sub-folder
  inside it?** Current `my_activated_blocks.py` imports from
  `from .external_blocks import block_flatypus_modes_manager` but the folder
  isn't shown in the workspace tree. Confirm whether this folder is intended
  to be commit-tracked or git-ignored.
  ANSWER: external_blocks is a sibling of native_blocks

- **`DGBLOCKS_*` prefix for re-skinned addons** — should the authoring guide
  recommend leaving the prefix as `DGBLOCKS` and only changing
  `addon_bl_type_prefix`, or rewriting class names too? Lean toward the former.
    ANSWER: To allow multiple block-based addons in Blender, the developer replaces all "DGBLOCKS_" strings with their own unique one.


---

## Known Headaches

- **Recursive reload** doesn't perfectly handle moving/renaming files at
  runtime. Restart Blender after structural refactors.
- **Post-bpy init dual-trigger** (load_post + timer) is correct but
  hard-to-debug if a block's `init_post_bpy` raises silently. Always wrap
  block-side post-init in `try/except + logger.error(exc_info=True)`.
- **Property `update=` callbacks fire during `register_class()` itself in some
  Blender versions.** That's why `is_bpy_ready()` and the syncing flag exist —
  always guard.

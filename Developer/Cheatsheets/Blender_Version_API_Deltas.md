# Blender Python API Deltas — 5.0 → 5.3

DGBlocks' floor is `bl_info["blender"] = (5, 0, 0)` (`__init__.py`). Everything below is API
surface that **changed within that supported window** — either added in 5.1/5.2/5.3 with no
5.0 equivalent, or renamed/restructured between point releases. Written ahead of the planned
geometry-nodes-manipulation block (and a possible sculpting block) so those blocks are designed
against the right target from day one, instead of discovering a rename mid-implementation.

This sheet is **inventory only** — no version-gating helper exists yet in `addon_helpers`.
Dispatch/fallback mechanism is a separate, not-yet-made design decision; don't invent a
per-block pattern for it until that lands.

Verify against the actual release notes before relying on exact signatures — this is a summary,
not a mirror. See References at the bottom.

---

## Quick reference

| Ver | Area | Old | New | DGBlocks relevance |
|---|---|---|---|---|
| 5.0 | Node editor space | `SpaceNodeEditor.geometry_nodes_type` / `.geometry_nodes_tool_tree` | `.node_tree_sub_type` / `.selected_node_group` | Geonodes block — if it reads active node-tree context from a `SpaceNodeEditor` |
| 5.0 | File Output node | `node.file_slots[i].path` | `node.file_output_items[i].name` | Low — no compositor block planned |
| 5.0 | Compositor nodes | `CompositorNodeGamma` etc. | Replaced by `ShaderNode*` equivalents | Low — no compositor block planned |
| 5.1 | Interpreter | Python 3.12 (approx.) | Python 3.13 (VFX Platform 2026) | All blocks — stdlib/typing behavior baseline |
| 5.1 | `UILayout.template_list` | `columns=` param | Deprecated (was already non-functional since 5.0) | Any block using `template_list` — drop the arg |
| 5.1 | Sculpt ops | `sculpt.sample_color` | Removed, merged into `paint.sample_color` | Sculpting block, if ever built |
| 5.1 | Brush props | Separate stroke-behavior props | Consolidated into `brush.stroke_method` enum | Sculpting block, if ever built |
| 5.2 | GeoNodes modifier | `modifier["Input_2"]` / `modifier["Input_2_attribute_name"]` (custom props) | `modifier.properties.inputs.<id>.value` / `.type` / `.attribute_name`, `modifier.properties.outputs.<id>.attribute_name` (proper RNA) | **Geonodes block — core.** See below |
| 5.2 | Node panels | No Python access to panel open/closed state | RNA-exposed open/close per node panel | Geonodes block — UI state for grouped node inputs |
| 5.3 | UI layout | Manual per-line `label()` looping (hand-rolled wrap) | `UILayout.label_multiline(text=..., icon=..., alignment=...)` | **Already hand-rolled once** — see below |
| 5.3 | Undo | No read API; only `bpy.app.handlers.undo_pre/post` event hooks | `context.window_manager.undo_stack` — read-only history query | Debug/introspection tooling, not a hook replacement — see below |
| 5.3 | UI buttons | — | `WindowManager.try_activate_rna_button()` — programmatically focus/activate a button bound to an RNA path | Possible use in modal/keymap-driven UI blocks |

---

## Geometry Nodes modifier RNA (5.2) — read before starting the geonodes block

Pre-5.2, geometry-node modifier inputs/outputs live as **custom properties** (`IDProperty`) on
the modifier, keyed by an opaque identifier string (`"Input_2"`, `"Input_2_use_attribute"`,
`"Input_2_attribute_name"`). This is what most existing geonodes-scripting examples online still
show.

5.2+ replaces this with real RNA:

```python
mod = obj.modifiers["GeometryNodes"]

# Pre-5.2 (custom props):
mod["Input_2"] = 1.0
mod["Input_2_attribute_name"] = ""

# 5.2+ (RNA):
mod.properties.inputs["Input_2"].value = 1.0
mod.properties.inputs["Input_2"].attribute_name = ""
mod.properties.outputs["Output_3"].attribute_name = "my_attr"

# Custom UI layout property binding — 5.2+ needs `.value` explicitly:
layout.prop(data=mod.properties.inputs["Input_2"], property="value", text="Example")
```

Since the floor is 5.0, a geonodes block touching modifier inputs/outputs **must** branch on
this — there is no single code path that works 5.0–5.3 unchanged. This is the strongest
candidate in this whole sheet for whatever version-gate/fallback mechanism gets designed;
unlike the UI-wrap and undo-stack cases there's no "degrade gracefully" option, both branches
have to actually work.

Node panel open/close state (also 5.2) is the other piece relevant here if the block exposes
grouped node-group inputs (panels) in custom UI — pre-5.2 there's no way to read/set that state
from Python at all, so on 5.0/5.1 the block can only leave panel state to Blender's own UI.

---

## UI label wrapping (5.3) — DGBlocks already hand-rolled this

`native_blocks/block_pip_library_manager/ui.py` predates 5.3's native wrap support and does it
manually:

- [`ui.py:22-33`](../../native_blocks/block_pip_library_manager/ui.py) — `_wrap_text(text, width=82)`,
  word-wrap by character count, called at `ui.py:40` and `ui.py:84` in a loop of `box.label(text=line)`.
- [`ui.py:93`](../../native_blocks/block_pip_library_manager/ui.py) — hard truncation, no wrap at
  all: `log_box.label(text=(line[:105] + "…") if len(line) > 106 else line)`.

5.3+ native equivalent:

```python
layout.label_multiline(text=long_text)          # replaces the _wrap_text() loop
```

This is the "graceful degrade" case in the table above: pre-5.3, `_wrap_text` + per-line
`label()` is the only option and keeps working fine on every version; 5.3+ *can* use
`label_multiline` instead but doesn't have to. Good candidate for a "prefer new if available,
fall back silently" pattern rather than a hard version gate — no behavior is impossible on
the older side, just uglier to write.

---

## Undo stack (5.3) — distinct from existing undo hooks, not a replacement

DGBlocks already reacts to undo/redo via `bpy.app.handlers.undo_pre` / `undo_post`, owned by
`block_core` structural handlers and routed through `block_app_handlers`
(`native_blocks/block_app_handlers/feature_app_handlers.py:90`). Those are **event** hooks —
"undo just happened" — and work on every supported version.

`context.window_manager.undo_stack` (5.3+) is a **query** API — "what does undo history contain
right now" (read-only; can't push/pop/rewrite it). The two aren't interchangeable:

| Need | Mechanism | Version |
|---|---|---|
| React when an undo/redo occurs | `undo_pre`/`undo_post` handlers | All (5.0+) |
| Inspect current undo stack contents (e.g. for a debug panel) | `window_manager.undo_stack` | 5.3+ only, no fallback |

If a future block wants to *display* undo history (debug/unit-testing UI is the natural home,
per `block_core/core_helpers/ui.py`), that feature is simply **unavailable** pre-5.3 — this is
the other clean "raise/hide, no fallback" case, same shape as the geonodes modifier RNA change
but lower stakes (a missing debug panel vs. a broken core feature).

---

## Detecting the running version

```python
bpy.app.version          # (5, 3, 0) — tuple, always 3 ints
bpy.app.version >= (5, 3, 0)   # tuple comparison, no helper needed for a single check
```

No DGBlocks helper wraps this today (confirmed — no `version_gate`/`version_compat`/
`min_blender` symbols exist anywhere in `native_blocks`, `addon_helpers`, or `external_blocks`
as of this writing). Every case above is currently a hypothetical branch point, not an existing
one — the pip_library_manager wrap code doesn't check version at all, it just always uses the
old-style manual wrap.

---

## References

- [5.0 Python API release notes](https://developer.blender.org/docs/release_notes/5.0/python_api/)
- [5.1 Python API release notes](https://developer.blender.org/docs/release_notes/5.1/python_api/)
- [5.2 LTS Python API release notes](https://developer.blender.org/docs/release_notes/5.2/python_api/)
- [5.3 Python API release notes](https://developer.blender.org/docs/release_notes/5.3/python_api/)
- [5.3 User Interface release notes](https://developer.blender.org/docs/release_notes/5.3/user_interface/) (`label_multiline`)
- Blender issue tracker: `#160038` (GeoNodes modifier RNA change breaks custom UI layouts using the old custom-prop path), `#157179` (node panel open/close RNA exposure), `#154351` (multiline labels PR)

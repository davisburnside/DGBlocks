# block_mesh_extract

**Block ID:** `block-mesh-extract`

## Purpose

Moves mesh data between Blender and numpy in bulk, in both directions, through an
ordered **step list** of reads, callbacks, and grouping markers. One reusable
**declaration** describes the whole chain. Every run produces a timestamped
`Mesh_Action_Record` so reads, callbacks, and topology edits are tracked identically.

This block is **fully demand-driven**: nothing runs unless a caller invokes it. There
are no hook sources, no app handlers, no data mirrors, and no UIList.

---

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers |

---

## Public API — `Wrapper_Mesh_Extract`

| Method | Returns | Description |
|---|---|---|
| `run_mesh_action_for_object(object, declaration, depsgraph=None, existing_instance=None)` | `RTC_Mesh_Extract_Instance` | Run one declaration's step list against one object |
| `run_mesh_actions_for_object(object, declarations, depsgraph=None)` | `RTC_Mesh_Extract_Instance` | Run several declarations in order on one chained instance; stops on first failure |
| `get_instance(object_name, slot="default", require_valid=True)` | instance \| `None` | Fetch a stored instance |
| `get_all_instances()` | `list` | All stored instances |
| `get_history(object_name, slot="default")` | `list` | Last N completed instances (newest last) for diffs |
| `clear_instances(object_name=None)` | `int` | Drop stored data + history for one object, or all |
| `diff_instances(old, new)` | `(added, removed, edited)` | Key-level comparison of two instances |

`run_mesh_action_for_object` **never raises** for mesh or attribute problems — failures
are recorded on the action. Check `instance.last_action.is_valid` for this call, or
`instance.is_valid` for the latest action.

```python
from ...native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract

instance = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, MY_DECLARATION)
if not instance.is_valid:
    logger.error(instance.error_str)
```

---

## Storage Modes

Storage is chosen **per declaration** with `should_cache_in_RTC`:

| Mode | Setting | Behaviour |
|---|---|---|
| **RTC-cached** | `should_cache_in_RTC = True` (default) | Instance is stored under `(object_name, slot)`, accumulates data + action history across calls, and appears in the debug panel |
| **No storage** | `should_cache_in_RTC = False` | Instance is returned to the caller only; nothing is retained |

History is **independent** of RTC storage and is chosen per declaration with
`history_depth`:

| Setting | Behaviour |
|---|---|
| `history_depth = 0` (default) | No history kept |
| `history_depth = N` | The last N completed instances for `(object_name, slot)` are kept in a deque, retrievable via `get_history()`. Useful for before/after diffs without holding your own snapshot. |

Nothing is ever mirrored into Blender data — every payload is a numpy array, so BL
persistence is not applicable. The debug panel reads the RTC list directly via a looped
draw function.

> **Diffing caveat:** an RTC-cached declaration mutates its stored instance **in place**.
> To diff before/after you must either use `should_cache_in_RTC=False`, hold your own
> snapshot, or use `get_history()` with `history_depth >= 1`.

---

## Instance Identity & Slots

Identity is the pair **`(object_name, slot)`**.

- Multiple actions may target the same object. Same `slot` → they accumulate into one
  instance (pass 1 → pass 2 chaining). Different `slot` → independent instances.
- Latest read wins per attribute slot.
- Overlapping or differing read/callback sets across actions are fine; each action records
  only the ops it actually performed.

---

## Step Types

A declaration is an ordered tuple of steps. Each step is one of:

| Step | Purpose |
|---|---|
| `Read_Step(attr)` | Read one MET attribute into the instance slot (manual refresh) |
| `Callback_Step(func)` | Run a callback that mutates the instance and/or the mesh |
| `Group_Tag(label)` | A named grouping marker for log/UI formatting only — performs no work |

**There is no automatic re-read after a callback.** If a callback changes topology or
attribute values, the developer must add an explicit `Read_Step` afterwards to refresh
the instance slot. This keeps the data flow explicit and predictable.

### Callback contract

```python
def my_callback(instance, action_record, mesh_context) -> None:
    ...
```

- Return values are ignored — the callback **mutates the instance**.
- Per-element results belong in `domain.custom[...]` so they can be written back;
  anything else goes in `instance.derived[...]`.
- `mesh_context` is provided for callbacks that need to write attributes or edit topology
  (see [Mesh_Context](#mesh_context--callback-mesh-access) below).
- A raising callback marks the op and the action invalid; data read before the failure is
  retained. The framework fails gracefully — it never crashes the host.
- Wrap in `Callback_Step(func, label="...")` for a nicer panel label.

---

## Declaration

```python
from ...native_blocks.block_mesh_extract.data_structures import (
    MET, Numpy_Mesh_Action_Declaration, Enum_Read_Source,
    Read_Step, Callback_Step, Group_Tag,
)
from ...native_blocks.block_mesh_extract.builtin_custom_callbacks import _cb_face_face_neighbors

MY_DECLARATION = Numpy_Mesh_Action_Declaration(
    label            = "planarity_pass",
    slot             = "assembly",
    read_source      = Enum_Read_Source.EVALUATED,
    steps            = (
        Group_Tag("topology"),
        Read_Step(MET.VERTEX.CO),
        Read_Step(MET.FACE.NORMAL),
        Read_Step(MET.EDGE.VERTICES),
        Read_Step(MET.FACE.LOOP_START),
        Read_Step(MET.FACE.LOOP_TOTAL),
        Read_Step(MET.CORNER.VERTEX_INDEX),
        Group_Tag("GN attributes"),
        Read_Step(MET.FACE.CUSTOM_ATTRIBUTE("gn_f1")),
        Read_Step(MET.CORNER.UV_MAP()),                     # active UV layer
        Group_Tag("adjacency"),
        Callback_Step(_cb_face_face_neighbors),
        Group_Tag("planarity"),
        Callback_Step(_compute_planarity),
    ),
)
```

| Field | Default | Purpose |
|---|---|---|
| `label` | required | Identifies the action in the panel and logs |
| `slot` | `"default"` | Second half of instance identity |
| `steps` | `()` | Ordered tuple of `Read_Step` / `Callback_Step` / `Group_Tag` |
| `read_source` | `EVALUATED` | `EVALUATED` (post-modifier) or `ORIGINAL` (write-safe) |
| `should_cache_in_RTC` | `True` | Storage mode |
| `history_depth` | `0` | Number of past instances to retain per `(object_name, slot)` |
| `max_actions_retained` | `50` | Per-instance action-log cap; oldest evicted |

Declarations are **object-free** module-level constants — never store a
`bpy.types.Object` on one.

---

## MET — One Vocabulary for Reads and Writes

```python
MET.VERTEX.CO                                        # builtin, writable
MET.VERTEX.NORMAL                                    # builtin, read-only (Blender-computed)
MET.EDGE.SEAM / .SHARP / .CREASE                     # builtin named attributes, writable
MET.FACE.NORMAL / .AREA / .LOOP_START / .LOOP_TOTAL  # read-only
MET.CORNER.VERTEX_INDEX                              # read-only

MET.<DOMAIN>.CUSTOM_ATTRIBUTE("name", data_type="INT")   # data_type needed only to create
MET.CORNER.UV_MAP()                                      # active UV layer, resolved at runtime
MET.CORNER.UV_MAP("UVMap")                               # explicit UV layer
```

Each `MET_Attr_Declaration` is a table-driven descriptor: domain, accessor
(`COLLECTION` vs `NAMED_ATTRIBUTE`), dtype, components, `value_field`, `is_writable`, and
the instance slot it maps to. Read and write helpers both dispatch off this table, so
there is no per-attribute `if/elif` chain anywhere.

Custom attributes (including UV maps) are read the same way as builtins — via
`mesh.attributes[name].data.foreach_get(value_field, buf)`. The dtype/components/value_field
are resolved at read time from the BL attribute's `data_type` when the declaration omits
them.

---

## Instance Data Layout

Data is domain-namespaced instead of prefix-flattened:

```python
instance.vertex.co                        # (n_verts, 3) float32
instance.vertex.count                     # element count
instance.edge.vertices                    # (n_edges, 2) int32
instance.face.normal / .area / .loop_start / .loop_total
instance.corner.vertex_index

instance.face.custom["planar_groups"]     # named / GN / user attributes
instance.face.planar_groups               # sugar (identifier-safe names only)
instance.corner.custom["UV Map"]          # names with spaces: dict access only

instance.derived["face_face_neighbors"]   # non-domain data: CSR tuples, dicts, scalars
```

Domain helpers: `.get(name, default)`, `.has(name)`, `.set_custom(name, value)`,
`.populated_field_names()`.

Instance helpers: `.domain("FACE")`, `.get_attr_value(attr)`, `.set_attr_value(attr, value)`,
`.last_action`, `.total_duration_ms`, `.summary_str()`.

**The instance is a bidirectional staging buffer.** A callback writes its result into the
slot (`domain.custom[...]` or a builtin field) and a later `Read_Step` or
`mesh_context.write_attr()` flushes it.

---

## Mesh_Context — Callback Mesh Access

`mesh_context` is the third argument to every callback. It is bound to **one mesh
acquisition for the whole step list** (minimizing depsgraph evaluations and mesh
creations). It provides:

| Method | Description |
|---|---|
| `write_attr(attr, arr)` | Attempt a validated-free attribute write. Object Mode: `foreach_set` (bulk). Edit Mode: per-element bmesh loop. Raises on failure; the framework catches and records it. |
| `edit_bmesh()` | Return a BMesh for topology edits. Edit Mode: the live `bmesh.from_edit_mesh`. Object Mode: a round-trip `bmesh.new()`/`from_mesh()`. The framework flushes it back after the callback returns. |
| `finalize()` | Called by the framework after each `Callback_Step`. Flushes bmesh mutations to the mesh and frees owned bmeshes. |

**Design philosophy: NO pre-flight validation.** The callback attempts its write or
topology edit; if Blender raises, the exception propagates to the step runner, which
catches it and marks the op (and the action) invalid with the error string. Fail
gracefully, never crash the host.

### Topology edits

A callback may add/remove verts, edges, faces via `mesh_context.edit_bmesh()`. After each
`Callback_Step`, the framework compares domain element counts before/after:

- If counts changed → `instance.topology_generation` is bumped, all per-element slots are
  invalidated (set to `None`), and instance counts are updated to the new reality.
- The developer **must** add an explicit `Read_Step` afterwards to refresh any slots
  needed by subsequent callbacks. The framework does not auto-refresh.

> **EVALUATED + topology edits is at odds** — the evaluated cage is throwaway data and
> won't reflect original-mesh topology changes until re-evaluation. Use
> `read_source=ORIGINAL` for chains that edit topology.

---

## Mesh Acquisition — One Per Action

The mesh is acquired **once per action** for the whole step list, not per step. This is
the key depsgraph-minimization guarantee.

| `read_source` × mode | Object Mode | Edit Mode |
|---|---|---|
| `EVALUATED` | `evaluated_get(dg).to_mesh()` (post-modifier cage; indices may not match original) | same — Blender syncs BMesh→evaluated |
| `ORIGINAL` | `object.data` directly (write-safe indices) | `object.update_from_editmode()` first (bulk BMesh→Mesh copy, **not** a mode switch), then `object.data` |

Only `EVALUATED` produces a temporary mesh that must be released with `to_mesh_clear()`.
For `ORIGINAL` reads it's essentially free (just `object.data` references).

`bmesh.from_edit_mesh()` does not create a new BMesh — it returns the BMesh already
backing Edit Mode. The code never calls `bmesh.new()` for Edit-Mode writes.

---

## Pre-built callbacks (`builtin_custom_callbacks.py`)

| Callback | Stores | Required reads |
|---|---|---|
| `cb_edge_length` | `derived["edge_length"]` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_face_center` | `derived["face_center"]` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_vert_vert_neighbors` | `derived["vert_vert_neighbors"]` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_vert_face_neighbors` | `derived["vert_face_neighbors"]` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `_cb_face_face_neighbors` | `derived["face_face_neighbors"]` | `FACE.NORMAL`, `EDGE.VERTICES`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |

CSR access:
```python
idx, off = instance.derived["face_face_neighbors"]
neighbors_of_face_i = idx[off[i] : off[i+1]]
```

---

## Action Records & Timestamp Ordering

Every call appends a `Mesh_Action_Record`:

| Field | Notes |
|---|---|
| `action_uid` | Monotonic, from the RTC counter |
| `label` | Declaration label |
| `timestamp_start` | Wall clock at action start — **the sort key** |
| `duration_ms` | Total action duration |
| `read_source`, `object_mode` | Provenance of this run |
| `is_valid`, `error_str` | Outcome |
| `ops` | `list[Mesh_Action_Op_Record]` |
| `domain_counts` | `{"VERTEX": 8, "EDGE": 12, ...}` |

`append_action()` keeps `actions` sorted by `(timestamp_start, action_uid)` and evicts the
oldest beyond `max_actions_retained`. Convenience properties: `read_count`,
`write_count`, `callback_count`, `failed_ops`.

Each `Mesh_Action_Op_Record` carries `op_type` (`READ` / `CALLBACK` / `WRITE` / `GROUP`),
`label`, `duration_ms`, `shape`, `is_valid`, `error_str`, and a `detail` string (e.g.
`→ face.custom['planar_groups']`, `bmesh loop, 12 changed`).

`GROUP` ops are emitted by `Group_Tag` steps and rendered as section headers in the debug
panel; subsequent ops are nested under the most recent group until another `Group_Tag`
appears.

---

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_mesh_extract_props.debug_mode_enabled` | `BoolProperty` | Show the instance inspector |
| `...debug_expanded_instance_key` | `StringProperty` | Which instance row is expanded |
| `...debug_max_actions_shown` | `IntProperty` | Actions listed per instance |
| `...debug_show_op_details` | `BoolProperty` | Show per-op breakdown |

Debug/inspection state only — there is nothing to mirror.

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `MESH_EXTRACT_INSTANCES` | `list[RTC_Mesh_Extract_Instance]` | Stored instances, keyed by `(object_name, slot)` |
| `MESH_EXTRACT_HISTORY` | `dict[str, deque[RTC_Mesh_Extract_Instance]]` | History deques, keyed by `"object_name\|slot"` |
| `MESH_ACTION_UID_COUNTER` | `int` | Monotonic `action_uid` source |

---

## Operators

| Operator | Purpose |
|---|---|
| `dgblocks.mesh_extract_toggle_instance` | Expand/collapse an instance row |
| `dgblocks.mesh_extract_clear` | Clear one object's data + history, or everything |

---

## Downstream Integration Example

```python
from ....native_blocks.block_mesh_extract.data_structures import (
    MET, Numpy_Mesh_Action_Declaration, Enum_Read_Source,
    Read_Step, Callback_Step, Group_Tag,
)
from ....native_blocks.block_mesh_extract.builtin_custom_callbacks import _cb_face_face_neighbors
from ....native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract


def _compute_planarity(instance, action_record, mesh_context):
    ffi, ffo = instance.derived["face_face_neighbors"]
    instance.face.custom["planar_groups"] = compute_groups(instance.face.normal, ffi, ffo)


PASS_1 = Numpy_Mesh_Action_Declaration(
    label            = "planarity",
    slot             = "assembly",
    should_cache_in_RTC = False,          # caller keeps the instance, enabling before/after diffs
    history_depth    = 1,                 # keep one past instance for diffing
    steps            = (
        Group_Tag("topology"),
        Read_Step(MET.VERTEX.CO),
        Read_Step(MET.FACE.NORMAL),
        Read_Step(MET.EDGE.VERTICES),
        Read_Step(MET.FACE.LOOP_START),
        Read_Step(MET.FACE.LOOP_TOTAL),
        Read_Step(MET.CORNER.VERTEX_INDEX),
        Group_Tag("adjacency"),
        Callback_Step(_cb_face_face_neighbors),
        Group_Tag("planarity"),
        Callback_Step(_compute_planarity),
    ),
)

instance = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, PASS_1)
if instance.is_valid:
    groups = instance.face.custom["planar_groups"]
```

Chaining a cheap pass 1 into an expensive pass 2 only when data actually changed:

```python
pass_1 = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, PASS_1, depsgraph)
history = Wrapper_Mesh_Extract.get_history(obj.name, "assembly")
previous_snapshot = history[-2] if len(history) >= 2 else None
if previous_snapshot:
    added, removed, edited = Wrapper_Mesh_Extract.diff_instances(previous_snapshot, pass_1)
    if added or removed or edited:
        pass_2 = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, PASS_2, depsgraph, pass_1)
```

---

## `helpers_computed.py` — NJIT Contract

All functions are pure: numpy arrays + scalars in, numpy arrays out. No bpy, no global
state. Each is a direct `@njit` candidate.

```python
def compute_edge_length(vertex_co, edge_vertices):
    return _compute_edge_length_inner(vertex_co, edge_vertices)

# @njit  ← uncomment when ready
def _compute_edge_length_inner(vertex_co, edge_vertices):
    ...
```

---

## Validation

**No pre-flight validation.** Reads, writes, and topology edits all attempt their
operation directly; if Blender raises, the exception is caught and recorded on the op
and action as invalid with a descriptive `error_str`. The framework fails gracefully and
never crashes the host.

The only automatic observation is **topology change detection**: after each
`Callback_Step`, domain element counts are compared before/after. If they differ,
`topology_generation` is bumped and per-element slots are invalidated — but this is an
observation for the record, not a validation gate.

---

## Loggers

| Logger | Usage |
|---|---|
| `MESH_EXTRACT_LIFECYCLE` | Wrapper init/remove, instance store/clear |
| `MESH_EXTRACT_EVENTS` | Per-action results, per-op errors |

---

## Files

```text
block_mesh_extract/
├── __init__.py                  # Block declaration, debug props, operators, panel
├── README.md                    # This file
├── common_declarations.py       # Block_Loggers, Block_RTC_Members
├── data_structures.py           # Enums, MET table, domain namespaces,
│                                # Read_Step / Callback_Step / Group_Tag,
│                                # Numpy_Mesh_Action_Declaration,
│                                # Mesh_Action_Record, Mesh_Action_Op_Record,
│                                # RTC_Mesh_Extract_Instance
├── helpers_actions.py           # step-list runner, RTC instance store, history
├── helpers_read.py              # Table-driven foreach_get, attribute resolution
├── helpers_write.py             # Mesh_Context (callback mesh access), bmesh paths
├── helpers_diff.py              # diff_instances over domains + custom + derived
├── helpers_computed.py          # Pure numpy functions (NJIT-ready)
├── builtin_custom_callbacks.py  # cb_edge_length, cb_face_center, cb_*_neighbors
└── ui.py                        # ui_draw_mesh_extract_instances (looped draw, no UIList)
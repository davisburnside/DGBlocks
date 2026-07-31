# block_mesh_extract

**Block ID:** `block-mesh-extract`

## Purpose

Moves mesh data between Blender and numpy in bulk, in both directions:

- **READ** — `foreach_get` from an evaluated or original mesh into a domain-namespaced
  numpy record.
- **CALLBACKS** — pure numpy work that mutates that record in place.
- **WRITE** — `foreach_set` (or a bmesh loop in Edit Mode) back into builtin attributes,
  named/custom attributes, or UV maps.

One reusable **action declaration** describes all three phases. Every run produces a
timestamped `Mesh_Action_Record` so reads and writes are tracked identically.

This block is **fully demand-driven**: nothing runs unless a caller invokes it. There are
no hook sources, no app handlers, no data mirrors, and no UIList.

---

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers |

---

## Public API — `Wrapper_Mesh_Extract`

| Method | Returns | Description |
|---|---|---|
| `run_mesh_action_for_object(object, declaration, depsgraph=None, existing_instance=None)` | `RTC_Mesh_Extract_Instance` | Run one declaration against one object |
| `run_mesh_actions_for_object(object, declarations, depsgraph=None)` | `RTC_Mesh_Extract_Instance` | Run several declarations in order on one chained instance; stops on first failure |
| `get_instance(object_name, slot="default", require_valid=True)` | instance \| `None` | Fetch a stored instance |
| `get_all_instances()` | `list` | All stored instances |
| `clear_instances(object_name=None)` | `int` | Drop stored data for one object, or all |
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

Nothing is ever mirrored into Blender data — every payload is a numpy array, so BL
persistence is not applicable. The debug panel reads the RTC list directly via a looped
draw function.

> **Diffing caveat:** an RTC-cached declaration mutates its stored instance **in place**.
> To diff before/after you must either use `should_cache_in_RTC=False` or hold your own
> snapshot of the previous instance.

---

## Instance Identity & Slots

Identity is the pair **`(object_name, slot)`**.

- Multiple actions may target the same object. Same `slot` → they accumulate into one
  instance (pass 1 → pass 2 chaining). Different `slot` → independent instances.
- Latest read wins per attribute slot.
- Overlapping or differing read/write sets across actions are fine; each action records
  only the ops it actually performed.

---

## Action Declaration

```python
from ...native_blocks.block_mesh_extract.data_structures import (
    MET, Numpy_Mesh_Action_Declaration, Enum_Read_Source, Callback_Op, Write_Op,
)

MY_DECLARATION = Numpy_Mesh_Action_Declaration(
    label            = "planarity_pass_1",
    slot             = "assembly",
    read_source      = Enum_Read_Source.EVALUATED,
    read_attributes  = (
        MET.VERTEX.CO,
        MET.FACE.NORMAL,
        MET.FACE.LOOP_START,
        MET.FACE.LOOP_TOTAL,
        MET.EDGE.VERTICES,
        MET.CORNER.VERTEX_INDEX,
        MET.FACE.CUSTOM_ATTRIBUTE("gn_f1"),
        MET.CORNER.UV_MAP(),                     # active UV layer
    ),
    callbacks        = (
        _cb_face_face_neighbors,
+                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           Callback_Op(_compute_planarity, label="planarity"),
    ),
    write_attributes = (
        MET.FACE.CUSTOM_ATTRIBUTE("planar_groups", data_type="INT"),
    ),
)
```

| Field | Default | Purpose |
|---|---|---|
| `label` | required | Identifies the action in the panel and logs |
| `slot` | `"default"` | Second half of instance identity |
| `read_attributes` | `()` | Ordered MET attrs to read |
| `callbacks` | `()` | Ordered callables / `Callback_Op` |
| `write_attributes` | `()` | Ordered MET attrs / `Write_Op` to flush |
| `read_source` | `EVALUATED` | `EVALUATED` (post-modifier) or `ORIGINAL` (write-safe) |
| `should_cache_in_RTC` | `True` | Storage mode |
| `allow_evaluated_index_space` | `False` | Required to combine writes with `EVALUATED` reads |
| `edit_mode_write_strategy` | `BMESH_LOOP` | Or `REJECT` to refuse Edit-Mode writes |
| `on_type_mismatch` | `ERROR` | Or `RECREATE` an existing attribute with the wrong domain/type |
| `diff_limited_writes` | `True` | Only touch elements whose value actually changed |
| `should_push_undo` | `False` | Push an undo step after a successful write |
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

**The instance is a bidirectional staging buffer.** A write with no explicit payload
flushes whatever currently sits at that attribute's slot — so a callback writes its
result into the slot and the WRITE phase picks it up. Use `Write_Op(attr, payload=arr)`
for a one-shot write that skips staging.

---

## Callbacks

```python
def _compute_planarity(instance, action_record):
    ffi, ffo = instance.derived["face_face_neighbors"]
    instance.face.custom["planar_groups"] = compute_groups(instance.face.normal, ffi, ffo)
    instance.derived["planar_group_boundary_edges"] = boundaries
```

- Signature: `func(instance, action_record) -> None`. Return values are ignored — the
  callback **mutates the instance**.
- Per-element results belong in `domain.custom[...]` so they can be written back;
  anything else goes in `instance.derived[...]`.
- Wrap in `Callback_Op(func, label="...")` for a nicer panel label.
- A raising callback marks the op and the action invalid; data read before the failure is
  retained.

### Pre-built callbacks (`builtin_custom_callbacks.py`)

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

## Writing to Meshes — Rules & Pitfalls

Writes are the risky half of the block. The guardrails:

| Concern | Rule |
|---|---|
| **Index space** | `EVALUATED` reads come from the post-modifier cage; those indices may not match the original mesh. Writing after an `EVALUATED` read requires `allow_evaluated_index_space=True` as an explicit acknowledgement. Prefer `read_source=ORIGINAL` for read-modify-write. |
| **Write target** | Writes always go to the **original** mesh (`object.data`). The evaluated cage is throwaway data. |
| **Length mismatch** | Payload length must equal `domain_count × components`. Mismatches fail the op, never truncate. |
| **Read-only attrs** | `is_writable=False` (normals, areas, loop_start/total, edge vertices, corner vertex_index) are rejected — these are Blender-computed or topology. |
| **Reserved names** | `position`, `id`, `material_index` are refused as custom-attribute targets. |
| **Type mismatch** | An existing attribute with a different domain/data_type raises under `ERROR`, or is deleted and recreated under `RECREATE`. |
| **Creating attributes** | Requires `data_type` on the MET declaration; otherwise the op fails with a clear message. |
| **Edit Mode** | `foreach_set` does not reach the BMesh. `BMESH_LOOP` writes through a per-element Python loop (slow, correct); `REJECT` fails fast instead of paying the cost. |
| **Diff-limited writes** | With `diff_limited_writes=True` the current mesh values are read first and the write is skipped entirely when nothing changed — avoids needless depsgraph churn. |
| **Depsgraph feedback** | A write triggers a depsgraph update. If your caller runs from a `depsgraph_update_post` handler, guard against re-entry (a re-entrancy flag or handler disable around the call). |
| **Topology** | This block writes **attribute values only** — it never adds or removes elements. `topology_generation` bumps if element counts change underneath, invalidating cached index-space data. New geometry must be built with bmesh by the caller. |
| **Undo** | `should_push_undo=True` pushes an undo step after a successful write. Off by default — high-frequency writes should not spam the undo stack. |

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

Each `Mesh_Action_Op_Record` carries `op_type` (`READ` / `CALLBACK` / `WRITE`), `label`,
`duration_ms`, `shape`, `is_valid`, `error_str`, and a `detail` string (e.g.
`→ face.custom['planar_groups']`, `bmesh loop, 12 changed`).

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
| `MESH_ACTION_UID_COUNTER` | `int` | Monotonic `action_uid` source |

---

## Operators

| Operator | Purpose |
|---|---|
| `dgblocks.mesh_extract_toggle_instance` | Expand/collapse an instance row |
| `dgblocks.mesh_extract_clear` | Clear one object's data, or everything |

---

## Downstream Integration Example

```python
from ....native_blocks.block_mesh_extract.data_structures import (
    MET, Numpy_Mesh_Action_Declaration, Enum_Read_Source,
)
from ....native_blocks.block_mesh_extract.builtin_custom_callbacks import _cb_face_face_neighbors
from ....native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract


def _compute_planarity(instance, action_record):
    ffi, ffo = instance.derived["face_face_neighbors"]
    instance.face.custom["planar_groups"] = compute_groups(instance.face.normal, ffi, ffo)


PASS_1 = Numpy_Mesh_Action_Declaration(
    label            = "planarity",
    slot             = "assembly",
    should_cache_in_RTC = False,          # caller keeps the instance, enabling before/after diffs
    read_attributes  = (MET.VERTEX.CO, MET.FACE.NORMAL, MET.EDGE.VERTICES,
                        MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX),
    callbacks        = (_cb_face_face_neighbors, _compute_planarity),
)

instance = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, PASS_1)
if instance.is_valid:
    groups = instance.face.custom["planar_groups"]
```

Chaining a cheap pass 1 into an expensive pass 2 only when data actually changed:

```python
pass_1 = Wrapper_Mesh_Extract.run_mesh_action_for_object(obj, PASS_1, depsgraph)
added, removed, edited = Wrapper_Mesh_Extract.diff_instances(pass_1, previous_snapshot)
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

No pre-flight validation of callback inputs. A callback that touches an array which was
never read raises at runtime; the op and action are marked invalid, `error_str` is
populated, and the failure is shown in the panel. Write-phase validation (writability,
reserved names, length, type mismatch) **is** performed and fails the op with a
descriptive message.

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
│                                # Numpy_Mesh_Action_Declaration, Callback_Op, Write_Op,
│                                # Mesh_Action_Record, Mesh_Action_Op_Record,
│                                # RTC_Mesh_Extract_Instance
├── helpers_actions.py           # run_mesh_action orchestration, RTC instance store
├── helpers_read.py              # Table-driven foreach_get, attribute resolution
├── helpers_write.py             # Table-driven foreach_set, bmesh Edit-Mode path,
│                                # attribute creation, diff-limited writes
├── helpers_diff.py              # diff_instances over domains + custom + derived
├── helpers_computed.py          # Pure numpy functions (NJIT-ready)
├── builtin_custom_callbacks.py  # cb_edge_length, cb_face_center, cb_*_neighbors
└── ui.py                        # ui_draw_mesh_extract_instances (looped draw, no UIList)
```

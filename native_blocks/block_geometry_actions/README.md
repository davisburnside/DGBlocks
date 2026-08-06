# block_geometry_actions

**Block ID:** `block-geometry-actions`
*(formerly `block_geometry_actions` / `block-mesh-extract`)*

## Purpose

Moves geometry data between Blender and numpy in bulk, in both directions, through an
ordered **step list** of reads, callbacks, and grouping markers. One reusable
**declaration** describes the whole chain. Every run produces a timestamped
`Action_Record`, so reads, callbacks, writes and topology edits are all tracked
identically.

Works on **meshes and curves**. Curve objects can either be read through their evaluated
mesh (the old behaviour) or through their own point/curve domains — the declaration
chooses.

This block is **fully demand-driven**: nothing runs unless a caller invokes it. There are
no hook sources, no app handlers, no data mirrors, and no UIList.

---

## What changed from `block_geometry_actions`

| Area | Before | Now |
|---|---|---|
| Name | `block_geometry_actions` / `Wrapper_Geometry_Actions` | `block_geometry_actions` / `Wrapper_Geometry_Actions` |
| Identity | `(object_name, slot)`, mutated in place | `(declaration_id, object_name)` → an immutable-per-run **stack** |
| Retention | `should_cache_in_RTC` + `history_depth` (two overlapping knobs) | one `retention_count` on the declaration (default `1`) |
| Run semantics | reused/mutated the stored instance | every run is a **new result**, pushed onto the stack |
| Timestamps | on the action only | on the action **and** the result (`timestamp_start` / `timestamp_end`) |
| Geometry | meshes only (curves via mesh eval) | meshes + native curve points/splines, via `geometry_target` |
| Step dispatch | `isinstance()` (broke on module reload) | `step_kind` field — reload-proof |
| Op records | had a `detail` string | removed (redundant) |
| UI | "Stored data" box, Detail column, "GN Attributes" | removed / renamed to "Named Attributes"; every level collapsible |
| Debug panel | drew an empty shell when debug was off | `poll()` hides the panel entirely |
| Serialization | — | builtin serialize/deserialize callbacks for socket transport |
| Tests | — | `tests/` folder with a headless-capable unittest suite |

---

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers |

---

## Public API — `Wrapper_Geometry_Actions`

| Method | Returns | Description |
|---|---|---|
| `run_geometry_action_for_object(object, declaration, depsgraph=None, existing_instance=None)` | result | Run one declaration's step list against one object |
| `run_geometry_actions_for_object(object, declarations, depsgraph=None)` | result | Run several declarations on one chained result; stops on first failure |
| `get_result(declaration_id, object_name, offset_from_latest=0, require_valid=True)` | result \| `None` | Fetch a stored result. `0` = newest, `1` = previous, ... |
| `get_result_stack(declaration_id, object_name)` | `list` | Every retained result for that pair, oldest first |
| `get_all_results()` | `list` | Flat list of every retained result |
| `clear_results(declaration_id=None, object_name=None)` | `int` | Drop by declaration, by object, by both, or all |
| `diff_results(old, new)` | `(added, removed, edited)` | Key-level comparison of two results |
| `serialize_object_geometry(object)` | `str` | Serialize a datablock outside the step-list flow |
| `apply_serialized_geometry_to_object(object, serialized)` | `str` | Replace a datablock from a transport string |
| `inspect_serialized_geometry(serialized)` | `dict` | Decode only the payload header |

`run_geometry_action_for_object` **never raises** for geometry or attribute problems —
failures are recorded on the action. Check `result.last_action.is_valid` for this call, or
`result.is_valid` for the latest action. The serialization helpers **do** raise, by design.

```python
from ...native_blocks.block_geometry_actions.feature_geometry_actions import Wrapper_Geometry_Actions

result = Wrapper_Geometry_Actions.run_geometry_action_for_object(obj, MY_DECLARATION)
if not result.is_valid:
    logger.error(result.error_str)
```

---

## Identity & Retention

Identity is the pair **`(declaration_id, object_name)`**.

- `declaration_id` is **required** and must be unique per logical action.
- Two different declaration objects sharing an id land in the **same stack**, regardless of
  their contents. The assumption is that they populate the same attribute fields, possibly
  with differing data or element counts.
- Every run creates a **new result instance** and pushes it onto that stack. Nothing is
  mutated in place, so a before/after diff is always available.

| `retention_count` | Behaviour |
|---|---|
| `0` | Nothing stored; the result is returned to the caller only |
| `1` (default) | Only the newest result is kept |
| `N` | The newest N results are kept — `get_result(id, name, 1)` vs `get_result(id, name, 0)` is a ready-made before/after pair |

Lowering `retention_count` on a later run truncates the stack to the new depth.

Nothing is ever mirrored into Blender data — every payload is a numpy array.

---

## Step Types

A declaration is an ordered tuple of steps:

| Step | Purpose |
|---|---|
| `Read_Step(attr)` | Read one attribute into the result slot |
| `Callback_Step(func, label=None)` | Run a callback that mutates the result and/or the geometry |
| `Group_Tag(label)` | A named grouping marker for log/UI structure — performs no work |

Steps carry a `step_kind` field, and the runner dispatches on **that**, not `isinstance()`.
This is deliberate: Blender addon reloads can produce two distinct copies of the same
dataclass, which silently broke `isinstance()` dispatch before.

**There is no automatic re-read after a callback.** If a callback changes topology or
attribute values, add an explicit `Read_Step` afterwards.

### Callback contract

```python
def my_callback(instance, action_record, geometry_context) -> None:
    ...
```

- Return values are ignored — the callback **mutates the instance**.
- Per-element results belong in `domain.custom[...]` so they can be written back; anything
  else goes in `instance.derived[...]`.
- `geometry_context` is how a callback writes attributes or edits topology.
- A raising callback marks the op and the action invalid; data read before the failure is
  retained. The framework never crashes the host.

---

## Declaration

```python
from ...native_blocks.block_geometry_actions.data_structures import (
    MET, CET, Geometry_Actions_Declaration, Enum_Read_Source, Enum_Geometry_Target,
    Read_Step, Callback_Step, Group_Tag,
)
from ...native_blocks.block_geometry_actions.builtin_custom_callbacks import cb_face_face_neighbors

MY_DECLARATION = Geometry_Actions_Declaration(
    declaration_id  = "flatypus.assembly.planarity",
    label           = "planarity pass",
    read_source     = Enum_Read_Source.EVALUATED,
    geometry_target = Enum_Geometry_Target.AUTO,
    retention_count = 2,
    steps           = (
        Group_Tag("topology"),
        Read_Step(MET.VERTEX.CO),
        Read_Step(MET.FACE.NORMAL),
        Read_Step(MET.EDGE.VERTICES),
        Read_Step(MET.FACE.LOOP_START),
        Read_Step(MET.FACE.LOOP_TOTAL),
        Read_Step(MET.CORNER.VERTEX_INDEX),
        Group_Tag("named attributes"),
        Read_Step(MET.FACE.CUSTOM_ATTRIBUTE("gn_f1")),
        Read_Step(MET.CORNER.UV_MAP()),                 # active UV layer
        Group_Tag("adjacency"),
        Callback_Step(cb_face_face_neighbors),
        Group_Tag("planarity"),
        Callback_Step(_compute_planarity),
    ),
)
```

| Field | Default | Purpose |
|---|---|---|
| `declaration_id` | **required** | Stack identity; unique per logical action |
| `label` | `""` (falls back to the id) | Display name in the panel and logs |
| `steps` | `()` | Ordered tuple of `Read_Step` / `Callback_Step` / `Group_Tag` |
| `read_source` | `EVALUATED` | `EVALUATED` (post-modifier) or `ORIGINAL` (write-safe) |
| `geometry_target` | `AUTO` | `AUTO` / `MESH_EVALUATED` / `NATIVE_DATA` — see below |
| `retention_count` | `1` | Stack depth |
| `max_actions_retained` | `50` | Per-result action-log cap; oldest evicted |

Declarations are **object-free** module-level constants — never store a `bpy.types.Object`
on one.

---

## Curves — `geometry_target`

Curve objects support the same actions as meshes wherever the operation is meaningful. The
declaration decides what "the geometry" means:

| `geometry_target` | Mesh object | Curve object |
|---|---|---|
| `AUTO` (default) | the mesh | the object's own point/curve domains, falling back to the evaluated mesh when the curve type has no native attribute API |
| `MESH_EVALUATED` | the mesh | `to_mesh()` result — read-only, mesh domains, MET attributes |
| `NATIVE_DATA` | the mesh | the `Curves` datablock — `POINT` / `CURVE` domains, CET attributes, writable |

`NATIVE_DATA` on a legacy `bpy.types.Curve` (Bezier/NURBS `CURVE` object) is rejected with
a clear error: only `Curves` datablocks expose `.attributes`. Use `MESH_EVALUATED` for
legacy curves, or convert.

The result's `geometry_type` field records what was actually operated on
(`MESH` / `CURVES`), and so does every action record.

---

## Attribute Vocabularies — MET and CET

```python
# MET — mesh
MET.VERTEX.CO / .NORMAL / .CREASE / .BEVEL_WEIGHT
MET.EDGE.VERTICES / .SEAM / .SHARP / .CREASE
MET.FACE.NORMAL / .AREA / .LOOP_START / .LOOP_TOTAL
MET.CORNER.VERTEX_INDEX
MET.<DOMAIN>.CUSTOM_ATTRIBUTE("name", data_type="INT")
MET.CORNER.UV_MAP()            # active UV layer, resolved at runtime

# CET — curves
CET.POINT.POSITION / .RADIUS / .TILT
CET.CURVE.CURVE_TYPE / .CYCLIC / .RESOLUTION / .POINTS_LENGTH / .FIRST_POINT_INDEX
CET.<DOMAIN>.CUSTOM_ATTRIBUTE("name", data_type="FLOAT")
```

Both produce the same `Attr_Declaration` dataclass: domain, accessor (`COLLECTION` vs
`NAMED_ATTRIBUTE`), dtype, components, `value_field`, `is_writable`, and the result slot it
maps to. Read and write helpers dispatch off this table, so there is no per-attribute
`if/elif` chain anywhere.

`CET.CURVE.POINTS_LENGTH` / `FIRST_POINT_INDEX` are derived from `curves.curve_offsets` —
they give you the CSR-style slice of each spline's points:

```python
start = instance.curve.first_point_index[i]
count = instance.curve.points_length[i]
spline_positions = instance.point.position[start : start + count]
```

---

## Result Data Layout

```python
result.declaration_id / .object_name / .geometry_type
result.timestamp_start / .timestamp_end

# mesh domains
result.vertex.co                        result.vertex.count
result.edge.vertices
result.face.normal / .area / .loop_start / .loop_total
result.corner.vertex_index

# curve domains
result.point.position / .radius / .tilt
result.curve.curve_type / .cyclic / .points_length / .first_point_index

result.face.custom["planar_groups"]     # named / GN / user attributes
result.face.planar_groups               # sugar (identifier-safe names only)
result.corner.custom["UV Map"]          # names with spaces: dict access only

result.derived["face_face_neighbors"]   # non-domain data: CSR tuples, dicts, strings
```

Domain helpers: `.get(name, default)`, `.has(name)`, `.set_custom(name, value)`,
`.populated_field_names()`.
Result helpers: `.domain("FACE")`, `.get_attr_value(attr)`, `.set_attr_value(attr, value)`,
`.domain_names`, `.last_action`, `.total_duration_ms`, `.summary_str()`.

**The result is a bidirectional staging buffer.** A callback writes its result into the
slot and a later `Read_Step` or `geometry_context.write_attr()` flushes it.

---

## Geometry_Context — Callback Access

`geometry_context` is the third argument to every callback. It is bound to **one geometry
acquisition for the whole step list** (minimizing depsgraph evaluations).

| Member | Description |
|---|---|
| `data` | The datablock being operated on (`Mesh` or `Curves`) |
| `geometry_type` | `MESH` / `CURVES` |
| `is_edit_mode` | Whether the object is in Edit Mode |
| `write_attr(attr, arr)` | Attempt an attribute write. Object Mode: `foreach_set`. Edit Mode (mesh): per-element bmesh loop. Raises on failure; the framework records it |
| `edit_bmesh()` | BMesh for mesh topology edits. Mesh-only — raises for curves |
| `finalize()` | Called by the framework after each `Callback_Step` |

**No pre-flight validation.** The callback attempts its write; if Blender raises, the
exception propagates to the step runner, which marks the op invalid with the error string.

### Topology edits

After each `Callback_Step` the framework compares domain element counts. If they changed,
`topology_generation` is bumped, all per-element slots are invalidated, and counts are
refreshed. Add an explicit `Read_Step` afterwards to repopulate what you need.

> `EVALUATED` + topology edits is at odds — the evaluated cage is throwaway data. Use
> `read_source=ORIGINAL` for chains that edit topology.

---

## Geometry Acquisition Matrix

| | Object Mode | Edit Mode |
|---|---|---|
| `EVALUATED` | `evaluated_get(dg).to_mesh()` — post-modifier cage, indices may not match original | same; Blender syncs BMesh→evaluated |
| `ORIGINAL`, mesh | `object.data` (write-safe indices) | `object.update_from_editmode()` first (bulk copy, **not** a mode switch), then `object.data` |
| `ORIGINAL`, curves + `NATIVE_DATA` | `object.data` (the `Curves` datablock) | same — curve Edit Mode writes go straight to the datablock |

Only `EVALUATED` produces a temporary mesh that must be released with `to_mesh_clear()`.

---

## Serialization (socket transport)

Two builtin callbacks turn a datablock into a portable string and back, so two machines
can keep each other's geometry in sync over a socket. **The socket/server layer is out of
scope for this block** — it only provides the payload.

| Callback | Direction | Behaviour |
|---|---|---|
| `cb_serialize_geometry` | out | Serializes topology + every named attribute → `instance.derived["serialized_geometry"]` |
| `cb_deserialize_geometry` | in | Reads `instance.derived["serialized_geometry"]` and **replaces** the object's geometry, custom attributes included |

Payload format: a `zlib`-compressed, base64-encoded blob whose first section is a JSON
header (format version, geometry type, element counts, topology + attribute inventory with
dtype/shape) followed by the raw little-endian array bytes. Compact and self-describing.

Both raise on invalid input — unsupported attribute data types, malformed/truncated
payloads, a header/array mismatch, a wrong-geometry-type payload, Edit Mode, or a missing
payload. Deserialization requires Object Mode and `read_source=ORIGINAL`.

```python
# machine A
SEND = Geometry_Actions_Declaration(
    declaration_id = "net.send",
    read_source    = Enum_Read_Source.ORIGINAL,
    steps          = (Callback_Step(cb_serialize_geometry),),
)
payload = Wrapper_Geometry_Actions.run_geometry_action_for_object(obj, SEND) \
              .derived["serialized_geometry"]
socket.send(payload)

# machine B
Wrapper_Geometry_Actions.apply_serialized_geometry_to_object(obj, socket.recv())
```

---

## Pre-built callbacks (`builtin_custom_callbacks.py`)

| Callback | Stores | Required reads |
|---|---|---|
| `cb_edge_length` | `edge.custom["edge_length"]` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_face_center` | `face.custom["face_center"]` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_vert_vert_neighbors` | `derived["vert_vert_neighbors"]` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_vert_face_neighbors` | `derived["vert_face_neighbors"]` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_face_face_neighbors` | `derived["face_face_neighbors"]` | `EDGE.VERTICES`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_serialize_geometry` | `derived["serialized_geometry"]` | none |
| `cb_deserialize_geometry` | replaces the geometry | `derived["serialized_geometry"]` must be staged |

CSR access:
```python
idx, off = result.derived["face_face_neighbors"]
neighbors_of_face_i = idx[off[i] : off[i+1]]
```

---

## Action Records

Every call appends an `Action_Record` to the result:

| Field | Notes |
|---|---|
| `action_uid` | Monotonic, from the RTC counter |
| `declaration_id`, `label` | Which declaration ran |
| `timestamp_start` | Wall clock at action start — **the sort key** |
| `duration_ms` | Total action duration |
| `read_source`, `geometry_target`, `geometry_type`, `object_mode` | Provenance |
| `is_valid`, `error_str` | Outcome |
| `ops` | `list[Action_Op_Record]` |
| `domain_counts` | `{"VERTEX": 8, ...}` or `{"POINT": 3, "CURVE": 1}` |

`Action_Op_Record` carries `op_type` (`READ` / `CALLBACK` / `WRITE` / `GROUP`), `label`,
`duration_ms`, `shape`, `is_valid`, `error_str`. The old `detail` string is gone — it
duplicated what the label and shape already said.

---

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_geometry_actions_props.debug_expanded_keys` | `StringProperty` | CSV of expanded panel keys — enables collapsing at every depth |
| `...debug_max_actions_shown` | `IntProperty` | Passes listed per stored result |

Debug/inspection state only — there is nothing to mirror.

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `GEOMETRY_ACTION_STACKS` | `dict[str, deque[result]]` | Result stacks, keyed by `"declaration_id\|object_name"` |
| `GEOMETRY_ACTION_UID_COUNTER` | `int` | Monotonic `action_uid` source |

---

## UI

The debug panel is a **helper only**, gated on the block's `debug_mode_enabled` flag
(toggled in core's All Blocks UIList). `poll()` reads it through the shared
`addon_helpers.generic_tools.is_block_debug_mode_enabled(block_id)` helper, which resolves
the block record by id — no hard-coded `managed_blocks[N]` index — so the panel disappears
entirely when debug mode is off.

Because Blender sub-panels (`bl_parent_id`) cannot be generated per runtime record, every
level in the panel is a box + `TRIA` toggle backed by one CSV property of expanded keys.
That makes result stacks, individual passes, and op groups independently collapsible at any
depth.

Removed in this rework: the "Stored Data" inventory box (large, low value), the per-op
"Detail" column, and the "GN Attributes" naming (attributes come from anywhere, so groups
are now labelled "named attributes").

| Operator | Purpose |
|---|---|
| `dgblocks.geometry_actions_toggle_expanded` | Expand/collapse any section |
| `dgblocks.geometry_actions_clear` | Clear one stack, one declaration, one object, or everything |

---

## Tests

```text
tests/
├── run_tests.py               # single entry point (interactive + headless)
├── test_helpers.py            # geometry factory + prefix-scoped cleanup
└── test_geometry_actions.py   # the suite
```

Interactive:
```python
from DGBlocks.native_blocks.block_geometry_actions.tests import run_tests
run_tests.run()
```

Headless:
```bash
blender --background --python native_blocks/block_geometry_actions/tests/run_tests.py
```

Coverage: builtin + custom reads, a graceful missing-attribute read, computed callback +
write-back, a raising callback, retention (`0` / `1` / `N` with a real before/after diff),
native curve reads and curve attribute round-trip, and serialization round-trip +
malformed-payload rejection. Every test builds its own geometry under the `DGB_TEST_`
prefix and removes it in `tearDown`, so the suite is safe in a live user session.

---

## `helpers_computed.py` — NJIT Contract

All functions are pure: numpy arrays + scalars in, numpy arrays out. No bpy, no global
state. Each is a direct `@njit` candidate.

---

## Loggers

| Logger | Usage |
|---|---|
| `GEOMETRY_ACTIONS_LIFECYCLE` | Wrapper init/remove, stack store/clear |
| `GEOMETRY_ACTIONS_EVENTS` | Per-action results, per-op errors |

---

## Files

```text
block_geometry_actions/
├── __init__.py                  # Block declaration, debug props, operators, panel
├── README.md                    # This file
├── common_declarations.py       # Block_Loggers, Block_RTC_Members
├── data_structures.py           # Enums, MET + CET tables, domain namespaces,
│                                # Read_Step / Callback_Step / Group_Tag (step_kind),
│                                # Geometry_Actions_Declaration,
│                                # Action_Record, Action_Op_Record,
│                                # Geometry_Actions_Result_Instance
├── feature_geometry_actions.py  # Wrapper_Geometry_Actions (public API)
├── helpers_actions.py           # step-list runner, retention stacks
├── helpers_read.py              # geometry acquisition, table-driven foreach_get
├── helpers_write.py             # Geometry_Context, bmesh paths
├── helpers_serialize.py         # serialize / deserialize payload codec
├── helpers_diff.py              # diff over domains + custom + derived
├── helpers_computed.py          # Pure numpy functions (NJIT-ready)
├── builtin_custom_callbacks.py  # computed, adjacency, serialize/deserialize callbacks
├── ui.py                        # collapsible looped draw, no UIList
└── tests/                       # unittest suite (interactive + headless)
```

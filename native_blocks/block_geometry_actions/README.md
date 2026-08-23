# block_geometry_actions

**Block ID:** `block-geometry-actions`

## Purpose

Moves geometry data between Blender and numpy through ordered read and callback steps.
Every run produces one timed action record, and the latest result for each action ID/object
is available through the runtime cache and debug panel. Meshes and native curves are
supported.

This block is demand-driven: nothing runs unless a caller invokes it. It has no hook
sources, app handlers, data mirrors, or UIList. Downstream blocks own redraw scheduling.

## Public API

| Method | Description |
|---|---|
| `run_geometry_action_for_object(object, declaration, depsgraph=None)` | Run one declaration |
| `run_geometry_actions_for_object(object, declarations, depsgraph=None)` | Run declarations in order |
| `get_result(declaration_id, object_name, require_valid=True)` | Fetch the latest stored result |
| `get_all_results()` | Return all latest stored results |
| `clear_results(declaration_id=None, object_name=None)` | Clear matching results or everything |
| `diff_results(old, new)` | Compare two caller-retained results |
| `serialize_object_geometry(object)` | Serialize geometry to a transport string |
| `apply_serialized_geometry_to_object(object, serialized)` | Apply serialized geometry |
| `inspect_serialized_geometry(serialized)` | Decode the payload header |

Geometry/read/callback failures are recorded rather than raised. Inspect
`result.last_action.is_valid` and `result.error_str`. Serialization convenience methods
raise on invalid input by design.

## Identity and Storage

Every declaration requires a `declaration_id`. Stored identity is:

```text
(declaration_id, object.session_uid)
```

All distinct action IDs are stored implicitly. Running the same ID again on the same
object replaces its previous result. There is no retention depth or internal history
stack. Every run still receives a monotonic `action_uid`, used as its displayed run number.

Object names are retained for display and public lookup. Session UID is used internally so
index-space data cannot be confused between different objects that reuse a name.

Callers needing a before/after diff retain the earlier returned result themselves.

## Grouping IDs

`grouping_id` is optional and joins action IDs into an object-scoped data pipeline. Before
a grouped action runs, the framework finds the latest result with the same grouping ID and
object session UID and deep-copies its payload into the new result.

Inherited data includes domain arrays, custom attributes, `derived`, counts, and topology
generation. Action records are not inherited.

- A successful `Read_Step` replaces its inherited attribute slot.
- A failed read records the error and leaves an inherited slot unchanged.
- Callbacks can consume inherited domain and derived data.
- Arrays and containers are copied, not shared with the earlier stored result.
- Grouping never crosses objects.

```python
READ = Geometry_Actions_Declaration(
    declaration_id="assembly.read",
    grouping_id="assembly.pipeline",
    steps=(Read_Step(MET.VERTEX.CO),),
)

COMPUTE = Geometry_Actions_Declaration(
    declaration_id="assembly.compute",
    grouping_id="assembly.pipeline",
    steps=(Callback_Step(compute_from_inherited_vertices),),
)
```

## Step Types

| Step | Purpose |
|---|---|
| `Read_Step(attr)` | Read one geometry attribute into its result slot |
| `Callback_Step(func, label=None)` | Mutate the result and/or geometry |

Steps dispatch through `step_kind` instead of `isinstance()`, which remains reliable after
Blender addon reloads. There is no automatic re-read after a callback; add an explicit
`Read_Step` when changed values must be refreshed.

Callback signature:

```python
def callback(instance, action_record, geometry_context) -> None:
    ...
```

Return values are ignored. Per-element output belongs in a domain slot or
`domain.custom[...]`; non-domain output belongs in `instance.derived[...]`.

## Declaration

```python
MY_DECLARATION = Geometry_Actions_Declaration(
    declaration_id="example.planarity",
    grouping_id="example.analysis",
    label="Compute planarity",
    read_source=Enum_Read_Source.EVALUATED,
    geometry_target=Enum_Geometry_Target.AUTO,
    steps=(
        Read_Step(MET.VERTEX.CO),
        Read_Step(MET.FACE.NORMAL),
        Callback_Step(compute_planarity, label="Planarity"),
    ),
)
```

| Field | Default | Purpose |
|---|---|---|
| `declaration_id` | required | Stored action identity |
| `grouping_id` | `None` | Optional object-scoped inheritance pipeline |
| `label` | action ID | UI/log label |
| `steps` | `()` | Ordered reads and callbacks |
| `read_source` | `EVALUATED` | Evaluated or original geometry |
| `geometry_target` | `AUTO` | `AUTO`, `MESH_EVALUATED`, or `NATIVE_DATA` |

Declarations are object-free module-level constants. Never cache a Blender ID on one.

## Result Data

```python
result.declaration_id
result.grouping_id
result.object_name
result.object_session_uid
result.vertex.co
result.edge.vertices
result.face.normal
result.corner.vertex_index
result.point.position
result.curve.curve_type
result.face.custom["planar_groups"]
result.derived["face_face_neighbors"]
```

Result helpers include `.domain()`, `.get_attr_value()`, `.set_attr_value()`,
`.last_action`, `.total_duration_ms`, and `.summary_str()`.

## Geometry and Attributes

`EVALUATED` uses post-modifier geometry; its indices may differ from original data.
`ORIGINAL` uses editable base data and is appropriate for writes. `geometry_target` selects
native mesh/curve data or evaluated mesh domains.

One geometry acquisition is shared by the whole action. `Geometry_Context` exposes
`write_attr()`, `edit_bmesh()`, and `finalize()`. Topology changes increment
`topology_generation`, invalidate per-element slots, and refresh counts.

`MET` declares mesh attributes across VERTEX, EDGE, FACE, and CORNER. `CET` declares native
curve attributes across POINT and CURVE. Both produce table-driven `Attr_Declaration`
records.

## Action Records and UI

Each run records its monotonic run number, ID, optional grouping ID, label, start time,
total duration, geometry provenance, validity, errors, and ordered substeps. Raised
substep errors also record the terminal traceback filename and line number.

The debug panel displays one native shared subpanel per stored action ID/object pair in the
order those unique identities were first sent to the wrapper API. Replacing a result keeps
its row position. The header shows status, three-decimal duration, run count, description,
and right-aligned trash/copy buttons. The copy button writes the complete domain and
`derived` payload as a Python string. Expanded content shows geometry provenance and run
time together, followed by titled **Name**, **Duration**, **Shape**, and **Type** columns.
Read types come directly from resolved attribute declarations (for example `FLOAT`, `INT`,
`BOOL`, `VEC2`, `VEC3`, and `COLOR4`); callbacks display `-`.

Subpanels use a stable action ID/object session UID panel identity, not the changing run
number, so native Blender expansion state survives result replacement. The block does not
request redraws.

Runtime cache:

| Key | Purpose |
|---|---|
| `GEOMETRY_ACTION_RESULTS` | Latest result per action ID/object session UID |
| `GEOMETRY_ACTION_UID_COUNTER` | Monotonic run-number source |

## Serialization

`cb_serialize_geometry` stores a compressed portable payload in
`instance.derived["serialized_geometry"]`. `cb_deserialize_geometry` applies one to original
Object Mode geometry. The `DGGEO2` frame uses an explicit compressed-header byte length
before its raw array payload. Socket transport is outside this block.

## Tests

Interactive:

```python
from DGBlocks.native_blocks.block_geometry_actions.tests import run_tests
run_tests.run()
```

Headless:

```bash
blender --background --python native_blocks/block_geometry_actions/tests/run_tests.py
```

Coverage includes mesh/curve reads, writes, callback failures, latest-result replacement,
object-scoped grouping, deep-copy inheritance, read replacement, object isolation, diffs,
and serialization.

## Loggers

| Logger | Usage |
|---|---|
| `GEOMETRY_ACTIONS_LIFECYCLE` | Wrapper and storage lifecycle |
| `GEOMETRY_ACTIONS_EVENTS` | Run timing and operation errors |
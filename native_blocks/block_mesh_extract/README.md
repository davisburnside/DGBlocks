# block_mesh_extract

**Block ID:** `block-mesh-extract`

## Purpose

Reads object mesh data into numpy arrays using `foreach_get` on Blender's evaluated
depsgraph mesh. Works on any object that can produce a mesh (`MESH`, `CURVE`, `SURFACE`,
`META`, `FONT`, `CURVES`, `POINTCLOUD`) in both Object mode and Edit mode without
switching modes. Lights, Empties, and other non-mesh types are rejected gracefully.

Downstream blocks declare what they need via `Numpy_Mesh_Extract_Declaration` (MET) objects submitted
through `hook_get_mesh_extract_targets`. This block merges, validates, extracts, caches,
and then fires `hook_mesh_extract_ready` to notify downstream blocks that data is available.

---

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |

---

## Architecture Summary

### Extraction Flow

1. `run_mesh_extract()` is called (via operator, scene property, or public API).
2. `hook_get_mesh_extract_targets` is broadcast — each subscribed block returns a
   `list[Numpy_Mesh_Extract_Declaration]`.
3. All METs are merged by `object_name` (silent union for attrs; last-writer-wins for callbacks).
4. Each object is extracted via `evaluated_get(depsgraph)` → `to_mesh()` — no mode switching.
5. First-level reads run, then custom attribute reads, then callbacks in insertion order.
6. Results are written to `RTC_Mesh_Extract_Instance` objects.
7. The BL `extract_mirror` CollectionProperty is synced.
8. `hook_mesh_extract_ready` fires with `object_names: list[str]`.

### Attribute Levels

**All MET attributes are first-level** — read directly via `foreach_get`:

| Attribute | Domain | dtype | Shape |
|---|---|---|---|
| `MET.VERTEX.CO` | VERTEX | float32 | (n_verts, 3) |
| `MET.VERTEX.NORMAL` | VERTEX | float32 | (n_verts, 3) |
| `MET.EDGE.VERTICES` | EDGE | int32 | (n_edges, 2) |
| `MET.EDGE.CREASE` | EDGE | float32 | (n_edges,) |
| `MET.EDGE.SHARP` | EDGE | bool | (n_edges,) |
| `MET.FACE.NORMAL` | FACE | float32 | (n_faces, 3) |
| `MET.FACE.AREA` | FACE | float32 | (n_faces,) |
| `MET.FACE.LOOP_START` | FACE | int32 | (n_faces,) |
| `MET.FACE.LOOP_TOTAL` | FACE | int32 | (n_faces,) |
| `MET.CORNER.VERTEX_INDEX` | CORNER | int32 | (n_corners,) |

**Derived data** (edge length, face center, neighbor CSR arrays, etc.) is produced by
callbacks and stored in `instance.custom_attribute_arrays`. Use the pre-built callbacks
in `block_mesh_extract.callbacks` — see the **Pre-built Callbacks** section below.

### Pre-built Callbacks (`callbacks.py`)

Import and use in `Numpy_Mesh_Extract_Declaration.callbacks` dict:

```python
from native_blocks.block_mesh_extract.callbacks import (
    cb_edge_length,          # np.ndarray (n_edges,)     float32
    cb_face_center,          # np.ndarray (n_faces, 3)   float32
    cb_vert_vert_neighbors,  # (indices, offsets) CSR tuple
    cb_vert_face_neighbors,  # (indices, offsets) CSR tuple
    cb_face_face_neighbors,  # (indices, offsets) CSR tuple
)
```

| Callback | Key | Returns | Required attrs |
|---|---|---|---|
| `cb_edge_length` | `"edge_length"` | `np.ndarray (n_edges,)` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_face_center` | `"face_center"` | `np.ndarray (n_faces, 3)` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_vert_vert_neighbors` | `"vert_vert_neighbors"` | `(idx, off)` | `VERTEX.CO`, `EDGE.VERTICES` |
| `cb_vert_face_neighbors` | `"vert_face_neighbors"` | `(idx, off)` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `cb_face_face_neighbors` | `"face_face_neighbors"` | `(idx, off)` | `FACE.NORMAL`, `EDGE.VERTICES`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |

**Accessing CSR data:**
```python
idx, off = instance.custom_attribute_arrays["face_face_neighbors"]
# Neighbors of face i:
neighbors = idx[off[i] : off[i+1]]
```

### Custom Attributes

Named mesh attributes (e.g. Geometry Nodes outputs, vertex color layers) are read via
`mesh.attributes[name].data.foreach_get(...)` and stored in
`instance.custom_attribute_arrays[attr_name]`.

```python
Numpy_Mesh_Extract_Declaration(
    object_name       = "Cube",
    read_attributes   = [MET.VERTEX.CO],
    custom_attributes = [(MET.VERTEX, "my_custom_float")],
)
```

### Callbacks

Callbacks run after all standard reads and custom attribute reads. The `callbacks` field is
a **dict mapping a string key to a callable**:

```python
callbacks: dict[str, Callable]  # attr_name → func(instance) → any
```

- Keys are insertion-ordered (Python 3.7+) — callbacks run in the order they appear in the dict.
- Each result is stored in `instance.custom_attribute_arrays[attr_name]`.
- The key is also used as the metadata timing key (`cb:<attr_name>`).
- A callback may return any value (numpy array, tuple, dict, etc.).

Callbacks that raise an exception **abort extraction for that object** — `is_valid` is set
to `False` and `error_str` is populated. No pre-flight validation of callback inputs is
performed; errors surface at runtime and are displayed in the UI panel details pane.

```python
from native_blocks.block_mesh_extract.callbacks import cb_face_face_neighbors

def _my_planarity(instance):
    ffi, ffo = instance.custom_attribute_arrays["face_face_neighbors"]
    return compute_coplanar_groups(
        instance.face_normal,
        ffi, ffo,
        tolerance_deg=1.0,
    )

Numpy_Mesh_Extract_Declaration(
    object_name     = "Cube",
    read_attributes = [MET.FACE.NORMAL, MET.EDGE.VERTICES,
                       MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL,
                       MET.CORNER.VERTEX_INDEX],
    callbacks       = {
        "face_face_neighbors": cb_face_face_neighbors,  # must run before planarity
        "coplanar_group_id":   _my_planarity,
    },
)
```

---

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_mesh_extract_props.run_mesh_extract` | `BoolProperty` | Momentary trigger; auto-resets to False |
| `scene.dgblocks_mesh_extract_props.extract_mirror` | `CollectionProperty` | Per-object BL persistence (key + is_valid only) |
| `scene.dgblocks_mesh_extract_props.extract_mirror_selected_idx` | `IntProperty` | Active UIList row |

**`DGBLOCKS_PG_Mesh_Extract_Mirror_Row` fields:**

| Field | Type | Notes |
|---|---|---|
| `object_name` | `StringProperty` | Key — matches `RTC_Mesh_Extract_Instance.object_name` |
| `is_valid` | `BoolProperty` | Display only |

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `MESH_EXTRACT_INSTANCES` | `list[RTC_Mesh_Extract_Instance]` | All extracted object instances |

### `RTC_Mesh_Extract_Instance` Fields

| Field | Shape | dtype | Description |
|---|---|---|---|
| `object_name` | — | str | UID |
| `is_valid` | — | bool | False if extraction failed (includes callback failures) |
| `error_str` | — | str\|None | Error detail if is_valid=False |
| `vertex_co` | (n_verts, 3) | float32 | Vertex positions |
| `vertex_normal` | (n_verts, 3) | float32 | Vertex normals |
| `edge_vertices` | (n_edges, 2) | int32 | Per-edge vertex indices |
| `edge_crease` | (n_edges,) | float32 | Edge crease values |
| `edge_sharp` | (n_edges,) | bool | Sharp edge flags |
| `face_normal` | (n_faces, 3) | float32 | Face normals |
| `face_area` | (n_faces,) | float32 | Face areas |
| `face_loop_start` | (n_faces,) | int32 | Loop start indices |
| `face_loop_total` | (n_faces,) | int32 | Loop counts per face |
| `corner_vertex_index` | (n_corners,) | int32 | Per-corner vertex index |
| `custom_attribute_arrays` | dict | — | Named mesh attr arrays, CSR tuples, and all callback results |
| `extract_metadata` | dict | — | Per-attr + `_total` timing, shape & read_count |

All derived data (edge length, face centers, neighbor CSR arrays, etc.) lives in
`custom_attribute_arrays`, keyed by the callback's dict key.

---

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_mesh_extract_targets` | block_mesh_extract → subscribers | `{}` | Collect `Numpy_Mesh_Extract_Declaration` objects |
| `hook_mesh_extract_ready` | block_mesh_extract → subscribers | `object_names: list[str]` | Signal that extraction is complete |

---

## Trigger Mechanisms

### Option 1 — Scene Property (from UI or Python)
```python
bpy.context.scene.dgblocks_mesh_extract_props.run_mesh_extract = True
# Auto-resets to False; triggers run_mesh_extract()
```

### Option 2 — Public API
```python
from native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract
processed_names = Wrapper_Mesh_Extract.run_mesh_extract_for_object()
```

---

## Public API — `Wrapper_Mesh_Extract`

| Method | Returns | Description |
|---|---|---|
| `run_mesh_extract_for_object()` | `list[str]` | Trigger full extraction; returns processed object names |
| `get_instance(name)` | `RTC_Mesh_Extract_Instance \| None` | Get valid instance by object name |
| `get_all_instances()` | `list[RTC_Mesh_Extract_Instance]` | All live instances |
| `diff_instances(old, new)` | `list[str]` | Return names of all shared fields that differ between two instances; empty = unchanged |

---

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_mesh_extract.data_structures import MET, Numpy_Mesh_Extract_Declaration
from ...native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract
from ...native_blocks.block_mesh_extract.callbacks import cb_face_face_neighbors
from ...native_blocks.block_mesh_extract.helpers_computed import compute_coplanar_groups


def _compute_planarity(instance):
    """Callback: receives the full RTC instance, returns one np.ndarray."""
    ffi, ffo = instance.custom_attribute_arrays["face_face_neighbors"]
    return compute_coplanar_groups(
        instance.face_normal,
        ffi, ffo,
        tolerance_deg=1.0,
    )


def hook_get_mesh_extract_targets():
    return [
        Numpy_Mesh_Extract_Declaration(
            object_name     = "Cube",
            read_attributes = [
                MET.VERTEX.CO,
                MET.FACE.NORMAL,
                MET.FACE.AREA,
                MET.FACE.LOOP_START,
                MET.FACE.LOOP_TOTAL,
                MET.EDGE.VERTICES,
                MET.CORNER.VERTEX_INDEX,
            ],
            custom_attributes = [(MET.VERTEX, "my_float_attr")],
            callbacks = {
                "face_face_neighbors": cb_face_face_neighbors,  # CSR — runs first
                "coplanar_group_id":   _compute_planarity,      # reads CSR result above
            },
        )
    ]


def hook_mesh_extract_ready(object_names: list):
    instance = Wrapper_Mesh_Extract.get_instance("Cube")
    if instance:
        print(f"Cube has {instance.vertex_co.shape[0]} vertices")
        print(f"Planarity groups: {instance.custom_attribute_arrays.get('coplanar_group_id')}")
        ffi, ffo = instance.custom_attribute_arrays["face_face_neighbors"]
        print(f"Face-face neighbor data: {ffi.shape[0]} adjacency entries")
```

---

## Planarity Helpers (`helpers_computed.py`)

Two functions are provided as ready-to-use callback innards for a planarity workflow:

### `compute_coplanar_groups(...) → np.ndarray (n_faces,) int32`
Assigns each face a coplanar group ID. Special values:
- `-1` : NGon/quad that fails self-planarity check
- `-2` : Face area below `min_area` threshold

Uses scipy `connected_components` on a face-adjacency graph filtered by normal dot product.

### `compute_coplanar_boundaries(...) → dict[int → list[list[int]]]`
For each coplanar group: returns ordered edge-index walks of all boundary loops.
Outer boundary (longest walk) is always first in the list.

---

## `helpers_computed.py` — NJIT Contract

All functions in `helpers_computed.py` are pure: only numpy arrays + scalars in,
numpy arrays out. No bpy, no global state. Each is a direct candidate for `@njit`.

Wrapping pattern for future NJIT conversion:

```python
def compute_edge_length(vertex_co, edge_vertices):
    return _compute_edge_length_inner(vertex_co, edge_vertices)

# @njit  ← uncomment when ready
def _compute_edge_length_inner(vertex_co, edge_vertices):
    ...
```

The boundary walk (`_traverse_boundary_walk`) contains a Python loop that cannot be
trivially vectorized. It is isolated in its own function with a docstring NJIT note
explaining the conversion path (replace dict/set with CSR integer arrays).

---

## Validation

No pre-flight validation is performed. Callbacks that access arrays which are `None`
(because the corresponding attribute was not requested) will raise at runtime, which
marks `is_valid=False` and populates `error_str` on the instance. The error is displayed
in the UI panel details pane.

---

## Metadata Format

`instance.extract_metadata` structure:

```python
{
    "VERTEX.co":                  {"duration_ms": 0.31, "read_count": 3, "shape": (1024, 3)},
    "FACE.normal":                {"duration_ms": 0.18, "read_count": 3, "shape": (512, 3)},
    "custom:my_attr":             {"duration_ms": 0.12, "read_count": 3, "shape": (1024,)},
    "cb:face_face_neighbors":     {"duration_ms": 0.80, "read_count": 3, "shape": "-"},
    "cb:coplanar_group_id":       {"duration_ms": 4.20, "read_count": 3, "shape": (512,)},
    "_total":                     {"duration_ms": 5.10, "read_count": 3},
}
```

- Attribute rows include `"shape"` (the numpy `.shape` tuple, or `"-"` for non-array results).
- Callback rows are prefixed `cb:` and show the shape of the returned value (if it has `.shape`).
- `_total.read_count` increments on every extraction run for that object.
- The UI details pane renders attribute rows and the total summary separately.

---

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `MESH_EXTRACT_LIFECYCLE` | `DEBUG` | Rebuild/clear events, sync, init/remove |
| `MESH_EXTRACT_EVENTS` | `DEBUG` | Per-object extraction results, attribute errors |

---

## Files

```text
block_mesh_extract/
├── __init__.py              # Block declaration, BL props, operator, panel, UIList
├── README.md                # This file
├── common_declarations.py   # Block_Hook_Sources, Block_Loggers, Block_RTC_Members,
│                            # Block_Data_Mirrors, Block_UIList_Configs
├── data_structures.py       # MET, MET_Attr_Declaration, Numpy_Mesh_Extract_Declaration,
│                            # RTC_Mesh_Extract_Instance, ALL_MET_ATTRS
├── callbacks.py             # Pre-built callback functions:
│                            # cb_edge_length, cb_face_center,
│                            # cb_vert_vert_neighbors, cb_vert_face_neighbors,
│                            # cb_face_face_neighbors
├── feature_mesh_extract.py  # Wrapper_Mesh_Extract (FWC)
├── helpers.py               # run_mesh_extract, merge, _new_mesh_extract_instance_from_mesh,
│                            # _foreach_get_attr, _read_custom_attribute
├── helpers_computed.py      # Pure numpy computed functions (NJIT-ready):
│                            # compute_edge_length, compute_face_center,
│                            # build_*_csr, compute_coplanar_groups,
│                            # compute_coplanar_boundaries
└── ui.py                    # UIList row + details draw helpers
```

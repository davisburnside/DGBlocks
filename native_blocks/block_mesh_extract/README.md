# block_mesh_extract

**Block ID:** `block-mesh-extract`

## Purpose

Reads object mesh data into numpy arrays using `foreach_get` on Blender's evaluated
depsgraph mesh. Works on any object that can produce a mesh (`MESH`, `CURVE`, `SURFACE`,
`META`, `FONT`, `CURVES`, `POINTCLOUD`) in both Object mode and Edit mode without
switching modes. Lights, Empties, and other non-mesh types are rejected gracefully.

Downstream blocks declare what they need via `Mesh_Extract_Target` (MET) objects submitted
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
   `list[Mesh_Extract_Target]`.
3. All METs are merged by `object_name` (silent union).
4. Merged targets are validated — dependency errors raise `ValueError` before any bpy access.
5. Each object is extracted via `evaluated_get(depsgraph)` → `to_mesh()` — no mode switching.
6. Results are written to `RTC_Mesh_Extract_Instance` objects.
7. The BL `extract_mirror` CollectionProperty is synced.
8. `hook_mesh_extract_ready` fires with `object_names: list[str]`.

### Attribute Levels

**First-level** — direct `foreach_get` calls:
- `MET.VERTEX.CO`, `MET.VERTEX.NORMAL`
- `MET.EDGE.VERTICES`, `MET.EDGE.CREASE`, `MET.EDGE.SHARP`
- `MET.FACE.NORMAL`, `MET.FACE.AREA`, `MET.FACE.LOOP_START`, `MET.FACE.LOOP_TOTAL`
- `MET.CORNER.VERTEX_INDEX`

**Nth-level (computed)** — derived from first-level data, validated at MET submission time:

| Attribute | Dependencies |
|---|---|
| `MET.EDGE.LENGTH` | `VERTEX.CO`, `EDGE.VERTICES` |
| `MET.FACE.CENTER` | `VERTEX.CO`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `MET.VERTEX.VERT_NEIGHBORS` | `EDGE.VERTICES` |
| `MET.VERTEX.FACE_NEIGHBORS` | `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |
| `MET.FACE.FACE_NEIGHBORS` | `EDGE.VERTICES`, `FACE.LOOP_START`, `FACE.LOOP_TOTAL`, `CORNER.VERTEX_INDEX` |

### Ragged Array Storage (CSR Format)

Neighbor data (vert-vert, vert-face, face-face) is stored in **Compressed Sparse Row**
format — two parallel numpy arrays:

```python
# Get neighbors of vertex i:
neighbors = instance.vert_vert_neighbor_indices[
    instance.vert_vert_neighbor_offsets[i] : instance.vert_vert_neighbor_offsets[i+1]
]
```

This enables fully vectorized downstream math via `np.add.reduceat` and scipy's
`csgraph` functions.

### Custom Attributes

Named mesh attributes (e.g. Geometry Nodes outputs, vertex color layers) are read via
`mesh.attributes[name].data.foreach_get(...)` and stored in
`instance.custom_attribute_arrays[attr_name]`.

```python
Mesh_Extract_Target(
    object_name       = "Cube",
    read_attributes   = [MET.VERTEX.CO],
    custom_attributes = [(MET.VERTEX, "my_custom_float")],
)
```

### Callbacks

`Mesh_Extract_Callback` objects attached to a MET run after all standard reads/computes.
They are timed individually and their results are stored in `instance.custom_domain_data`.
Callbacks do not abort extraction on exception — errors are logged and the next callback continues.

```python
Mesh_Extract_Callback(
    uid                 = "MY_CALLBACK",
    callback            = _my_fn,      # (instance, **params) -> None
    required_attributes = [MET.FACE.NORMAL, MET.FACE.AREA],
    params              = {"threshold": 0.01},
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

### `RTC_Mesh_Extract_Instance` Key Fields

| Field | Shape | dtype | Description |
|---|---|---|---|
| `object_name` | — | str | UID |
| `is_valid` | — | bool | False if extraction failed |
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
| `edge_length` | (n_edges,) | float32 | Computed edge lengths |
| `face_center` | (n_faces, 3) | float32 | Computed face centroids |
| `vert_vert_neighbor_indices` | (n_edges×2,) | int32 | CSR data for V-V neighbors |
| `vert_vert_neighbor_offsets` | (n_verts+1,) | int32 | CSR offsets for V-V neighbors |
| `vert_face_neighbor_indices` | (n_corners,) | int32 | CSR data for V-F neighbors |
| `vert_face_neighbor_offsets` | (n_verts+1,) | int32 | CSR offsets for V-F neighbors |
| `face_face_neighbor_indices` | (n_shared×2,) | int32 | CSR data for F-F neighbors |
| `face_face_neighbor_offsets` | (n_faces+1,) | int32 | CSR offsets for F-F neighbors |
| `custom_attribute_arrays` | dict | — | Named mesh attr arrays |
| `custom_domain_data` | dict | — | Callback output storage |
| `extract_metadata` | dict | — | Per-attr + `_total` timing & read_count |

---

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_mesh_extract_targets` | block_mesh_extract → subscribers | `{}` | Collect `Mesh_Extract_Target` objects |
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
processed_names = Wrapper_Mesh_Extract.run_extract()
```

---

## Public API — `Wrapper_Mesh_Extract`

| Method | Returns | Description |
|---|---|---|
| `run_extract()` | `list[str]` | Trigger full extraction; returns processed object names |
| `get_instance(name)` | `RTC_Mesh_Extract_Instance \| None` | Get valid instance by object name |
| `get_instance_raw(name)` | `RTC_Mesh_Extract_Instance \| None` | Get instance regardless of is_valid |
| `get_all_instances()` | `list[RTC_Mesh_Extract_Instance]` | All live instances |

---

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_mesh_extract.data_structures import (
    MET, Mesh_Extract_Target, Mesh_Extract_Callback
)
from ...native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract

def hook_get_mesh_extract_targets():
    return [
        Mesh_Extract_Target(
            object_name       = "Cube",
            read_attributes   = [
                MET.VERTEX.CO,
                MET.FACE.NORMAL,
                MET.FACE.AREA,
                MET.FACE.LOOP_START,
                MET.FACE.LOOP_TOTAL,
                MET.EDGE.VERTICES,
                MET.CORNER.VERTEX_INDEX,
                MET.FACE.FACE_NEIGHBORS,   # Nth-level; deps above satisfy it
            ],
            custom_attributes = [(MET.VERTEX, "my_float_attr")],
            callbacks         = [
                Mesh_Extract_Callback(
                    uid                 = "MY_PLANARITY",
                    callback            = _compute_planarity,
                    required_attributes = [MET.FACE.NORMAL, MET.FACE.AREA],
                    params              = {"tolerance_deg": 1.0},
                )
            ],
        )
    ]

def hook_mesh_extract_ready(object_names: list):
    instance = Wrapper_Mesh_Extract.get_instance("Cube")
    if instance:
        print(f"Cube has {instance.vertex_co.shape[0]} vertices")
        print(f"Planarity groups: {instance.custom_domain_data.get('coplanar_group_id')}")
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

`validate_mesh_extract_targets()` in `helpers.py` runs before any bpy access:

1. Every computed attribute's `first_level_deps` must be present in `read_attributes`.
2. Every callback's `required_attributes` must be present in `read_attributes`.
3. No duplicate callback UIDs within a single merged target.

---

## Metadata Format

`instance.extract_metadata` structure:

```python
{
    "VERTEX.co":        {"duration_ms": 0.31, "read_count": 3},
    "FACE.normal":      {"duration_ms": 0.18, "read_count": 3},
    "EDGE.(computed)":  {"duration_ms": 0.05, "read_count": 3},
    "custom:my_attr":   {"duration_ms": 0.12, "read_count": 3},
    "MY_CALLBACK":      {"duration_ms": 4.20, "read_count": 3},
    "_total":           {"duration_ms": 5.10, "read_count": 3},
}
```

`_total.read_count` increments on every extraction run for that object.

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
├── data_structures.py       # MET, MET_Attr_Declaration, Mesh_Extract_Target,
│                            # Mesh_Extract_Callback, RTC_Mesh_Extract_Instance
├── feature_mesh_extract.py  # Wrapper_Mesh_Extract (FWC)
├── helpers.py               # run_mesh_extract, merge, validate, _extract_single_object,
│                            # _foreach_get_attr, _read_custom_attribute
├── helpers_computed.py      # Pure numpy computed functions (NJIT-ready):
│                            # compute_edge_length, compute_face_center,
│                            # build_*_csr, compute_coplanar_groups,
│                            # compute_coplanar_boundaries
└── ui.py                    # UIList row + details draw helpers
```


from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Optional

# ==============================================================================================================================
# MET ATTRIBUTE DECLARATIONS
# Typed descriptors for every readable mesh attribute.
# Each leaf is a frozen MET_Attr_Declaration — no magic strings outside this file.
# ==============================================================================================================================

@dataclass(frozen=True)
class MET_Attr_Declaration:
    """
    Descriptor for a single readable mesh attribute.

    domain          : Blender domain string — "VERTEX", "EDGE", "FACE", or "CORNER"
    blender_attr    : Key passed to foreach_get, or None for computed attributes
    dtype           : numpy dtype string ("float32", "int32", "bool")
    components      : Number of scalar values per mesh element (1 = scalar, 2 = vec2, 3 = vec3)
    is_computed     : True → not a foreach_get; depends on first_level_deps
    first_level_deps: Tuple of MET_Attr_Declarations that must also be requested in the MET
    """
    domain:           str
    blender_attr:     Optional[str]
    dtype:            str
    components:       int
    is_computed:      bool = False
    first_level_deps: tuple = field(default_factory=tuple)

    def __repr__(self):
        return f"MET.{self.domain}.{self.blender_attr or '(computed)'}"


# ----------------------------------------------------------
# Forward-declare containers so cross-references work below.
# The actual class bodies are filled in immediately after.

class _MET_VERTEX:
    pass

class _MET_EDGE:
    pass

class _MET_FACE:
    pass

class _MET_CORNER:
    pass


# ----------------------------------------------------------
# CORNER — declared first; used as deps by others

class _MET_CORNER:
    VERTEX_INDEX = MET_Attr_Declaration(
        domain        = "CORNER",
        blender_attr  = "vertex_index",
        dtype         = "int32",
        components    = 1,
    )


# ----------------------------------------------------------
# VERTEX

class _MET_VERTEX:
    CO = MET_Attr_Declaration(
        domain       = "VERTEX",
        blender_attr = "co",
        dtype        = "float32",
        components   = 3,
    )
    NORMAL = MET_Attr_Declaration(
        domain       = "VERTEX",
        blender_attr = "normal",
        dtype        = "float32",
        components   = 3,
    )
    # Computed — requires edge connectivity
    VERT_NEIGHBORS = MET_Attr_Declaration(
        domain            = "VERTEX",
        blender_attr      = None,
        dtype             = "int32",
        components        = 1,
        is_computed       = True,
        first_level_deps  = (),   # filled below after _MET_EDGE exists
    )
    FACE_NEIGHBORS = MET_Attr_Declaration(
        domain            = "VERTEX",
        blender_attr      = None,
        dtype             = "int32",
        components        = 1,
        is_computed       = True,
        first_level_deps  = (),   # filled below
    )


# ----------------------------------------------------------
# EDGE

class _MET_EDGE:
    VERTICES = MET_Attr_Declaration(
        domain       = "EDGE",
        blender_attr = "vertices",
        dtype        = "int32",
        components   = 2,
    )
    CREASE = MET_Attr_Declaration(
        domain       = "EDGE",
        blender_attr = "crease_edge",
        dtype        = "float32",
        components   = 1,
    )
    SHARP = MET_Attr_Declaration(
        domain       = "EDGE",
        blender_attr = "sharp_edge",
        dtype        = "bool",
        components   = 1,
    )
    # Computed
    LENGTH = MET_Attr_Declaration(
        domain           = "EDGE",
        blender_attr     = None,
        dtype            = "float32",
        components       = 1,
        is_computed      = True,
        first_level_deps = (),   # filled below
    )


# ----------------------------------------------------------
# FACE

class _MET_FACE:
    NORMAL = MET_Attr_Declaration(
        domain       = "FACE",
        blender_attr = "normal",
        dtype        = "float32",
        components   = 3,
    )
    AREA = MET_Attr_Declaration(
        domain       = "FACE",
        blender_attr = "area",
        dtype        = "float32",
        components   = 1,
    )
    LOOP_START = MET_Attr_Declaration(
        domain       = "FACE",
        blender_attr = "loop_start",
        dtype        = "int32",
        components   = 1,
    )
    LOOP_TOTAL = MET_Attr_Declaration(
        domain       = "FACE",
        blender_attr = "loop_total",
        dtype        = "int32",
        components   = 1,
    )
    # Computed
    CENTER = MET_Attr_Declaration(
        domain           = "FACE",
        blender_attr     = None,
        dtype            = "float32",
        components       = 3,
        is_computed      = True,
        first_level_deps = (),   # filled below
    )
    FACE_NEIGHBORS = MET_Attr_Declaration(
        domain           = "FACE",
        blender_attr     = None,
        dtype            = "int32",
        components       = 1,
        is_computed      = True,
        first_level_deps = (),   # filled below
    )


# ----------------------------------------------------------
# Patch deps now that all sibling classes exist.
# frozen=True dataclasses can't be mutated, so we replace the field
# via object.__setattr__ (bypasses frozen enforcement for internal init).

def _patch_deps(obj: MET_Attr_Declaration, deps: tuple) -> MET_Attr_Declaration:
    """Return a new MET_Attr_Declaration with first_level_deps replaced."""
    return MET_Attr_Declaration(
        domain           = obj.domain,
        blender_attr     = obj.blender_attr,
        dtype            = obj.dtype,
        components       = obj.components,
        is_computed      = obj.is_computed,
        first_level_deps = deps,
    )


_MET_EDGE.LENGTH = _patch_deps(
    _MET_EDGE.LENGTH,
    (_MET_VERTEX.CO, _MET_EDGE.VERTICES),
)

_MET_FACE.CENTER = _patch_deps(
    _MET_FACE.CENTER,
    (_MET_VERTEX.CO, _MET_FACE.LOOP_START, _MET_FACE.LOOP_TOTAL, _MET_CORNER.VERTEX_INDEX),
)

_MET_FACE.FACE_NEIGHBORS = _patch_deps(
    _MET_FACE.FACE_NEIGHBORS,
    (_MET_EDGE.VERTICES, _MET_FACE.LOOP_START, _MET_FACE.LOOP_TOTAL, _MET_CORNER.VERTEX_INDEX),
)

_MET_VERTEX.VERT_NEIGHBORS = _patch_deps(
    _MET_VERTEX.VERT_NEIGHBORS,
    (_MET_EDGE.VERTICES,),
)

_MET_VERTEX.FACE_NEIGHBORS = _patch_deps(
    _MET_VERTEX.FACE_NEIGHBORS,
    (_MET_FACE.LOOP_START, _MET_FACE.LOOP_TOTAL, _MET_CORNER.VERTEX_INDEX),
)


# ----------------------------------------------------------
# Public top-level namespace

class MET:
    """
    Mesh Extract Target attribute namespace.

    Usage:
        MET.VERTEX.CO
        MET.EDGE.VERTICES
        MET.FACE.NORMAL
        MET.CORNER.VERTEX_INDEX
    """
    VERTEX = _MET_VERTEX
    EDGE   = _MET_EDGE
    FACE   = _MET_FACE
    CORNER = _MET_CORNER


# Flat set of all known MET_Attr_Declarations — used for validation and iteration
ALL_MET_ATTRS: tuple[MET_Attr_Declaration, ...] = (
    MET.VERTEX.CO,
    MET.VERTEX.NORMAL,
    MET.VERTEX.VERT_NEIGHBORS,
    MET.VERTEX.FACE_NEIGHBORS,
    MET.EDGE.VERTICES,
    MET.EDGE.CREASE,
    MET.EDGE.SHARP,
    MET.EDGE.LENGTH,
    MET.FACE.NORMAL,
    MET.FACE.AREA,
    MET.FACE.LOOP_START,
    MET.FACE.LOOP_TOTAL,
    MET.FACE.CENTER,
    MET.FACE.FACE_NEIGHBORS,
    MET.CORNER.VERTEX_INDEX,
)

# Human-readable label for a MET_Attr_Declaration (used in metadata keys and logs)
_DOMAIN_SHORT = {
    "VERTEX": "VERTEX",
    "EDGE":   "EDGE",
    "FACE":   "FACE",
    "CORNER": "CORNER",
}

def met_attr_label(attr: MET_Attr_Declaration) -> str:
    """Return a stable string key for this attr, e.g. 'VERTEX.co' or 'FACE.normal'."""
    suffix = attr.blender_attr if attr.blender_attr else "(computed)"
    return f"{attr.domain}.{suffix}"


# ==============================================================================================================================
# MESH EXTRACT TARGET (MET DECLARATION)
# ==============================================================================================================================

@dataclass
class Mesh_Extract_Target:
    """
    Declaration submitted by downstream blocks inside hook_get_mesh_extract_targets.

    object_name         : Blender object name — the UID.
    read_attributes     : Standard attributes to read via foreach_get or compute.
                          Use MET.DOMAIN.ATTR enum members; never raw strings.
    custom_attributes   : Named mesh attributes to read from bpy mesh.attributes.
                          Each entry is a (domain_class, attr_name_str) tuple,
                          e.g. (MET.VERTEX, "my_vert_color").
    callbacks           : Optional list of 2-tuples (attr_name, func), executed after all
                          standard reads/computes, in MET submission order.
                          func signature: func(instance) -> np.ndarray
                          Result stored in instance.custom_attribute_arrays[attr_name].

    Example:
        Mesh_Extract_Target(
            object_name       = "Cube",
            read_attributes   = [MET.VERTEX.CO, MET.FACE.NORMAL, MET.EDGE.LENGTH],
            custom_attributes = [(MET.VERTEX, "my_attr")],
            callbacks         = [my_planarity_callback],
        )
    """
    object_name:       str
    read_attributes:   list   # list[MET_Attr_Declaration]
    custom_attributes: list = field(default_factory=list)   # list[tuple[domain_class, str]]
    callbacks:         list = field(default_factory=list)   # list[tuple[attr_name: str, func: Callable]]
                                                            # func signature: func(instance) -> np.ndarray


# ==============================================================================================================================
# RTC MESH EXTRACT INSTANCE
# Runtime record for one extracted object. Lifecycle managed by Wrapper_Mesh_Extract.
# ==============================================================================================================================

@dataclass
class RTC_Mesh_Extract_Instance:
    """
    Live runtime record for a single extracted object.
    Fully managed by Wrapper_Mesh_Extract — do not construct directly.

    Standard attribute arrays are None until their corresponding MET_Attr_Declaration
    was included in the merged Mesh_Extract_Target for this object.

    Ragged neighbor data (CSR format):
        indices array: flat concatenation of all neighbor lists
        offsets array: length (n_elements + 1) — neighbors of element i are
                       indices[ offsets[i] : offsets[i+1] ]

    custom_attribute_arrays : dict[attr_name_str → np.ndarray]
                              Holds both named BL mesh attributes and callback results.
                              Callback keys are the attr_name from each callback 2-tuple.
    extract_metadata        : dict[label_str → {"duration_ms": float, "read_count": int}]
                              Special key "_total" holds object-level totals.
    """

    # Identity
    object_name: str

    # Status
    is_valid:   bool            = False
    error_str:  Optional[str]   = None

    # ---- First-level arrays (foreach_get) ----------------------------------------

    # VERTEX
    vertex_co:           Optional[np.ndarray] = None   # (n_verts, 3)  float32
    vertex_normal:       Optional[np.ndarray] = None   # (n_verts, 3)  float32

    # EDGE
    edge_vertices:       Optional[np.ndarray] = None   # (n_edges, 2)  int32
    edge_crease:         Optional[np.ndarray] = None   # (n_edges,)    float32
    edge_sharp:          Optional[np.ndarray] = None   # (n_edges,)    bool

    # FACE
    face_normal:         Optional[np.ndarray] = None   # (n_faces, 3)  float32
    face_area:           Optional[np.ndarray] = None   # (n_faces,)    float32
    face_loop_start:     Optional[np.ndarray] = None   # (n_faces,)    int32
    face_loop_total:     Optional[np.ndarray] = None   # (n_faces,)    int32

    # CORNER
    corner_vertex_index: Optional[np.ndarray] = None   # (n_corners,)  int32

    # ---- Nth-level computed arrays -----------------------------------------------

    # EDGE computed
    edge_length:                Optional[np.ndarray] = None   # (n_edges,)    float32

    # FACE computed
    face_center:                Optional[np.ndarray] = None   # (n_faces, 3)  float32

    # VERTEX neighbors — CSR
    vert_vert_neighbor_indices: Optional[np.ndarray] = None   # (total_edges*2,) int32
    vert_vert_neighbor_offsets: Optional[np.ndarray] = None   # (n_verts+1,)    int32

    vert_face_neighbor_indices: Optional[np.ndarray] = None   # (n_corners,)  int32
    vert_face_neighbor_offsets: Optional[np.ndarray] = None   # (n_verts+1,)  int32

    # FACE neighbors — CSR
    face_face_neighbor_indices: Optional[np.ndarray] = None   # (n_shared_edges*2,) int32
    face_face_neighbor_offsets: Optional[np.ndarray] = None   # (n_faces+1,)        int32

    # ---- Custom & callback output -------------------------------------------------

    # dict[attr_name_str → np.ndarray]
    custom_attribute_arrays: dict = field(default_factory=dict)

    # ---- Metadata ----------------------------------------------------------------
    # dict[label_str → {"duration_ms": float, "read_count": int}]
    # "_total" key holds object-level totals
    extract_metadata: dict = field(default_factory=dict)

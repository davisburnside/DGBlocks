
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Optional

# ==============================================================================================================================
# MET ATTRIBUTE DECLARATIONS
# Typed descriptors for every readable (first-level) mesh attribute.
# All attributes are read directly via foreach_get — no computed attributes.
# Derived data (edge length, face center, neighbor CSR, etc.) is obtained via callbacks.
# ==============================================================================================================================

@dataclass(frozen=True)
class MET_Attr_Declaration:
    """
    Descriptor for a single readable mesh attribute.

    domain       : Blender domain string — "VERTEX", "EDGE", "FACE", or "CORNER"
    blender_attr : Key passed to foreach_get
    dtype        : numpy dtype string ("float32", "int32", "bool")
    components   : Number of scalar values per mesh element (1 = scalar, 2 = vec2, 3 = vec3)
    """
    domain:       str
    blender_attr: str
    dtype:        str
    components:   int

    def __repr__(self):
        return f"MET.{self.domain}.{self.blender_attr}"


# ----------------------------------------------------------
# CORNER

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
    CREASE = MET_Attr_Declaration(
        domain       = "VERTEX",
        blender_attr = "crease_vert",
        dtype        = "float32",
        components   = 1,
    )
    BEVEL_WEIGHT = MET_Attr_Declaration(
        domain       = "VERTEX",
        blender_attr = "bevel_weight_vert",
        dtype        = "float32",
        components   = 1,
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
    SEAM = MET_Attr_Declaration(
        domain       = "EDGE",
        blender_attr = "seam_edge",
        dtype        = "bool",
        components   = 1,
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


# ----------------------------------------------------------
# Public top-level namespace

class MET:
    """
    Mesh Extract Target attribute namespace.
    All attributes are first-level: read directly via foreach_get.

    Derived data (edge length, face center, CSR neighbor arrays, etc.) is not part of MET.
    Use the pre-built callbacks in block_mesh_extract.callbacks, or write your own,
    and add them to Numpy_Mesh_Extract_Declaration.callbacks.

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


# Flat tuple of all known MET_Attr_Declarations — used for validation and iteration
ALL_MET_ATTRS: tuple[MET_Attr_Declaration, ...] = (
    MET.VERTEX.CO,
    MET.VERTEX.NORMAL,
    MET.VERTEX.CREASE,
    MET.VERTEX.BEVEL_WEIGHT,
    MET.EDGE.VERTICES,
    MET.EDGE.CREASE,
    MET.EDGE.SHARP,
    MET.EDGE.SEAM,
    MET.FACE.NORMAL,
    MET.FACE.AREA,
    MET.FACE.LOOP_START,
    MET.FACE.LOOP_TOTAL,
    MET.CORNER.VERTEX_INDEX,
)

# Human-readable label for a MET_Attr_Declaration (used in metadata keys and logs)
def met_attr_label(attr: MET_Attr_Declaration) -> str:
    """Return a stable string key for this attr, e.g. 'VERTEX.co' or 'FACE.normal'."""
    return f"{attr.domain}.{attr.blender_attr}"


# ==============================================================================================================================
# MESH EXTRACT TARGET (MET DECLARATION)
# ==============================================================================================================================

@dataclass
class Numpy_Mesh_Extract_Declaration:
    """
    Declaration submitted by downstream blocks inside hook_get_mesh_extract_targets.

    object_name         : Blender object name — the UID.
    read_attributes     : Standard attributes to read via foreach_get.
                          Use MET.DOMAIN.ATTR members; never raw strings.
    custom_attributes   : Named mesh attributes to read from bpy mesh.attributes.
                          Each entry is a (domain_class, attr_name_str) tuple,
                          e.g. (MET.VERTEX, "my_vert_color").
    callbacks           : dict[attr_name: str → func: Callable], executed after all
                          standard reads/custom attributes, in insertion order.
                          func signature: func(instance) -> any
                          Result stored in instance.custom_attribute_arrays[attr_name].
                          Use pre-built callbacks from block_mesh_extract.callbacks for
                          standard derived data (edge_length, face_center, CSR neighbors).

    Example:
        from native_blocks.block_mesh_extract.callbacks import cb_face_face_neighbors

        Numpy_Mesh_Extract_Declaration(
            object_name       = "Cube",
            read_attributes   = [MET.VERTEX.CO, MET.FACE.NORMAL, MET.EDGE.VERTICES,
                                  MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX],
            custom_attributes = [(MET.VERTEX, "my_attr")],
            callbacks         = {
                "face_face_neighbors": cb_face_face_neighbors,
                "coplanar_group_id":   _my_planarity_callback,
            },
        )
    """
    object_name:       str
    read_attributes:   list   # list[MET_Attr_Declaration]
    custom_attributes: list = field(default_factory=list)   # list[tuple[domain_class, str]]
    callbacks:         dict = field(default_factory=dict)   # dict[attr_name: str → func: Callable]
                                                            # func signature: func(instance) -> any


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
    was included in the merged Numpy_Mesh_Extract_Declaration for this object.

    All derived/computed data (edge length, face center, CSR neighbor arrays, etc.)
    is stored in custom_attribute_arrays by the callback that produced it.
    CSR callbacks store a (indices, offsets) tuple under their key:
        idx, off = instance.custom_attribute_arrays["face_face_neighbors"]

    custom_attribute_arrays : dict[attr_name_str → any]
                              Holds named BL mesh attributes and all callback results.
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
    vertex_crease:       Optional[np.ndarray] = None   # (n_verts,)    float32
    vertex_bevel_weight: Optional[np.ndarray] = None   # (n_verts,)    float32

    # EDGE
    edge_vertices:       Optional[np.ndarray] = None   # (n_edges, 2)  int32
    edge_crease:         Optional[np.ndarray] = None   # (n_edges,)    float32
    edge_sharp:          Optional[np.ndarray] = None   # (n_edges,)    bool
    edge_seam:           Optional[np.ndarray] = None   # (n_edges,)    bool

    # FACE
    face_normal:         Optional[np.ndarray] = None   # (n_faces, 3)  float32
    face_area:           Optional[np.ndarray] = None   # (n_faces,)    float32
    face_loop_start:     Optional[np.ndarray] = None   # (n_faces,)    int32
    face_loop_total:     Optional[np.ndarray] = None   # (n_faces,)    int32

    # CORNER
    corner_vertex_index: Optional[np.ndarray] = None   # (n_corners,)  int32

    # ---- Custom & callback output -------------------------------------------------

    # dict[attr_name_str → any]   — numpy arrays, CSR tuples, or any callback result
    custom_attribute_arrays: dict = field(default_factory=dict)

    # ---- Metadata ----------------------------------------------------------------
    # dict[label_str → {"duration_ms": float, "read_count": int}]
    # "_total" key holds object-level totals
    extract_metadata: dict = field(default_factory=dict)

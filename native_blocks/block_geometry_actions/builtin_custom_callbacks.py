"""
builtin_custom_callbacks.py — pre-built callbacks for common derived geometry data.

CALLBACK CONTRACT
    func(instance, action_record, geometry_context) -> None      (return value ignored)

A callback MUTATES the instance. Where it stores the result decides what the result IS:

    instance.<domain>.custom["name"] = arr     per-element, len == domain count
                                               → can be written straight back to the geometry
    instance.derived["name"] = anything         CSR pairs, dicts, scalars, strings
                                               → never writable as an attribute

`geometry_context` is provided for callbacks that need to write attributes or edit
topology. Pure-numpy callbacks ignore it.
"""

from .helpers_computed import (
    build_face_face_neighbors_csr,
    build_vert_face_neighbors_csr,
    build_vert_vert_neighbors_csr,
    compute_edge_length,
    compute_face_center,
)
from .helpers_serialize import (
    DERIVED_KEY_SERIALIZED,
    apply_serialized_geometry,
    serialize_geometry,
)

# ==============================================================================================================================
# PER-ELEMENT RESULTS  →  domain.custom  (geometry-writable)
# ==============================================================================================================================

def cb_edge_length(instance, action_record, geometry_context) -> None:
    """
    Per-edge Euclidean length → instance.edge.custom["edge_length"]  (n_edges,) float32
    Requires: MET.VERTEX.CO, MET.EDGE.VERTICES
    """
    instance.edge.custom["edge_length"] = compute_edge_length(
        instance.vertex.co,
        instance.edge.vertices,
    )


def cb_face_center(instance, action_record, geometry_context) -> None:
    """
    Per-face centroid → instance.face.custom["face_center"]  (n_faces, 3) float32
    Requires: MET.VERTEX.CO, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    """
    instance.face.custom["face_center"] = compute_face_center(
        instance.vertex.co,
        instance.face.loop_start,
        instance.face.loop_total,
        instance.corner.vertex_index,
    )


# ==============================================================================================================================
# CSR ADJACENCY  →  instance.derived  (not attribute-writable)
#
#   idx, off = instance.derived["face_face_neighbors"]
#   neighbors_of_face_i = idx[off[i] : off[i + 1]]
# ==============================================================================================================================

def cb_vert_vert_neighbors(instance, action_record, geometry_context) -> None:
    """
    Vertex-vertex adjacency (edge-connected) → instance.derived["vert_vert_neighbors"]
    Requires: MET.VERTEX.CO, MET.EDGE.VERTICES
    """
    instance.derived["vert_vert_neighbors"] = build_vert_vert_neighbors_csr(
        instance.edge.vertices,
        instance.vertex.co.shape[0],
    )


def cb_vert_face_neighbors(instance, action_record, geometry_context) -> None:
    """
    Vertex-face adjacency → instance.derived["vert_face_neighbors"]
    Requires: MET.VERTEX.CO, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    """
    instance.derived["vert_face_neighbors"] = build_vert_face_neighbors_csr(
        instance.face.loop_start,
        instance.face.loop_total,
        instance.corner.vertex_index,
        instance.vertex.co.shape[0],
    )


def cb_face_face_neighbors(instance, action_record, geometry_context) -> None:
    """
    Face-face adjacency (shared edge) → instance.derived["face_face_neighbors"]
    Requires: MET.EDGE.VERTICES, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL,
              MET.CORNER.VERTEX_INDEX  (face count taken from instance.face.count)
    """
    instance.derived["face_face_neighbors"] = build_face_face_neighbors_csr(
        instance.edge.vertices,
        instance.face.loop_start,
        instance.face.loop_total,
        instance.corner.vertex_index,
        instance.face.count,
    )


# Legacy alias kept so existing declarations keep importing successfully.
_cb_face_face_neighbors = cb_face_face_neighbors


# ==============================================================================================================================
# SERIALIZATION  →  instance.derived["serialized_geometry"]
#
# Intended for a socket link between two machines: machine A runs cb_serialize_geometry
# and ships instance.derived["serialized_geometry"]; machine B stages that string on its
# instance and runs cb_deserialize_geometry to replace its local geometry.
# The socket/server layer itself is out of scope for this block.
# ==============================================================================================================================

def cb_serialize_geometry(instance, action_record, geometry_context) -> None:
    """
    Serialize the whole datablock (topology + every named attribute) into a string at
    instance.derived["serialized_geometry"].

    Works for mesh and curve geometry. Raises for unsupported attribute types.
    """
    instance.derived[DERIVED_KEY_SERIALIZED] = serialize_geometry(
        geometry_context.data,
        geometry_context.geometry_type,
    )


def cb_deserialize_geometry(instance, action_record, geometry_context) -> None:
    """
    Replace the object's geometry with the string staged at
    instance.derived["serialized_geometry"], custom attributes included.

    Requires Object Mode and read_source=ORIGINAL (writing to an evaluated cage is
    meaningless). Raises for a missing / malformed / mismatched payload.
    """
    serialized = (instance.derived or {}).get(DERIVED_KEY_SERIALIZED)
    if not serialized:
        raise RuntimeError(
            f"instance.derived['{DERIVED_KEY_SERIALIZED}'] is empty — stage the serialized "
            f"string on the instance before running cb_deserialize_geometry."
        )
    if geometry_context.is_edit_mode:
        raise RuntimeError("Deserialization requires Object Mode.")

    apply_serialized_geometry(
        geometry_context.data,
        serialized,
        geometry_context.geometry_type,
    )

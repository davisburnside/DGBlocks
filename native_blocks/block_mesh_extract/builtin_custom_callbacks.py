
"""
builtin_custom_callbacks.py — pre-built callbacks for common derived mesh data.

CALLBACK CONTRACT
    func(instance, action_record) -> None      (return value ignored)

A callback MUTATES the instance. Where it stores the result decides what the result IS:

    instance.<domain>.custom["name"] = arr     per-element, len == domain count
                                               → can be written straight back to the mesh
    instance.derived["name"] = anything        CSR pairs, dicts, scalars, matrices
                                               → never writable to a mesh

Use `action_record` only to append extra Mesh_Action_Op_Record entries if you want
finer-grained timing than the one op record the framework already creates for you.

Round-trip example — compute per-face data, then write it as a FACE attribute:

    attr_face_center = MET.FACE.CUSTOM_ATTRIBUTE("face_center", data_type="FLOAT_VECTOR")

    Numpy_Mesh_Action_Declaration(
        label            = "face centers",
        read_attributes  = [MET.VERTEX.CO, MET.FACE.LOOP_START,
                            MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX],
        callbacks        = [cb_face_center],          # → instance.face.custom["face_center"]
        write_attributes = [attr_face_center],        # same key, written back to the mesh
        read_source      = Enum_Read_Source.ORIGINAL,
    )
"""

from .helpers_computed import (
    build_face_face_neighbors_csr,
    build_vert_face_neighbors_csr,
    build_vert_vert_neighbors_csr,
    compute_edge_length,
    compute_face_center,
)

# ==============================================================================================================================
# PER-ELEMENT RESULTS  →  domain.custom  (mesh-writable)
# ==============================================================================================================================

def cb_edge_length(instance, action_record) -> None:
    """
    Per-edge Euclidean length → instance.edge.custom["edge_length"]  (n_edges,) float32
    Requires: MET.VERTEX.CO, MET.EDGE.VERTICES
    Writable as: MET.EDGE.CUSTOM_ATTRIBUTE("edge_length", data_type="FLOAT")
    """
    instance.edge.custom["edge_length"] = compute_edge_length(
        instance.vertex.co,
        instance.edge.vertices,
    )


def cb_face_center(instance, action_record) -> None:
    """
    Per-face centroid → instance.face.custom["face_center"]  (n_faces, 3) float32
    Requires: MET.VERTEX.CO, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    Writable as: MET.FACE.CUSTOM_ATTRIBUTE("face_center", data_type="FLOAT_VECTOR")
    """
    instance.face.custom["face_center"] = compute_face_center(
        instance.vertex.co,
        instance.face.loop_start,
        instance.face.loop_total,
        instance.corner.vertex_index,
    )


# ==============================================================================================================================
# CSR ADJACENCY  →  instance.derived  (not mesh-writable)
#
#   idx, off = instance.derived["face_face_neighbors"]
#   neighbors_of_face_i = idx[off[i] : off[i + 1]]
# ==============================================================================================================================

def cb_vert_vert_neighbors(instance, action_record) -> None:
    """
    Vertex-vertex adjacency (edge-connected) → instance.derived["vert_vert_neighbors"]
    Requires: MET.VERTEX.CO, MET.EDGE.VERTICES
    """
    instance.derived["vert_vert_neighbors"] = build_vert_vert_neighbors_csr(
        instance.edge.vertices,
        instance.vertex.co.shape[0],
    )


def cb_vert_face_neighbors(instance, action_record) -> None:
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


def cb_face_face_neighbors(instance, action_record) -> None:
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

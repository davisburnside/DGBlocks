
"""
callbacks.py — Pre-built callback functions for standard derived mesh attributes.

These callbacks wrap the pure functions in helpers_computed.py and follow the
Mesh_Extract_Target callback contract:

    func signature: func(instance: RTC_Mesh_Extract_Instance) -> any
    result stored in: instance.custom_attribute_arrays[attr_name]

Usage in hook_get_mesh_extract_targets:

    from native_blocks.block_mesh_extract.callbacks import (
        cb_edge_length,
        cb_face_center,
        cb_vert_vert_neighbors,
        cb_vert_face_neighbors,
        cb_face_face_neighbors,
    )

    Mesh_Extract_Target(
        object_name     = "Cube",
        read_attributes = [MET.VERTEX.CO, MET.EDGE.VERTICES, ...],
        callbacks       = {
            "face_face_neighbors":  cb_face_face_neighbors,
            "coplanar_group_id":    _my_planarity_callback,
        },
    )

CSR callbacks store a (indices, offsets) tuple under their key:

    idx, off = instance.custom_attribute_arrays["face_face_neighbors"]
    # neighbors of face i:
    neighbors = idx[off[i] : off[i+1]]

Recommended canonical key names for each pre-built callback:
    "edge_length"          → np.ndarray (n_edges,)        float32
    "face_center"          → np.ndarray (n_faces, 3)      float32
    "vert_vert_neighbors"  → (indices: np.ndarray, offsets: np.ndarray)
    "vert_face_neighbors"  → (indices: np.ndarray, offsets: np.ndarray)
    "face_face_neighbors"  → (indices: np.ndarray, offsets: np.ndarray)

Required read_attributes for each callback are documented per-function below.
"""

from .helpers_computed import (
    build_face_face_neighbors_csr,
    build_vert_face_neighbors_csr,
    build_vert_vert_neighbors_csr,
    compute_edge_length,
    compute_face_center,
)


# ==============================================================================================================================
# SCALAR / VECTOR COMPUTED ATTRIBUTES
# ==============================================================================================================================

def cb_edge_length(instance):
    """
    Compute per-edge Euclidean length.

    Required read_attributes: MET.VERTEX.CO, MET.EDGE.VERTICES
    Returns: np.ndarray (n_edges,) float32
    """
    return compute_edge_length(instance.vertex_co, instance.edge_vertices)


def cb_face_center(instance):
    """
    Compute mean vertex position (centroid) per face.

    Required read_attributes:
        MET.VERTEX.CO, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    Returns: np.ndarray (n_faces, 3) float32
    """
    return compute_face_center(
        instance.vertex_co,
        instance.face_loop_start,
        instance.face_loop_total,
        instance.corner_vertex_index,
    )


# ==============================================================================================================================
# CSR NEIGHBOR CALLBACKS
# Each returns a (indices, offsets) tuple stored under a single key.
# ==============================================================================================================================

def cb_vert_vert_neighbors(instance):
    """
    Build CSR vertex-vertex adjacency (vertices connected by a shared edge).

    Required read_attributes: MET.VERTEX.CO, MET.EDGE.VERTICES
    Returns: (indices: np.ndarray, offsets: np.ndarray)
        Neighbors of vertex i:
            idx, off = instance.custom_attribute_arrays["vert_vert_neighbors"]
            neighbors = idx[off[i] : off[i+1]]
    """
    n_verts = instance.vertex_co.shape[0]
    return build_vert_vert_neighbors_csr(instance.edge_vertices, n_verts)


def cb_vert_face_neighbors(instance):
    """
    Build CSR vertex-face adjacency (which faces each vertex belongs to).

    Required read_attributes:
        MET.VERTEX.CO, MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    Returns: (indices: np.ndarray, offsets: np.ndarray)
        Face-neighbors of vertex i:
            idx, off = instance.custom_attribute_arrays["vert_face_neighbors"]
            faces = idx[off[i] : off[i+1]]
    """
    n_verts = instance.vertex_co.shape[0]
    return build_vert_face_neighbors_csr(
        instance.face_loop_start,
        instance.face_loop_total,
        instance.corner_vertex_index,
        n_verts,
    )


def cb_face_face_neighbors(instance):
    """
    Build CSR face-face adjacency (faces that share at least one edge).

    Required read_attributes:
        MET.FACE.NORMAL (for n_faces), MET.EDGE.VERTICES,
        MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL, MET.CORNER.VERTEX_INDEX
    Returns: (indices: np.ndarray, offsets: np.ndarray)
        Face-neighbors of face i:
            idx, off = instance.custom_attribute_arrays["face_face_neighbors"]
            neighbors = idx[off[i] : off[i+1]]
    """
    n_faces = instance.face_normal.shape[0]
    return build_face_face_neighbors_csr(
        instance.edge_vertices,
        instance.face_loop_start,
        instance.face_loop_total,
        instance.corner_vertex_index,
        n_faces,
    )

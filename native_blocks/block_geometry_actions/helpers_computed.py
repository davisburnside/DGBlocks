
"""
helpers_computed.py — Pure numpy computed-attribute functions for block_geometry_actions.

ARCHITECTURE CONTRACT
---------------------
Every function in this file is a *pure function*:
    - Arguments are only numpy arrays and Python scalars.
    - No bpy, no self, no class access, no global state.
    - All return values are numpy arrays (or tuples of numpy arrays for CSR pairs).

This makes every function a direct candidate for @njit decoration in a future step.
The wrapping pattern to use for NJIT is:

    # helpers_computed.py
    def compute_edge_length(vertex_co, edge_vertices):
        return _compute_edge_length_inner(vertex_co, edge_vertices)

    @njit
    def _compute_edge_length_inner(vertex_co, edge_vertices):
        ...

Until NJIT is added, the _inner suffix is optional — the outer wrapper is the public API
called by helpers.py.
"""

import numpy as np

# ==============================================================================================================================
# EDGE — COMPUTED
# ==============================================================================================================================

def compute_edge_length(
    vertex_co: np.ndarray,      # (n_verts, 3)  float32
    edge_vertices: np.ndarray,  # (n_edges, 2)  int32
) -> np.ndarray:                # (n_edges,)    float32
    """
    Euclidean length of each edge.
    Fully vectorized: no Python loops.
    """
    v0 = vertex_co[edge_vertices[:, 0]]   # (n_edges, 3)
    v1 = vertex_co[edge_vertices[:, 1]]   # (n_edges, 3)
    delta = v1 - v0                        # (n_edges, 3)
    return np.sqrt(np.einsum("ij,ij->i", delta, delta)).astype(np.float32)


# ==============================================================================================================================
# FACE — COMPUTED
# ==============================================================================================================================

def compute_face_center(
    vertex_co: np.ndarray,          # (n_verts, 3)     float32
    face_loop_start: np.ndarray,    # (n_faces,)       int32
    face_loop_total: np.ndarray,    # (n_faces,)       int32
    corner_vertex_index: np.ndarray # (n_corners,)     int32
) -> np.ndarray:                    # (n_faces, 3)     float32
    """
    Mean position of each face's vertices.
    Uses np.add.reduceat for a vectorized loop-free sum.

    Steps:
        1. Build a flat array of per-corner vertex positions ordered by face.
        2. reduceat-sum each face's slice.
        3. Divide by loop_total.
    """
    n_faces = face_loop_start.shape[0]

    # Gather vertex positions for all corners, in corner order
    corner_positions = vertex_co[corner_vertex_index]   # (n_corners, 3)

    # Sum per face using reduceat (requires corners sorted by face — they always are in Blender)
    face_position_sums = np.add.reduceat(corner_positions, face_loop_start.astype(np.intp), axis=0)
    # face_position_sums shape: (n_faces, 3) — but reduceat produces one row per unique start index

    # Divide by vertex count per face
    face_centers = face_position_sums / face_loop_total[:, np.newaxis].astype(np.float32)
    return face_centers.astype(np.float32)


# ==============================================================================================================================
# CSR NEIGHBOR BUILDERS
# ==============================================================================================================================

def build_vert_vert_neighbors_csr(
    edge_vertices: np.ndarray,  # (n_edges, 2)  int32
    n_verts: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a CSR (Compressed Sparse Row) representation of vertex-vertex adjacency.

    Returns
    -------
    indices : (n_edges * 2,) int32
        Flat concatenation of neighbor vertex indices for every vertex.
    offsets : (n_verts + 1,) int32
        offsets[i]:offsets[i+1] slices indices for vertex i's neighbors.

    Algorithm (fully vectorized):
        - From each undirected edge (a, b), emit both (a→b) and (b→a).
        - Sort by source vertex, stable sort to keep ordering deterministic.
        - Build offsets with np.bincount + np.cumsum.
    """
    # Both directions
    src = np.concatenate([edge_vertices[:, 0], edge_vertices[:, 1]]).astype(np.int32)
    dst = np.concatenate([edge_vertices[:, 1], edge_vertices[:, 0]]).astype(np.int32)

    # Sort by source vertex
    order = np.argsort(src, kind="stable")
    src_sorted = src[order]
    dst_sorted = dst[order]

    # Count neighbors per vertex
    counts = np.bincount(src_sorted, minlength=n_verts).astype(np.int32)

    # Build offsets: cumsum with a leading zero
    offsets = np.empty(n_verts + 1, dtype=np.int32)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])

    return dst_sorted, offsets


def build_vert_face_neighbors_csr(
    face_loop_start: np.ndarray,    # (n_faces,)   int32
    face_loop_total: np.ndarray,    # (n_faces,)   int32
    corner_vertex_index: np.ndarray,# (n_corners,) int32
    n_verts: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build CSR for vertex-face adjacency: which faces each vertex belongs to.

    Returns
    -------
    indices : (n_corners,) int32  — face index for each corner, sorted by vertex
    offsets : (n_verts + 1,) int32

    Uses np.repeat to expand face indices into corner space — fully vectorized,
    no uninitialized memory reads.
    """
    n_faces = face_loop_start.shape[0]

    # face_of_corner[i] = face index that owns corner i
    face_of_corner = np.repeat(np.arange(n_faces, dtype=np.int32), face_loop_total)

    # Sort by vertex index to build CSR
    vert_indices = corner_vertex_index   # (n_corners,) — the "source" vertex
    order = np.argsort(vert_indices, kind="stable")
    vert_sorted = vert_indices[order]
    face_sorted = face_of_corner[order]

    counts = np.bincount(vert_sorted, minlength=n_verts).astype(np.int32)

    offsets = np.empty(n_verts + 1, dtype=np.int32)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])

    return face_sorted, offsets


def build_face_face_neighbors_csr(
    edge_vertices: np.ndarray,          # (n_edges, 2)   int32
    face_loop_start: np.ndarray,        # (n_faces,)     int32
    face_loop_total: np.ndarray,        # (n_faces,)     int32
    corner_vertex_index: np.ndarray,    # (n_corners,)   int32
    n_faces: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build CSR for face-face adjacency: faces that share at least one edge.

    Algorithm (vectorized):
        1. Build edge→face map: for each corner edge (v_i, v_{i+1}), record (edge_key, face_idx).
        2. Group corner edges by canonical edge key (min, max pair as int64).
        3. Where two faces share an edge key → they are neighbors.

    Returns
    -------
    indices : (n_shared_edge_slots,) int32
    offsets : (n_faces + 1,) int32
    """
    n_corners = corner_vertex_index.shape[0]

    # --- Build corner edge keys ---
    # For each corner i in face f, the next corner in the face is:
    #   next_corner_within_face = (i - loop_start[f] + 1) % loop_total[f] + loop_start[f]
    # Vectorized via face_of_corner expansion (reuse the pattern from vert_face CSR)

    face_of_corner = _build_face_of_corner(face_loop_start, face_loop_total, n_corners)

    # Next corner index (wraps within face)
    within_face_idx = np.arange(n_corners, dtype=np.int32) - face_loop_start[face_of_corner]
    next_within = (within_face_idx + 1) % face_loop_total[face_of_corner]
    next_corner = face_loop_start[face_of_corner] + next_within

    # Corner edge: (vert_a, vert_b)
    vert_a = corner_vertex_index                 # (n_corners,)
    vert_b = corner_vertex_index[next_corner]    # (n_corners,)

    # Canonical edge key: pack (min, max) into int64
    edge_lo = np.minimum(vert_a, vert_b).astype(np.int64)
    edge_hi = np.maximum(vert_a, vert_b).astype(np.int64)
    # Use a large prime multiplier to avoid collisions for reasonable mesh sizes
    edge_key = edge_lo * 2_000_000_007 + edge_hi   # int64

    # --- Find shared edges ---
    # Sort corner edges by key
    order = np.argsort(edge_key, kind="stable")
    key_sorted  = edge_key[order]
    face_sorted = face_of_corner[order]

    # Find consecutive pairs with the same key → shared edge
    same_as_next = key_sorted[:-1] == key_sorted[1:]
    pair_mask = np.where(same_as_next)[0]   # indices into sorted arrays where pair starts

    face_i = face_sorted[pair_mask]
    face_j = face_sorted[pair_mask + 1]

    # Remove degenerate self-adjacency (shouldn't happen in valid meshes)
    valid = face_i != face_j
    face_i = face_i[valid]
    face_j = face_j[valid]

    # Both directions
    src = np.concatenate([face_i, face_j]).astype(np.int32)
    dst = np.concatenate([face_j, face_i]).astype(np.int32)

    # Sort by source face
    order2 = np.argsort(src, kind="stable")
    src2 = src[order2]
    dst2 = dst[order2]

    counts = np.bincount(src2.astype(np.int64), minlength=n_faces).astype(np.int32)
    offsets = np.empty(n_faces + 1, dtype=np.int32)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])

    return dst2, offsets


def _build_face_of_corner(
    face_loop_start: np.ndarray,    # (n_faces,) int32
    face_loop_total: np.ndarray,    # (n_faces,) int32
    n_corners: int,
) -> np.ndarray:                    # (n_corners,) int32
    """
    Vectorized expansion: face_of_corner[i] = index of the face that owns corner i.
    Uses np.repeat for a clean loop-free implementation.
    """
    n_faces = face_loop_start.shape[0]
    face_indices = np.arange(n_faces, dtype=np.int32)
    return np.repeat(face_indices, face_loop_total)

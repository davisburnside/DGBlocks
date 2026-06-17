
"""
helpers_computed.py — Pure numpy computed-attribute functions for block_mesh_extract.

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


# ==============================================================================================================================
# PLANARITY — CALLBACK-READY INNER FUNCTIONS
# These are designed to be called from a Mesh_Extract_Callback in a downstream block.
# The wrapping callback is thin; all computation lives here as a pure function.
# ==============================================================================================================================

def compute_coplanar_groups(
    face_normals: np.ndarray,       # (n_faces, 3)  float32
    face_areas: np.ndarray,         # (n_faces,)    float32
    face_face_neighbor_indices: np.ndarray,  # CSR indices
    face_face_neighbor_offsets: np.ndarray,  # CSR offsets
    vertex_co: np.ndarray,          # (n_verts, 3)  float32 — for self-planarity check
    face_loop_start: np.ndarray,    # (n_faces,)    int32
    face_loop_total: np.ndarray,    # (n_faces,)    int32
    corner_vertex_index: np.ndarray,# (n_corners,)  int32
    tolerance_deg: float = 1.0,
    min_area: float = 0.0001,
    self_planarity_threshold: float = 0.001,
) -> np.ndarray:                    # (n_faces,) int32 — group id per face, -1=invalid, -2=too small
    """
    Assign each face a coplanar group integer ID via scipy connected components.
    Returns a (n_faces,) int32 array.

    Special values:
        -1 : face is non-planar (NGon/quad self-planarity exceeds threshold)
        -2 : face area is below min_area

    Steps (vectorized except the walk step which is handled separately):
        1. Mark too-small faces as -2.
        2. For NGons/quads: SVD self-planarity check → mark non-planar as -1.
        3. Build face-pair adjacency filtered by normal-dot tolerance.
        4. scipy connected_components → integer group IDs.
        5. Overwrite group IDs for -1/-2 faces.
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components

    n_faces = face_normals.shape[0]
    group_ids = np.full(n_faces, -1, dtype=np.int32)

    # Step 1: too-small mask
    too_small = face_areas < min_area

    # Step 2: self-planarity check for polygons with > 3 corners
    non_planar = _check_ngon_self_planarity(
        vertex_co, face_loop_start, face_loop_total, corner_vertex_index,
        face_normals, threshold=self_planarity_threshold,
    )

    # Step 3: valid faces
    valid_mask = ~too_small & ~non_planar   # (n_faces,) bool

    # Step 4: Build face-pair list from CSR, filtered by normal tolerance and validity
    cos_threshold = np.cos(np.radians(tolerance_deg))

    # Expand CSR to (src, dst) edge list
    counts = np.diff(face_face_neighbor_offsets)
    src_faces = np.repeat(np.arange(n_faces, dtype=np.int32), counts)
    dst_faces = face_face_neighbor_indices

    # Keep only pairs where both faces are valid and normals agree
    both_valid = valid_mask[src_faces] & valid_mask[dst_faces]
    src_v = src_faces[both_valid]
    dst_v = dst_faces[both_valid]

    if src_v.size > 0:
        dots = np.einsum("ij,ij->i", face_normals[src_v], face_normals[dst_v])
        coplanar = dots >= cos_threshold
        src_c = src_v[coplanar]
        dst_c = dst_v[coplanar]
    else:
        src_c = src_v
        dst_c = dst_v

    # Step 5: connected components (only on valid faces, but graph uses full n_faces)
    if src_c.size > 0:
        weights = np.ones(src_c.shape[0], dtype=np.float32)
        graph = csr_matrix((weights, (src_c, dst_c)), shape=(n_faces, n_faces))
        _, labels = connected_components(graph, directed=False, connection="weak")
        group_ids[valid_mask] = labels[valid_mask].astype(np.int32)
    else:
        # Each valid face is its own group
        label_counter = 0
        valid_indices = np.where(valid_mask)[0]
        group_ids[valid_indices] = np.arange(len(valid_indices), dtype=np.int32)

    # Overwrite special faces
    group_ids[non_planar] = -1
    group_ids[too_small]  = -2

    # Re-index groups to 0..N (remove gaps caused by masking)
    group_ids = _reindex_group_ids(group_ids)

    return group_ids


def _check_ngon_self_planarity(
    vertex_co: np.ndarray,
    face_loop_start: np.ndarray,
    face_loop_total: np.ndarray,
    corner_vertex_index: np.ndarray,
    face_normals: np.ndarray,
    threshold: float,
) -> np.ndarray:   # (n_faces,) bool — True = non-planar
    """
    For each face with > 3 corners, check whether all its vertices lie within
    `threshold` units of the face's plane (defined by its normal and first vertex).

    Triangles are always planar by definition → always False.

    Vectorized for faces of the same loop_total using np.unique batching.
    Falls back to a Python loop only for sizes that appear rarely (<=2 faces).
    """
    n_faces = face_normals.shape[0]
    non_planar = np.zeros(n_faces, dtype=bool)

    # Only test faces with more than 3 corners
    ngon_mask = face_loop_total > 3
    if not ngon_mask.any():
        return non_planar

    ngon_indices = np.where(ngon_mask)[0]
    unique_sizes = np.unique(face_loop_total[ngon_indices])

    for size in unique_sizes:
        size_mask = (face_loop_total == size) & ngon_mask
        face_idx = np.where(size_mask)[0]   # (m,)
        m = face_idx.shape[0]

        # Gather corner indices: (m, size)
        starts = face_loop_start[face_idx]   # (m,)
        offsets_local = np.arange(size, dtype=np.int32)[np.newaxis, :]  # (1, size)
        corner_idx = starts[:, np.newaxis] + offsets_local               # (m, size)
        vert_idx = corner_vertex_index[corner_idx]                        # (m, size)
        positions = vertex_co[vert_idx]                                   # (m, size, 3)

        # Plane origin = first vertex, normal = face_normals[face_idx]
        origins = positions[:, 0, :]                                      # (m, 3)
        normals = face_normals[face_idx]                                  # (m, 3)

        # Distance of each vertex from the plane: dot(v - origin, normal)
        # positions shape (m, size, 3), origins shape (m, 3)
        delta = positions - origins[:, np.newaxis, :]                    # (m, size, 3)
        dist = np.einsum("msj,mj->ms", delta, normals)                   # (m, size)
        max_dev = np.abs(dist).max(axis=1)                               # (m,)

        non_planar[face_idx] = max_dev > threshold

    return non_planar


def _reindex_group_ids(group_ids: np.ndarray) -> np.ndarray:
    """
    Remap positive group IDs to a contiguous 0..N range.
    Negative sentinels (-1, -2) are preserved as-is.
    """
    positive_mask = group_ids >= 0
    if not positive_mask.any():
        return group_ids

    result = group_ids.copy()
    positive_ids = group_ids[positive_mask]

    unique_ids, inverse = np.unique(positive_ids, return_inverse=True)
    new_ids = np.arange(len(unique_ids), dtype=np.int32)
    result[positive_mask] = new_ids[inverse]

    return result


def compute_coplanar_boundaries(
    group_ids: np.ndarray,          # (n_faces,)  int32
    face_face_neighbor_indices: np.ndarray,
    face_face_neighbor_offsets: np.ndarray,
    edge_vertices: np.ndarray,      # (n_edges, 2) int32
    face_loop_start: np.ndarray,
    face_loop_total: np.ndarray,
    corner_vertex_index: np.ndarray,
    n_faces: int,
) -> dict:
    """
    For each coplanar group, find all boundary edge walks in order.

    A boundary edge of group G is any edge where:
        - Exactly one adjacent face belongs to G (exterior boundary), OR
        - The edge separates group G from a different positive group (inter-group boundary).

    Edges that border the mesh boundary (is_boundary — adjacent to only 1 face total)
    are included in the same walk logic.

    Returns
    -------
    dict[group_id (int) → list[list[int]]]
        Outer boundary walk is always first (largest by edge count).
        Each walk is a list of edge indices in walk order, starting with the
        lowest-index boundary edge of that walk.

    NOTE: The walk step (traverse_boundary_walk) is a Python loop — it cannot be
    trivially vectorized. It is isolated in a separate function for future NJIT conversion.
    """
    n_corners = corner_vertex_index.shape[0]
    face_of_corner = _build_face_of_corner(face_loop_start, face_loop_total, n_corners)

    # Build corner → edge index map using the same canonical key trick
    corner_edge_indices = _build_corner_to_edge_map(
        edge_vertices, face_loop_start, face_loop_total, corner_vertex_index, face_of_corner
    )

    # For each corner edge, determine if it's a boundary of its group
    # A corner edge (c_i, c_j) is a group boundary if:
    #   - Its face belongs to a positive group, AND
    #   - Its neighboring face (if any) belongs to a different group (or there is no neighbor)

    boundaries: dict[int, list[list[int]]] = {}
    unique_groups = np.unique(group_ids[group_ids >= 0])

    for gid in unique_groups:
        group_face_mask = group_ids == gid
        boundary_edges = _find_group_boundary_edges(
            gid, group_ids, edge_vertices, face_of_corner, corner_edge_indices,
            face_loop_start, face_loop_total, corner_vertex_index,
        )
        if len(boundary_edges) == 0:
            boundaries[int(gid)] = []
            continue
        walks = _walk_all_boundaries(boundary_edges, edge_vertices)
        boundaries[int(gid)] = walks

    return boundaries


def _build_corner_to_edge_map(
    edge_vertices: np.ndarray,
    face_loop_start: np.ndarray,
    face_loop_total: np.ndarray,
    corner_vertex_index: np.ndarray,
    face_of_corner: np.ndarray,
) -> np.ndarray:   # (n_corners,) int32 — edge index for corner i's leading edge
    """
    For each corner i, find the index of the edge that connects
    corner_vertex_index[i] to the next corner in the face.
    Uses the canonical edge-key hash to look up into edge_vertices.
    """
    n_corners = corner_vertex_index.shape[0]
    n_faces = face_loop_start.shape[0]

    within_face_idx = np.arange(n_corners, dtype=np.int32) - face_loop_start[face_of_corner]
    next_within = (within_face_idx + 1) % face_loop_total[face_of_corner]
    next_corner = face_loop_start[face_of_corner] + next_within

    vert_a = corner_vertex_index
    vert_b = corner_vertex_index[next_corner]

    # Build lookup: canonical edge key → edge index
    ev_lo = np.minimum(edge_vertices[:, 0], edge_vertices[:, 1]).astype(np.int64)
    ev_hi = np.maximum(edge_vertices[:, 0], edge_vertices[:, 1]).astype(np.int64)
    ev_key = ev_lo * 2_000_000_007 + ev_hi

    # Corner edge keys
    c_lo = np.minimum(vert_a, vert_b).astype(np.int64)
    c_hi = np.maximum(vert_a, vert_b).astype(np.int64)
    c_key = c_lo * 2_000_000_007 + c_hi

    # Sort ev_key and use searchsorted
    sort_order = np.argsort(ev_key, kind="stable")
    ev_key_sorted = ev_key[sort_order]
    ev_idx_sorted = np.arange(len(edge_vertices), dtype=np.int32)[sort_order]

    positions = np.searchsorted(ev_key_sorted, c_key)
    positions = np.clip(positions, 0, len(ev_key_sorted) - 1)
    corner_edge_indices = ev_idx_sorted[positions]

    return corner_edge_indices.astype(np.int32)


def _find_group_boundary_edges(
    gid: int,
    group_ids: np.ndarray,
    edge_vertices: np.ndarray,
    face_of_corner: np.ndarray,
    corner_edge_indices: np.ndarray,
    face_loop_start: np.ndarray,
    face_loop_total: np.ndarray,
    corner_vertex_index: np.ndarray,
) -> np.ndarray:   # 1D int32 of edge indices
    """
    Return the set of unique edge indices that form the boundary of group `gid`.
    Vectorized: uses per-edge face-count logic to find boundary edges.
    """
    n_faces = group_ids.shape[0]
    n_corners = corner_edge_indices.shape[0]

    # Corners belonging to faces in group gid
    face_in_group = (group_ids == gid)
    corner_in_group = face_in_group[face_of_corner]   # (n_corners,) bool

    group_edge_indices = corner_edge_indices[corner_in_group]   # edges touched by group
    unique_group_edges, counts = np.unique(group_edge_indices, return_counts=True)

    # An edge is on the boundary if it is touched by exactly 1 corner within the group
    # (2 corners = interior edge shared by two group faces)
    boundary_edge_mask = counts == 1
    return unique_group_edges[boundary_edge_mask].astype(np.int32)


def _walk_all_boundaries(
    boundary_edge_indices: np.ndarray,  # (m,) int32
    edge_vertices: np.ndarray,          # (n_edges, 2) int32
) -> list[list[int]]:
    """
    Walk all boundary loops for a coplanar group.

    Builds a vertex→next-edge adjacency for the boundary subgraph, then
    traverses each connected loop starting from the lowest edge index.
    Returns list of walks; outer boundary (most edges) is first.

    NOTE: This function contains a Python loop (the walk traversal).
    It is intentionally isolated here for future NJIT replacement.
    All pre-processing above uses numpy; only the actual pointer-chasing is Python.
    """
    be = boundary_edge_indices
    be_verts = edge_vertices[be]   # (m, 2)

    # Build adjacency: vertex → list of (neighbor_vertex, edge_index)
    # We need to traverse, so Python dicts are unavoidable here
    adj: dict[int, list[tuple[int, int]]] = {}
    for i in range(len(be)):
        edge_idx = int(be[i])
        va, vb = int(be_verts[i, 0]), int(be_verts[i, 1])
        adj.setdefault(va, []).append((vb, edge_idx))
        adj.setdefault(vb, []).append((va, edge_idx))

    visited_edges: set[int] = set()
    walks: list[list[int]] = []

    # Walk starting from each unvisited edge, lowest index first
    sorted_edges = sorted(int(e) for e in be)

    for start_edge in sorted_edges:
        if start_edge in visited_edges:
            continue

        walk = _traverse_boundary_walk(start_edge, edge_vertices, adj, visited_edges)
        if walk:
            walks.append(walk)

    # Sort: largest walk (outer boundary) first
    walks.sort(key=len, reverse=True)
    return walks


def _traverse_boundary_walk(
    start_edge: int,
    edge_vertices: np.ndarray,
    adj: dict,
    visited_edges: set,
) -> list[int]:
    """
    Single boundary walk starting from start_edge.
    Follows the chain of boundary edges until the loop closes.

    NJIT NOTE: To port this to numba, replace the dict/set with flat arrays
    and integer-based pointer logic. The adjacency structure can be expressed
    as a CSR pair (indices, offsets) over boundary vertices only.
    """
    walk: list[int] = []
    current_edge = start_edge
    va, vb = int(edge_vertices[current_edge, 0]), int(edge_vertices[current_edge, 1])
    current_vert = vb
    prev_vert = va

    max_steps = len(adj) * 2 + 2   # safety limit

    for _ in range(max_steps):
        if current_edge in visited_edges:
            break
        visited_edges.add(current_edge)
        walk.append(current_edge)

        # Find next edge: neighbor of current_vert that isn't the edge we came from
        neighbors = adj.get(current_vert, [])
        next_edge = None
        next_vert = None
        for (nv, ne) in neighbors:
            if ne != current_edge and nv != prev_vert:
                next_edge = ne
                next_vert = nv
                break

        if next_edge is None:
            break

        prev_vert = current_vert
        current_vert = next_vert
        current_edge = next_edge

    return walk

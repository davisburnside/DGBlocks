import numpy as np
import time

from .feature_numba_function_wrapper import safe_numba_decorator
from .block_constants import Enum_Numba_Decorator_Configs

# Example 1: Basic function with safe_numba_decorator
@safe_numba_decorator(njit=True, parallel=False)
def calculate_distance_matrix(points):
    """
    Calculate distance matrix between all pairs of 3D points.
    This is a computationally intensive task that benefits from numba.
    
    Args:
        points: Numpy array of shape (N, 3) containing N 3D points
    
    Returns:
        Numpy array of shape (N, N) containing pairwise distances
    """
    n = len(points)
    result = np.zeros((n, n), dtype=np.float64)
    
    # Double loop - perfect for numba optimization
    for i in range(n):
        for j in range(n):
            if i != j:
                # Compute Euclidean distance
                dx = points[i, 0] - points[j, 0]
                dy = points[i, 1] - points[j, 1]
                dz = points[i, 2] - points[j, 2]
                result[i, j] = (dx*dx + dy*dy + dz*dz) ** 0.5
    
    return result

# Example 2: Using preset configs
@safe_numba_decorator(**Enum_Numba_Decorator_Configs.PARALLEL_JIT.value)
def calculate_normals(vertices, faces):
    """
    Calculate vertex normals for a mesh.
    
    Args:
        vertices: Numpy array of shape (V, 3) containing vertex positions
        faces: Numpy array of shape (F, 3) containing face indices
    
    Returns:
        Numpy array of shape (V, 3) containing normalized vertex normals
    """
    v_count = len(vertices)
    normals = np.zeros((v_count, 3), dtype=np.float32)
    
    # For each face
    for face_idx in range(len(faces)):
        # Get vertex indices for this face
        v0, v1, v2 = faces[face_idx]
        
        # Get vertex positions
        p0 = vertices[v0]
        p1 = vertices[v1]
        p2 = vertices[v2]
        
        # Compute face normal using cross product
        edge1 = p1 - p0
        edge2 = p2 - p0
        face_normal = np.cross(edge1, edge2)
        
        # Add face normal to each vertex normal
        normals[v0] += face_normal
        normals[v1] += face_normal
        normals[v2] += face_normal
    
    # Normalize all vertex normals
    for i in range(v_count):
        n = normals[i]
        length = np.sqrt(n[0]*n[0] + n[1]*n[1] + n[2]*n[2])
        if length > 0:
            normals[i] = n / length
    
    return normals

def demo_with_random_data(n_points=1000):
    """
    Demonstrate numba acceleration with random points.
    
    Args:
        n_points: Number of random 3D points to generate
    """
    # Generate random points
    points = np.random.random((n_points, 3)).astype(np.float32)
    
    # Run distance calculation
    t0 = time.time()
    distance_matrix = calculate_distance_matrix(points)
    elapsed = time.time() - t0
    
    print(f"Calculated {n_points}x{n_points} distance matrix in {elapsed:.3f} seconds")
    
    # Generate a simple mesh (cube)
    vertices = np.array([
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]
    ], dtype=np.float32)
    
    faces = np.array([
        [0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [0, 3, 7], [0, 7, 4], [1, 2, 6], [1, 6, 5]
    ], dtype=np.int32)
    
    # Calculate normals
    t0 = time.time()
    normals = calculate_normals(vertices, faces)
    elapsed = time.time() - t0
    
    print(f"Calculated vertex normals in {elapsed:.6f} seconds")
    print("Vertex normals:")
    for i, normal in enumerate(normals):
        print(f"  Vertex {i}: {normal}")
    
    return distance_matrix, normals
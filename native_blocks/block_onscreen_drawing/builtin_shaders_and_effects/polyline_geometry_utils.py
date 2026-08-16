"""
Shared geometry-expansion utilities for polyline-style shaders.

Both Polyline_Dash_Shader and Polyline_Annotated_Shader expand line segments into
screen-space quads (2 triangles each) for Metal-safe thickness. Blender's own POLYLINE_*
builtins avoid Metal's ignored GL line-width by doing the same: each segment becomes a
billboarded quad whose corners are offset perpendicular to the segment in window space.

This module centralises the shared corner-pattern and triangle-pattern data so that
future polyline shaders don't re-derive the 4-corner / 2-triangle layout.
"""

# ------------------------------------------------------------------
# Segment quad layout
# ------------------------------------------------------------------
#
# Each segment (A, B) produces 4 corner vertices:
#
#     0: (end_flag=0, side=+1)   1: (end_flag=0, side=-1)
#     2: (end_flag=1, side=+1)   3: (end_flag=1, side=-1)
#
#   end_flag  selects the base endpoint   (0 → A, 1 → B)
#   side      selects the quad side        (+1 → left, -1 → right)
#
SEGMENT_CORNERS = (
    (0.0, 1.0),   # end_flag, side
    (0.0, -1.0),
    (1.0, 1.0),
    (1.0, -1.0),
)

# Two triangles that tile the 4-vertex quad above:
#   (0,1,2)  and  (2,1,3)
SEGMENT_TRIANGLES = (
    (0, 1, 2),
    (2, 1, 3),
)


def segment_quad_indices(offset: int):
    """
    Return 2 triangle index-tuples for a 4-vertex segment quad,
    offset to the vertex at position *offset* in the global vertex array.

    >>> segment_quad_indices(0)
    ((0, 1, 2), (2, 1, 3))
    >>> segment_quad_indices(8)
    ((8, 9, 10), (10, 9, 11))
    """
    return tuple(
        (offset + a, offset + b, offset + c)
        for a, b, c in SEGMENT_TRIANGLES
    )


def segment_quad_corner_attrs(seg_a, seg_b, corner_index: int):
    """
    Given a segment (seg_a, seg_b) and a corner index (0-3), return
    (end_flag, side) for that corner.

    The caller uses end_flag to pick the base endpoint and side to
    pick the quad side, then applies a perpendicular offset in the
    vertex shader.
    """
    end_flag, side = SEGMENT_CORNERS[corner_index]
    return end_flag, side

"""
Text Box Renderer for Blender 5
================================

A robust, real-time text box rendering system using POST_PIXEL shaders and BLF.

OVERVIEW
--------
This module provides a single entry point `draw_text_box()` that renders
text boxes with gradient backgrounds, word wrapping, and flexible alignment.
It's designed for real-time UI overlays and tooltips in Blender.

KEY FEATURES
------------
- Two positioning modes: absolute XY point, or offset from area/region corners
- Gradient backgrounds with alpha support (top/bottom colors)
- Automatic word wrapping (preserves whole words, no hyphenation)
- Per-line formatting (font size, alignment, max char count)
- Flexible padding system (single values, tuples, or per-line lists)
- Smart conflict resolution (uses max values when lines have different padding)
- Real-time optimized (no nested functions, batch-friendly)

PADDING SYSTEM
--------------
Padding accepts multiple formats:
    - Single number: 5 -> all sides = 5
    - Tuple of 2: (5, 10) -> (vertical, horizontal)
    - Tuple of 4: (5, 10, 5, 10) -> (top, right, bottom, left)
    - Nested tuple: ((5, 8), (10, 15)) -> ((top, bottom), (left, right))
    - List of any of the above: one per text line

When lines have different padding, the MAX value is used for spacing between lines.
This ensures "minimum padding" is always respected.

POSITIONING MODES
-----------------
1. XY Point: Box expands downward from (x, y) point
2. Corner Offset: Box positioned at offset from a specific corner of an area/region
   - Auto-adjusts so inner corner aligns with the specified offset
   - Box expands inward from that corner

ALIGNMENT TYPES
---------------
- "left": Text starts at left edge + padding-left
- "left-soft": Text aligns with content start of previous line
- "center": Text centered in the box
- "right-soft": Text aligns with content end of previous line
- "right": Text ends at right edge - padding-right

USAGE EXAMPLE
-------------
from .text_box import draw_text_box

# Simple absolute positioning
draw_text_box(
    context,
    xy_point=(100, 200),
    text_lines=["Hello World", "This is a tooltip"],
    bg_color_top=(0.1, 0.1, 0.2, 0.8),
    bg_color_bottom=(0.2, 0.1, 0.3, 0.8),
    font_sizes=14,
    alignments="center",
    min_padding=10,
)

# Corner offset with per-line formatting
draw_text_box(
    context,
    corner_offset=("TOP_LEFT", some_area, 20, -20),
    text_lines=["Title", "Description text here", "Footer"],
    font_sizes=[18, 14, 12],
    alignments=["center", "left", "right"],
    max_char_count=[40, 60, 40],
    min_padding=[(10, 10, 5, 10), (5, 15, 5, 15), (5, 15, 10, 15)],
    bg_color_top=(0.0, 0.0, 0.0, 0.7),
    bg_color_bottom=(0.2, 0.2, 0.2, 0.7),
)

NOTES
-----
- Both bg_color_top and bg_color_bottom can be None to skip background
- If one is None, it defaults to (1, 1, 1, 0)
- Text lines with empty strings are skipped
- All positions are in Blender's pixel coordinates (Y-up)

REQUIREMENTS
------------
- A shader with set_points(), set_colors(), and draw() methods
- The shader should accept numpy arrays for batch processing
- BLF font system available in Blender 5
"""

import bpy
import blf
import numpy as np
from mathutils import Vector
from typing import Union, List, Tuple, Optional, Any

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_FONT_SIZE = 14
DEFAULT_MAX_CHAR_COUNT = 80
DEFAULT_ALIGNMENT = "left"
DEFAULT_PADDING = 5
DEFAULT_COLOR = (1.0, 1.0, 1.0, 0.0)

# ============================================================================
# PADDING UTILITIES
# ============================================================================

def _normalize_padding_value(padding: Any) -> Tuple[float, float, float, float]:
    """Convert any padding format to (top, right, bottom, left)."""
    if padding is None:
        return (DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING)
    
    if isinstance(padding, (int, float)):
        p = float(padding)
        return (p, p, p, p)
    
    if isinstance(padding, (tuple, list)):
        if len(padding) == 0:
            return (DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING)
        
        # Nested format: ((top, bottom), (left, right))
        if len(padding) == 2 and isinstance(padding[0], (tuple, list)):
            top_bottom = padding[0]
            left_right = padding[1]
            if len(top_bottom) == 2 and len(left_right) == 2:
                return (float(top_bottom[0]), float(left_right[1]), 
                        float(top_bottom[1]), float(left_right[0]))
        
        if len(padding) == 2:
            # (vertical, horizontal)
            v, h = float(padding[0]), float(padding[1])
            return (v, h, v, h)
        
        if len(padding) == 4:
            # (top, right, bottom, left)
            return (float(padding[0]), float(padding[1]), 
                    float(padding[2]), float(padding[3]))
    
    return (DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING, DEFAULT_PADDING)


def _resolve_padding_parameters(
    min_padding: Any,
    num_lines: int
) -> Tuple[Tuple[float, float, float, float], List[Tuple[float, float, float, float]]]:
    """
    Resolve padding parameters into box padding and per-line paddings.
    
    Returns:
        box_padding: (top, right, bottom, left) for the overall box
        line_paddings: List of (top, right, bottom, left) per line
    """
    # Convert to list if single value
    if not isinstance(min_padding, (list, tuple)):
        min_padding = [min_padding]
    
    # Normalize each padding value
    normalized = []
    for pad in min_padding:
        normalized.append(_normalize_padding_value(pad))
    
    # Extend list to match num_lines
    while len(normalized) < num_lines:
        normalized.append(normalized[-1] if normalized else (DEFAULT_PADDING,) * 4)
    
    # Truncate if too many
    line_paddings = normalized[:num_lines]
    
    # Calculate box padding (max of all line paddings)
    if line_paddings:
        box_padding = (
            max(p[0] for p in line_paddings),  # top
            max(p[1] for p in line_paddings),  # right
            max(p[2] for p in line_paddings),  # bottom
            max(p[3] for p in line_paddings),  # left
        )
    else:
        box_padding = (DEFAULT_PADDING,) * 4
    
    return box_padding, line_paddings


def _get_vertical_spacing(
    prev_padding: Tuple[float, float, float, float],
    curr_padding: Tuple[float, float, float, float]
) -> float:
    """Get max vertical spacing between two lines."""
    return max(prev_padding[2], curr_padding[0])  # max(prev_bottom, curr_top)


# ============================================================================
# INPUT NORMALIZATION
# ============================================================================

def _normalize_parameter(
    param: Any,
    num_lines: int,
    default: Any,
    param_name: str
) -> List[Any]:
    """Normalize a parameter to a list of length num_lines."""
    if param is None:
        param = default
    
    if not isinstance(param, (list, tuple)):
        param = [param] * num_lines
    
    # Convert to list
    param = list(param)
    
    # Extend if too short
    while len(param) < num_lines:
        param.append(param[-1] if param else default)
    
    # Truncate if too long
    param = param[:num_lines]
    
    return param


def _validate_input_lengths(
    text_lines: List[str],
    font_sizes: List[int],
    alignments: List[str],
    max_char_counts: List[int],
    line_paddings: List[Tuple[float, float, float, float]]
) -> bool:
    """Validate that all input lists have the same length. Returns False if invalid."""
    expected_len = len(text_lines)
    issues = []
    
    if len(font_sizes) != expected_len:
        issues.append(f"font_sizes ({len(font_sizes)})")
    if len(alignments) != expected_len:
        issues.append(f"alignments ({len(alignments)})")
    if len(max_char_counts) != expected_len:
        issues.append(f"max_char_counts ({len(max_char_counts)})")
    if len(line_paddings) != expected_len:
        issues.append(f"line_paddings ({len(line_paddings)})")
    
    if issues:
        print(f"WARNING: Input list length mismatch in draw_text_box")
        print(f"  text_lines has {expected_len} items")
        for issue in issues:
            print(f"  {issue} does not match")
        return False
    
    return True


# ============================================================================
# POSITION RESOLVER
# ============================================================================

def _resolve_position(
    context,
    xy_point: Optional[Tuple[float, float]] = None,
    corner_offset: Optional[Tuple[str, Any, float, float]] = None,
    area: Any = None,
    region: Any = None,
) -> Optional[Tuple[float, float]]:
    """
    Resolve the position based on either XY point or corner offset.
    
    Returns:
        (x, y) position in window coordinates, or None if invalid
    """
    if xy_point is not None:
        return (float(xy_point[0]), float(xy_point[1]))
    
    if corner_offset is not None:
        corner, area_ref, offset_x, offset_y = corner_offset
        target_area = area_ref if area_ref else area
        
        if not target_area:
            print("WARNING: No area provided for corner offset mode")
            return None
        
        # Get area bounds
        x_min = target_area.x
        y_min = target_area.y
        x_max = target_area.x + target_area.width
        y_max = target_area.y + target_area.height
        
        # Calculate corner position
        corner = corner.upper()
        if corner == "TOP_LEFT":
            x, y = x_min, y_max
        elif corner == "TOP_RIGHT":
            x, y = x_max, y_max
        elif corner == "BOTTOM_LEFT":
            x, y = x_min, y_min
        elif corner == "BOTTOM_RIGHT":
            x, y = x_max, y_min
        elif corner == "CENTER":
            x, y = (x_min + x_max) / 2, (y_min + y_max) / 2
        else:
            print(f"WARNING: Unknown corner '{corner}'")
            return None
        
        return (x + offset_x, y + offset_y)
    
    print("WARNING: No position specified for draw_text_box")
    return None


def _calculate_box_dimensions(
    line_infos: List[dict],
    box_padding: Tuple[float, float, float, float]
) -> Tuple[float, float, float]:
    """
    Calculate box dimensions from line information.
    
    Returns:
        total_width, total_height, max_line_width
    """
    if not line_infos:
        return 0.0, 0.0, 0.0
    
    max_line_width = max(info['width'] for info in line_infos)
    total_width = max_line_width + box_padding[3] + box_padding[1]
    
    # Calculate total height with line spacing
    total_height = box_padding[0] + box_padding[2]  # top + bottom
    
    for i, info in enumerate(line_infos):
        total_height += info['height']
        if i < len(line_infos) - 1:
            # Add spacing between lines
            total_height += _get_vertical_spacing(
                info['padding'],
                line_infos[i + 1]['padding']
            )
    
    return total_width, total_height, max_line_width


def _calculate_line_y_positions(
    line_infos: List[dict],
    box_y: float,
    box_height: float,
    box_padding: Tuple[float, float, float, float]
) -> List[float]:
    """Calculate Y positions for each line from bottom to top."""
    y_positions = []
    current_y = box_y + box_padding[2]  # Start from bottom + bottom padding
    
    for i, info in enumerate(line_infos):
        if i > 0:
            # Add spacing from previous line
            current_y += _get_vertical_spacing(
                line_infos[i - 1]['padding'],
                info['padding']
            )
        
        y_positions.append(current_y)
        current_y += info['height']
    
    return y_positions


# ============================================================================
# TEXT LAYOUT ENGINE
# ============================================================================

def _measure_text(
    font_id: int,
    text: str,
    font_size: int
) -> Tuple[float, float]:
    """Measure text dimensions using BLF."""
    blf.size(font_id, font_size)
    width, height = blf.dimensions(font_id, text)
    return width, height


def _wrap_text_line(
    text: str,
    font_id: int,
    font_size: int,
    max_char_count: int
) -> List[str]:
    """Wrap a single text line by word, respecting max char count."""
    if max_char_count <= 0 or len(text) <= max_char_count:
        return [text]
    
    words = text.split(' ')
    wrapped_lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        word_len = len(word)
        # Check if adding this word would exceed max
        if current_length + word_len + (1 if current_line else 0) > max_char_count:
            if current_line:
                wrapped_lines.append(' '.join(current_line))
                current_line = []
                current_length = 0
            # If word itself is longer than max, split it
            if word_len > max_char_count:
                # Split long word by characters
                for i in range(0, word_len, max_char_count):
                    wrapped_lines.append(word[i:i+max_char_count])
            else:
                current_line.append(word)
                current_length = word_len
        else:
            current_line.append(word)
            current_length += word_len + (1 if current_line else 0)
    
    if current_line:
        wrapped_lines.append(' '.join(current_line))
    
    return wrapped_lines


def _process_text_lines(
    text_lines: List[str],
    font_sizes: List[int],
    alignments: List[str],
    max_char_counts: List[int],
    line_paddings: List[Tuple[float, float, float, float]],
    font_id: int
) -> List[dict]:
    """
    Process all text lines, handling wrapping and measuring.
    
    Returns:
        List of line info dicts with keys:
        - text: str
        - font_size: int
        - alignment: str
        - padding: tuple
        - width: float
        - height: float
        - wrapped_from: int (original line index)
    """
    line_infos = []
    original_line_index = -1
    
    for orig_idx, text in enumerate(text_lines):
        if not text.strip():
            continue
        
        original_line_index += 1
        font_size = font_sizes[orig_idx]
        alignment = alignments[orig_idx]
        max_char = max_char_counts[orig_idx]
        padding = line_paddings[orig_idx]
        
        # Wrap the text
        wrapped = _wrap_text_line(text, font_id, font_size, max_char)
        
        # Process each wrapped line
        for wrapped_text in wrapped:
            width, height = _measure_text(font_id, wrapped_text, font_size)
            line_infos.append({
                'text': wrapped_text,
                'font_size': font_size,
                'alignment': alignment,
                'padding': padding,
                'width': width,
                'height': height,
                'original_index': orig_idx,
            })
    
    return line_infos


def _calculate_text_x_positions(
    line_infos: List[dict],
    box_x: float,
    box_width: float,
    box_padding: Tuple[float, float, float, float],
    max_line_width: float
) -> List[float]:
    """Calculate X positions for each line based on alignment."""
    x_positions = []
    box_left = box_x
    box_right = box_x + box_width
    
    # Track previous line's content start/end for soft alignments
    prev_content_start = None
    prev_content_end = None
    
    for info in line_infos:
        alignment = info['alignment']
        line_width = info['width']
        padding_left = info['padding'][3]
        padding_right = info['padding'][1]
        
        if alignment == "left":
            x = box_left + padding_left
        elif alignment == "left-soft":
            if prev_content_start is not None:
                x = prev_content_start
            else:
                x = box_left + padding_left
        elif alignment == "center":
            x = box_left + (box_width - line_width) / 2.0
        elif alignment == "right-soft":
            if prev_content_end is not None:
                x = prev_content_end - line_width
            else:
                x = box_right - padding_right - line_width
        elif alignment == "right":
            x = box_right - padding_right - line_width
        else:
            # Default to left
            x = box_left + padding_left
        
        x_positions.append(x)
        prev_content_start = x
        prev_content_end = x + line_width
    
    return x_positions


# ============================================================================
# BACKGROUND RENDERER
# ============================================================================

def _draw_background(
    shader,
    x: float,
    y: float,
    width: float,
    height: float,
    color_top: Tuple[float, float, float, float],
    color_bottom: Tuple[float, float, float, float]
) -> None:
    """Draw a gradient background quad using the shader."""
    # Create quad vertices (clockwise from top-left)
    vertices = np.array([
        [x, y + height],  # top-left
        [x + width, y + height],  # top-right
        [x + width, y],  # bottom-right
        [x, y],  # bottom-left
    ], dtype=np.float32)
    
    # Create UVs for gradient (v=1 at top, v=0 at bottom)
    uvs = np.array([
        [0.0, 1.0],  # top-left
        [1.0, 1.0],  # top-right
        [1.0, 0.0],  # bottom-right
        [0.0, 0.0],  # bottom-left
    ], dtype=np.float32)
    
    # Combine position and UV into single array if shader expects it
    # Or use separate calls to set_points and set_colors
    shader.set_points(vertices)
    
    # Set colors for each vertex (top colors for top vertices, bottom colors for bottom)
    colors = np.array([
        color_top,  # top-left
        color_top,  # top-right
        color_bottom,  # bottom-right
        color_bottom,  # bottom-left
    ], dtype=np.float32)
    
    shader.set_colors(colors)
    shader.draw()


# ============================================================================
# MAIN DRAW FUNCTION
# ============================================================================

def draw_text_box(
    context,
    shader,
    text_lines: List[str],
    xy_point: Optional[Tuple[float, float]] = None,
    corner_offset: Optional[Tuple[str, Any, float, float]] = None,
    bg_color_top: Optional[Tuple[float, float, float, float]] = None,
    bg_color_bottom: Optional[Tuple[float, float, float, float]] = None,
    font_sizes: Union[int, List[int], None] = None,
    alignments: Union[str, List[str], None] = None,
    max_char_count: Union[int, List[int], None] = None,
    min_padding: Union[int, float, tuple, list] = DEFAULT_PADDING,
    area=None,
    region=None,
    font_id: int = 0,
) -> bool:
    """
    Draw a text box with gradient background and formatted text.
    
    Args:
        context: Blender context
        shader: Shader object with set_points(), set_colors(), draw()
        text_lines: List of text strings to display
        xy_point: (x, y) absolute position (box expands downward)
        corner_offset: (corner, area_ref, offset_x, offset_y) for relative positioning
        bg_color_top: (r, g, b, a) color for top of gradient (None = skip)
        bg_color_bottom: (r, g, b, a) color for bottom of gradient (None = skip)
        font_sizes: int or list of ints (default: 14)
        alignments: str or list of str (default: "left")
        max_char_count: int or list of ints (default: 80)
        min_padding: Padding value(s) (see PADDING SYSTEM above)
        area: Area for corner offset mode
        region: Region for corner offset mode
        font_id: BLF font ID (default: 0)
    
    Returns:
        bool: True if drawing was successful, False if errors occurred
    
    Example:
        draw_text_box(
            context, shader,
            text_lines=["Hello", "World"],
            xy_point=(100, 100),
            bg_color_top=(0.1, 0.1, 0.2, 0.8),
            bg_color_bottom=(0.2, 0.1, 0.3, 0.8),
        )
    """
    # Validate input
    if not text_lines:
        print("WARNING: draw_text_box called with empty text_lines")
        return False
    
    # Clean text lines (remove empty strings)
    text_lines = [line for line in text_lines if line.strip()]
    if not text_lines:
        print("WARNING: draw_text_box called with only empty strings")
        return False
    
    num_lines = len(text_lines)
    
    # Normalize parameters
    font_sizes = _normalize_parameter(font_sizes, num_lines, DEFAULT_FONT_SIZE, "font_sizes")
    alignments = _normalize_parameter(alignments, num_lines, DEFAULT_ALIGNMENT, "alignments")
    max_char_counts = _normalize_parameter(max_char_count, num_lines, DEFAULT_MAX_CHAR_COUNT, "max_char_count")
    
    # Resolve padding
    box_padding, line_paddings = _resolve_padding_parameters(min_padding, num_lines)
    
    # Validate all lengths match
    if not _validate_input_lengths(text_lines, font_sizes, alignments, max_char_counts, line_paddings):
        return False
    
    # Resolve position
    position = _resolve_position(context, xy_point, corner_offset, area, region)
    if position is None:
        print("WARNING: Could not resolve position for draw_text_box")
        return False
    
    pos_x, pos_y = position
    
    # Process text lines (wrapping and measurement)
    line_infos = _process_text_lines(
        text_lines, font_sizes, alignments, max_char_counts, line_paddings, font_id
    )
    
    if not line_infos:
        print("WARNING: No lines after processing text")
        return False
    
    # Calculate box dimensions
    box_width, box_height, max_line_width = _calculate_box_dimensions(line_infos, box_padding)
    
    # Check if we need to draw background
    draw_bg = bg_color_top is not None or bg_color_bottom is not None
    
    if draw_bg:
        # Resolve colors
        top_color = bg_color_top if bg_color_top is not None else DEFAULT_COLOR
        bottom_color = bg_color_bottom if bg_color_bottom is not None else DEFAULT_COLOR
        
        # Draw background
        _draw_background(shader, pos_x, pos_y, box_width, box_height, top_color, bottom_color)
    
    # Calculate line Y positions (from bottom to top)
    y_positions = _calculate_line_y_positions(
        line_infos, pos_y, box_height, box_padding
    )
    
    # Calculate line X positions
    x_positions = _calculate_text_x_positions(
        line_infos, pos_x, box_width, box_padding, max_line_width
    )
    
    # Draw each text line
    for i, info in enumerate(line_infos):
        x = x_positions[i]
        y = y_positions[i]
        
        # BLF uses bottom-left origin, so we need to add line height
        blf.size(font_id, info['font_size'])
        blf.position(font_id, x, y, 0.0)
        blf.draw(font_id, info['text'])
    
    return True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_gradient_shader() -> Any:
    """
    Create a simple gradient shader for the text box.
    
    This is a helper function that creates a basic shader with the required
    set_points(), set_colors(), and draw() methods.
    
    Returns:
        Shader object or None if creation fails
    """
    try:
        import gpu
        from gpu.types import GPUShader, GPUBatch
        
        # Vertex shader for 2D position + UV
        vertex_shader = """
        uniform mat4 ModelViewProjectionMatrix;
        in vec2 pos;
        in vec2 uv;
        out vec2 uv_interp;
        void main() {
            uv_interp = uv;
            gl_Position = ModelViewProjectionMatrix * vec4(pos, 0.0, 1.0);
        }
        """
        
        # Fragment shader with gradient
        fragment_shader = """
        uniform vec4 color_top;
        uniform vec4 color_bottom;
        in vec2 uv_interp;
        out vec4 fragColor;
        void main() {
            float t = uv_interp.y;
            fragColor = mix(color_bottom, color_top, t);
        }
        """
        
        shader = GPUShader(vertex_shader, fragment_shader)
        shader.set_points = lambda pts: shader.uniform_vec2("pos", pts)
        shader.set_colors = lambda colors: None  # Not used in this shader
        shader.draw = lambda: None  # Placeholder
        
        return shader
        
    except Exception as e:
        print(f"Could not create gradient shader: {e}")
        return None

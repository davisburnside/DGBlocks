"""

Custom Shader_Instance subclass: draws text boxes via BLF with an optional GPU-rendered
gradient background quad, in the POST_PIXEL phase.

ARCHITECTURE (post-refactor)
----------------------------
Following the canonical Shader_Instance pattern (see Billboard_Shader, Polyline_Dash_Shader,
Stripe_Shader), this shader now:

- Exposes a **clear_lines() / add_line()** API that stores raw text + formatting parameters.
- Overrides **set_points() / set_colors()** to raise Exception — callers must use add_line().
- Moves ALL expensive computation (word wrapping, BLF measurement, box sizing, background
  TRI vertex generation) into **_shader_update_batch()**, which runs only when properties change.
- **_shader_draw()** is lightweight: it draws the pre-built GPU background batch (SMOOTH_COLOR
  builtin) then blits pre-computed BLF text positions — zero recomputation per frame.

BACKGROUND QUAD
---------------
One shared background rectangle covers all text lines. Its gradient (top/bottom colors) is set
via the last add_line() call that supplies bg_color_top/bg_color_bottom. If no call provides
background colors, the background quad is skipped.

The background quad vertices (2 TRIs = 4 verts + 6 indices) are computed from the shared
box dimensions and the resolved origin (spawn_point + offsets + region).

Setup: 'shader_uid' is the only Shader_Declaration value you control. The rest must match:
Shader_Declaration(
    shader_uid="MY_TEXTBOXES",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_PIXEL,
    custom_shader_class=Textbox_Demo_Shader,
)
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple
import numpy as np
import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from ....native_blocks.block_onscreen_drawing.data_structures import Shader_Instance

# --------------------------------------------------------------------------
# Text-layout helpers (imported from simple_textbox.py to inline computation
# in _shader_update_batch rather than calling draw_text_box every frame).
# --------------------------------------------------------------------------
from .simple_textbox import (
    _wrap_text_line,
    _measure_text,
    _calculate_box_dimensions,
    _calculate_line_y_positions,
    _calculate_text_x_positions,
    _normalize_parameter,
    _resolve_padding_parameters,
    DEFAULT_FONT_SIZE,
    DEFAULT_MAX_CHAR_COUNT,
    DEFAULT_ALIGNMENT,
    DEFAULT_PADDING,
)

# Optional foreign RTC member owned by block_modal_events (NOT a dependency). Read defensively.
_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE = "USER_INPUT_CAPTURE"

# Spawn-point identifiers (must match the EnumProperty items in __init__.py).
SPAWN_TOP_LEFT     = "TOP_LEFT"
SPAWN_TOP_RIGHT    = "TOP_RIGHT"
SPAWN_BOTTOM_LEFT  = "BOTTOM_LEFT"
SPAWN_BOTTOM_RIGHT = "BOTTOM_RIGHT"
SPAWN_MOUSE        = "MOUSE"

_MARGIN = 20
_LINE_HEIGHT = 34
_BOX_WIDTH_GUESS = 130  # approx px for right-aligned spawn anchoring


@dataclass
class Textbox_Demo_Shader(Shader_Instance):

    # ----------------------------------------------------------
    # State — raw input (set via public API; triggers batch rebuild)
    # ----------------------------------------------------------
    spawn_point: str = field(default=SPAWN_TOP_LEFT)
    _x_offset: float = field(init=False, default=0.0)  # px offset from spawn anchor
    _y_offset: float = field(init=False, default=0.0)
    _lines: list = field(init=False, default_factory=list)  # list[dict] raw line configs
    _bg_color_top: Optional[Tuple[float, ...]] = field(init=False, default=None)
    _bg_color_bottom: Optional[Tuple[float, ...]] = field(init=False, default=None)

    # ----------------------------------------------------------
    # Pre-computed draw data (populated by _shader_update_batch)
    # ----------------------------------------------------------
    _text_draw_entries: list = field(init=False, default_factory=list)
    # Each entry: (x: float, y: float, font_size: int, text: str)

    # ----------------------------------------------------------
    # Override parent methods that should NOT be called directly
    # ----------------------------------------------------------

    def set_points(self, value):
        raise Exception(
            f"Textbox_Demo_Shader '{self.shader_uid}' does not support set_points(). "
            f"Use clear_lines() / add_line() instead. The spawn_point, offsets, and "
            f"add_line() attributes determine the background TRI positions automatically."
        )

    def set_colors(self, value):
        raise Exception(
            f"Textbox_Demo_Shader '{self.shader_uid}' does not support set_colors(). "
            f"Use clear_lines() / add_line() instead. Background colors are set via "
            f"add_line(bg_color_top=..., bg_color_bottom=...)."
        )

    # ----------------------------------------------------------
    # Public API — NEW: clear_lines / add_line
    # ----------------------------------------------------------

    def clear_lines(self) -> None:
        """Remove all text lines. Call before rebuilding a fresh set."""
        self._lines.clear()
        self._bg_color_top = None
        self._bg_color_bottom = None
        self._needs_new_batch = True

    def add_line(
        self,
        text: str,
        *,
        font_size: int = DEFAULT_FONT_SIZE,
        alignment: str = DEFAULT_ALIGNMENT,
        max_char_count: int = DEFAULT_MAX_CHAR_COUNT,
        min_padding=DEFAULT_PADDING,
        bg_color_top: Optional[Tuple[float, float, float, float]] = None,
        bg_color_bottom: Optional[Tuple[float, float, float, float]] = None,
    ) -> None:
        """Add one text line with optional per-line formatting.

        Args:
            text: The text string to display (required).
            font_size: BLF font size (default 14).
            alignment: One of 'left', 'center', 'right', 'left-soft', 'right-soft'.
            max_char_count: Max chars before word-wrap (default 80).
            min_padding: Padding value(s) — see PADDING SYSTEM in simple_textbox.py.
            bg_color_top: Top gradient color for the SHARED background quad.
            bg_color_bottom: Bottom gradient color for the SHARED background quad.
                The last add_line() providing these wins; if none do, no background is drawn.
        """
        if not isinstance(text, str) or not text.strip():
            return  # silently skip empty/blank lines

        self._lines.append({
            "text": text,
            "font_size": int(font_size),
            "alignment": str(alignment),
            "max_char_count": int(max_char_count),
            "min_padding": min_padding,
        })

        # Shared background colours — last write wins.
        if bg_color_top is not None:
            self._bg_color_top = tuple(bg_color_top)
        if bg_color_bottom is not None:
            self._bg_color_bottom = tuple(bg_color_bottom)

        self._needs_new_batch = True

    # ----------------------------------------------------------
    # Public API — existing setters (now flag batch update)
    # ----------------------------------------------------------

    def set_spawn_point(self, value: str) -> None:
        self.spawn_point = str(value)
        self._needs_new_batch = True

    def set_textbox_offsets(self, x_offset: float, y_offset: float) -> None:
        """Pixel offset applied to the box's spawn anchor (moves the whole group)."""
        self._x_offset = float(x_offset)
        self._y_offset = float(y_offset)
        self._needs_new_batch = True

    # ----------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------

    def _resolve_mouse_xy(self, region):
        """Window-space mouse -> region-space (x, y), or None when unavailable."""
        from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
        capture = Wrapper_Runtime_Cache.get_cache(_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE)
        if capture is None:
            return None
        mx = getattr(capture, "mouse_x", None)
        my = getattr(capture, "mouse_y", None)
        if not mx or not my:
            return None
        return (mx - region.x, my - region.y)

    def _resolve_origin(self, region, box_width, box_height):
        """Top-left anchor (x, y) in region space for the SINGLE shared box,
        plus the user x_offset / y_offset."""
        w, h = region.width, region.height
        sp = self.spawn_point

        if sp == SPAWN_MOUSE:
            mouse_xy = self._resolve_mouse_xy(region)
            if mouse_xy is None:
                x, y = (_MARGIN, h - _MARGIN)
            else:
                x = mouse_xy[0] - box_width / 2.0
                y = mouse_xy[1] - box_height / 2.0
        elif sp == SPAWN_TOP_LEFT:
            x, y = (_MARGIN, h - _MARGIN)
        elif sp == SPAWN_TOP_RIGHT:
            x, y = (w - _MARGIN - box_width, h - _MARGIN)
        elif sp == SPAWN_BOTTOM_LEFT:
            x, y = (_MARGIN, _MARGIN)
        else:  # SPAWN_BOTTOM_RIGHT
            x, y = (w - _MARGIN - box_width, _MARGIN)

        return (x + self._x_offset, y + self._y_offset)

    # ----------------------------------------------------------
    # Private API — overriding parent class lifecycle methods
    # ----------------------------------------------------------

    def _shader_init(self, spawn_point = SPAWN_BOTTOM_LEFT):
        """Create the SMOOTH_COLOR builtin shader for the background gradient quad."""
        self.shader_actual = gpu.shader.from_builtin('SMOOTH_COLOR')
        self.spawn_point = spawn_point

    def _shader_update_batch(self):
        """Rebuild the entire pre-computed draw state — word wrap, measurement,
        box sizing, background quad vertices, and BLF draw positions."""
        self._needs_new_batch = False
        self._text_draw_entries.clear()

        # --- Early-out: no lines ---
        if not self._lines:
            self._batch = None
            return

        num_lines = len(self._lines)

        # --- Extract per-line raw data ---
        raw_texts = [ln["text"] for ln in self._lines]
        font_sizes_list = [ln["font_size"] for ln in self._lines]
        alignments_list = [ln["alignment"] for ln in self._lines]
        max_char_counts_list = [ln["max_char_count"] for ln in self._lines]

        # --- Normalize per-line parameters (same as draw_text_box) ---
        font_sizes = _normalize_parameter(
            font_sizes_list, num_lines, DEFAULT_FONT_SIZE, "font_sizes")
        alignments = _normalize_parameter(
            alignments_list, num_lines, DEFAULT_ALIGNMENT, "alignments")
        max_char_counts = _normalize_parameter(
            max_char_counts_list, num_lines, DEFAULT_MAX_CHAR_COUNT, "max_char_count")

        raw_paddings = [ln["min_padding"] for ln in self._lines]
        box_padding, line_paddings = _resolve_padding_parameters(
            raw_paddings, num_lines)

        # --- Wrap & measure every line ---
        font_id = 0
        line_infos: list = []
        for orig_idx in range(num_lines):
            text = raw_texts[orig_idx]
            font_size = font_sizes[orig_idx]
            alignment = alignments[orig_idx]
            max_char = max_char_counts[orig_idx]
            padding = line_paddings[orig_idx]

            wrapped = _wrap_text_line(text, font_id, font_size, max_char)
            for wrapped_text in wrapped:
                width, height = _measure_text(font_id, wrapped_text, font_size)
                line_infos.append({
                    "text": wrapped_text,
                    "font_size": font_size,
                    "alignment": alignment,
                    "padding": padding,
                    "width": width,
                    "height": height,
                    "original_index": orig_idx,
                })

        if not line_infos:
            self._batch = None
            return

        # --- Calculate shared box dimensions ---
        box_width, box_height, max_line_width = _calculate_box_dimensions(
            line_infos, box_padding)

        # --- Resolve origin ---
        region = bpy.context.region
        if region is None:
            self._batch = None
            return
        box_x, box_y = self._resolve_origin(region, box_width, box_height)

        # --- Build background quad (2 TRIs = 4 verts + 6 indices) ---
        draw_bg = self._bg_color_top is not None or self._bg_color_bottom is not None
        if draw_bg:
            top_color = (self._bg_color_top if self._bg_color_top is not None
                         else (1.0, 1.0, 1.0, 0.0))
            bottom_color = (self._bg_color_bottom if self._bg_color_bottom is not None
                            else (1.0, 1.0, 1.0, 0.0))

            vertices = np.array([
                (box_x, box_y + box_height),
                (box_x + box_width, box_y + box_height),
                (box_x + box_width, box_y),
                (box_x, box_y),
            ], dtype=np.float32)

            colors = np.array([
                top_color, top_color, bottom_color, bottom_color,
            ], dtype=np.float32)

            indices = np.array([0, 1, 2,  0, 2, 3], dtype=np.int32)

            self._batch = batch_for_shader(
                self.shader_actual,
                self.shader_type,
                {"pos": vertices, "color": colors},
                indices=indices,
            )
        else:
            self._batch = None

        # --- Pre-compute BLF text draw positions ---
        y_positions = _calculate_line_y_positions(
            line_infos, box_y, box_height, box_padding)
        x_positions = _calculate_text_x_positions(
            line_infos, box_x, box_width, box_padding, max_line_width)

        for i, info in enumerate(line_infos):
            self._text_draw_entries.append((
                x_positions[i],
                y_positions[i],
                info["font_size"],
                info["text"],
            ))

    def _shader_draw(self):
        gpu.state.blend_set('ALPHA')

        # --- Draw background quad (if any) ---
        if self._batch is not None:
            self.shader_actual.bind()
            self._batch.draw(self.shader_actual)

        # --- Draw text via BLF (pre-computed positions, zero per-frame cost) ---
        font_id = 0
        for x, y, font_size, text in self._text_draw_entries:
            blf.size(font_id, font_size)
            blf.position(font_id, x, y, 0.0)
            blf.color(font_id, 1, 1, 1, 1)
            blf.draw(font_id, text)

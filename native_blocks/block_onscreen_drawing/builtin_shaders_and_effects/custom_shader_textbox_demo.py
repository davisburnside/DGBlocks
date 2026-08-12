"""

Custom Shader_Instance subclass: draws N demo text boxes in the POST_PIXEL phase.

This is a thin wrapper around the standalone draw_text_box() renderer in simple_textbox.py
(which uses BLF for glyphs). It exists so the text-box feature can participate in the pull-based
Shader_Instance lifecycle like any other example shader: the controlling code only sets a count
via set_textbox_count(); all drawing lives here, keeping the renderer independent of its control.

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
from typing import Any
import bpy

from ....native_blocks.block_onscreen_drawing.data_structures import Shader_Instance

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

    _count: int = field(init=False, default=1)
    _spawn_point: str = field(init=False, default=SPAWN_TOP_LEFT)

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_textbox_count(self, value: int) -> None:
        self._count = max(0, int(value))

    def set_spawn_point(self, value: str) -> None:
        self._spawn_point = str(value)

    # ----------------------------------------------------------
    # Private API, overriding parent class funcs

    def _shader_init(self):
        # No GPU program of our own — draw_text_box() handles all rendering via BLF.
        self.shader_actual = None

    def _shader_update_batch(self):
        # No batch geometry; text is drawn immediately in _shader_draw().
        self._needs_new_batch = False

    def _resolve_mouse_xy(self, region):
        """
        Window-space mouse -> region-space (x, y), or None when the foreign USER_INPUT_CAPTURE
        member is absent/idle or the mouse is outside this region. Never raises.
        """
        from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
        capture = Wrapper_Runtime_Cache.get_cache(_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE)
        if capture is None:
            return None
        mx = getattr(capture, "mouse_x", None)
        my = getattr(capture, "mouse_y", None)
        if not mx or not my:
            return None
        return (mx - region.x, my - region.y)

    def _resolve_origin(self, region, box_index):
        """Top-left anchor (x, y) in region space for text box `box_index`."""
        stack_offset = box_index * _LINE_HEIGHT
        w, h = region.width, region.height
        sp = self._spawn_point

        if sp == SPAWN_MOUSE:
            mouse_xy = self._resolve_mouse_xy(region)
            if mouse_xy is None:
                # Mouse capture unavailable — fall back to top-left rather than skipping.
                return (_MARGIN, h - _MARGIN - stack_offset)
            return (mouse_xy[0], mouse_xy[1] - stack_offset)

        if sp == SPAWN_TOP_LEFT:
            return (_MARGIN, h - _MARGIN - stack_offset)
        if sp == SPAWN_TOP_RIGHT:
            return (w - _MARGIN - _BOX_WIDTH_GUESS, h - _MARGIN - stack_offset)
        if sp == SPAWN_BOTTOM_LEFT:
            return (_MARGIN, _MARGIN + (self._count - 1 - box_index) * _LINE_HEIGHT)
        if sp == SPAWN_BOTTOM_RIGHT:
            return (w - _MARGIN - _BOX_WIDTH_GUESS,
                    _MARGIN + (self._count - 1 - box_index) * _LINE_HEIGHT)
        return (_MARGIN, h - _MARGIN - stack_offset)

    def _shader_draw(self):
        # Import here to keep the module's import graph identical to before (avoids any
        # import-time cost when the demo isn't used).
        from .simple_textbox import draw_text_box

        context = bpy.context
        region = context.region
        if region is None:
            return

        for i in range(self._count):
            xy = self._resolve_origin(region, i)
            draw_text_box(
                context,
                None,  # background quad drawing is disabled inside draw_text_box; shader unused
                text_lines=[f"Text Box #{i + 1}"],
                xy_point=xy,
                font_sizes=14,
                alignments="left",
                min_padding=6,
            )

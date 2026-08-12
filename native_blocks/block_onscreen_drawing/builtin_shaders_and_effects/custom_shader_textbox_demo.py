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
import bpy

from ....native_blocks.block_onscreen_drawing.data_structures import Shader_Instance
from .simple_textbox import draw_text_box


@dataclass
class Textbox_Demo_Shader(Shader_Instance):

    _count: int = field(init=False, default=1)

    # ----------------------------------------------------------
    # Public API, unique to this shader

    def set_textbox_count(self, value: int) -> None:
        self._count = max(0, int(value))

    # ----------------------------------------------------------
    # Private API, overriding parent class funcs

    def _shader_init(self):
        # No GPU program of our own — draw_text_box() handles all rendering via BLF.
        self.shader_actual = None

    def _shader_update_batch(self):
        # No batch geometry; text is drawn immediately in _shader_draw().
        self._needs_new_batch = False

    def _shader_draw(self):
        context = bpy.context
        region = context.region
        if region is None:
            return

        # Stack the boxes down the top-left corner of the region.
        line_height = 34
        for i in range(self._count):
            draw_text_box(
                context,
                None,  # background quad drawing is disabled inside draw_text_box; shader unused
                text_lines=[f"Text Box #{i + 1}"],
                xy_point=(20, region.height - 20 - i * line_height),
                font_sizes=14,
                alignments="left",
                min_padding=6,
            )

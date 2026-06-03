
import random
import sys
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...native_blocks.block_onscreen_drawing.feature_draw_handler_manager import Wrapper_Draw_Handlers

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Loggers, Block_RTC_Members, FLATYPUS_SHADER_DEFS

# ==============================================================================================================================
# OPERATOR HELPERS
# ==============================================================================================================================

def op_assembly_mode_on():
    """
    Register both shaders via set_state, then push initial geometry.
    Both shaders share (VIEW_3D, WINDOW, POST_VIEW) so a single Blender
    draw handler is created for the pair.
    """

    Wrapper_Draw_Handlers.set_state(FLATYPUS_SHADER_DEFS)

    simple2d = Wrapper_Draw_Handlers.get_shader("SIMPLE_2D")
    if simple2d is not None:
        simple2d.set_points([
            (-0.5, -0.5),
            ( 50, 100.5),
        ])
        simple2d.set_uniform("color", (1,1,1,1))



    # --- Simple TRIS: a coloured triangle near the origin ---
    tris = Wrapper_Draw_Handlers.get_shader("SIMPLE_TRIS")
    if tris is not None:
        tris.set_points([
            (-0.5, -0.5, 0.0),
            ( 0.5, -0.5, 0.0),
            ( 0.0,  0.5, 0.0),
        ])
        tris.set_colors([
            (1.0, 0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0, 1.0),
            (0.0, 0.0, 1.0, 1.0),
        ])


    # --- Billboard: one billboard quad at the world origin ---
    billboard_shader = Wrapper_Draw_Handlers.get_shader("BILLBOARD")
    if billboard_shader is not None:
        rf = random.uniform
        minf = -0.1
        maxf = 0.1
        points = [(rf(minf, maxf), rf(minf, maxf), rf(minf, maxf)) for _ in range(3)]
        colors = [(0.0, 0.0, 1.0, 1.0) for _ in points]
        sizes = [0.5 for _ in points]
        billboard_shader.set_points(points)
        billboard_shader.set_colors(colors)
        billboard_shader.set_billboard_sizes(sizes)


def op_assembly_mode_off():
    """Tear down all draw handlers and shaders."""
    Wrapper_Draw_Handlers.clear()

# ==============================================================================================================================
# OPERATOR
# ==============================================================================================================================

class DGBLOCKS_OT_Toggle_Assembly_Mode(bpy.types.Operator):
    bl_idname = "dgblocks.toggle_assembly_mode"
    bl_label = "Toggle Assembly Mode"
    bl_options = {"REGISTER"}

    action: bpy.props.StringProperty(default="ON")  # type: ignore  — "ON" or "OFF"

    def execute(self, context):
        if self.action == "ON":
            op_assembly_mode_on()
        elif self.action == "OFF":
            op_assembly_mode_off()

        for area in context.window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()

        return {"FINISHED"}

# ==============================================================================================================================
# UI PANEL
# ==============================================================================================================================

class DGBLOCKS_PT_Assembly_Mode_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_Assembly_Mode_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 0

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            "FLT-mode-debug",
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name="TOOL_SETTINGS",
        )

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        op_on = row.operator("dgblocks.toggle_assembly_mode", text="ON")
        op_on.action = "ON"
        op_off = row.operator("dgblocks.toggle_assembly_mode", text="OFF")
        op_off.action = "OFF"

# ==============================================================================================================================
# BLOCK DECLARATION
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module=sys.modules[__name__],
    block_id="block-flatypus-assembly-mode",
    block_dependencies=[
        "block-core",
        "block-onscreen-drawing",
    ],
    block_bpy_classes=[
        DGBLOCKS_OT_Toggle_Assembly_Mode,
        DGBLOCKS_PT_Assembly_Mode_Panel,
    ],
    block_loggers=Block_Loggers,
    block_RTC_members=Block_RTC_Members,
)

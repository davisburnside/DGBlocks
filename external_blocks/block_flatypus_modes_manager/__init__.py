
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
from ...native_blocks.block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Loggers, FLATYPUS_SHADER_DEFS

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# Top-level functions — auto-discovered by Wrapper_Hooks at registration time.
# ==============================================================================================================================

def hook_get_shader_definitions():

    return FLATYPUS_SHADER_DEFS


def hook_before_first_draw():
    """
    Push initial geometry to all shaders immediately after they are created.
    Called by Wrapper_Shader_Manager.rebuild_all_shaders() after all instances
    are live and is_enabled preferences have been restored.
    """
    simple2d = Wrapper_Shader_Manager.get_shader("SIMPLE_2D")
    if simple2d is not None:
        simple2d.set_points([
            (-0.5, -0.5),
            (50.0, 100.5),
        ])
        simple2d.set_uniform("color", (1, 1, 1, 1))

    tris = Wrapper_Shader_Manager.get_shader("SIMPLE_TRIS")
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

    billboard_shader = Wrapper_Shader_Manager.get_shader("BILLBOARD")
    if billboard_shader is not None:
        rf = random.uniform
        minf, maxf = -0.1, 0.1
        points = [(rf(minf, maxf), rf(minf, maxf), rf(minf, maxf)) for _ in range(3)]
        colors = [(0.0, 0.0, 1.0, 1.0) for _ in points]
        sizes  = [0.5 for _ in points]
        billboard_shader.set_points(points)
        billboard_shader.set_colors(colors)
        billboard_shader.set_billboard_sizes(sizes)


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
        # enable_drawing is owned by block_onscreen_drawing and drives the whole
        # rebuild cycle.  Toggling it here fires _cb_enable_drawing_changed which
        # calls rebuild_all_shaders() or clear_all_shaders() as appropriate.
        layout.prop(
            context.scene.dgblocks_onscreen_drawing_props,
            "enable_drawing",
            toggle=True,
        )


# ==============================================================================================================================
# BLOCK DECLARATION
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module=sys.modules[__name__],
    block_id="block-flatypus-assembly-mode",
    block_dependencies=[
        "block-core",
        "block-onscreen-draw",
    ],
    block_bpy_classes=[
        DGBLOCKS_PT_Assembly_Mode_Panel,
    ],
    block_loggers=Block_Loggers,
)

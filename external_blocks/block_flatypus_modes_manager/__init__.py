
import sys
import bpy
from .custom_shaders.helpers import populate_points  # type: ignore

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
from .common_declarations import Block_Loggers, FLATYPUS_SHADER_DEFS

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# Top-level functions — auto-discovered by Wrapper_Hooks at registration time.
# ==============================================================================================================================

def hook_get_shader_definitions():

    return FLATYPUS_SHADER_DEFS


def hook_before_first_draw():

    populate_points()

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

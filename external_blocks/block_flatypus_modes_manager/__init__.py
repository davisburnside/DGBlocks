
import random
import sys
import bpy
from .custom_shaders.helpers import populate_points  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_helpers.ui import ui_draw_block_panel_header

from ...native_blocks.block_timers.data_structures import Timer_Definition


# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_declarations import Block_Loggers
from .shader_declarations import FLATYPUS_SHADER_DEFS

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# Top-level functions — auto-discovered by Wrapper_Hooks at registration time.
# ==============================================================================================================================

def hook_get_shader_definitions():

    return FLATYPUS_SHADER_DEFS

def timer_call(aa):

    num = random.randint(0, 50)
    if num > 40:
        raise Exception(f"Exception_{num}")
    print(aa)


def hook_get_timer_definitions():

    return [
        Timer_Definition(
            timer_uid = "atimer",
            frequency = 0.5,
            callback = timer_call,
        )
    ]


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
        "block-timers",
    ],
    block_bpy_classes=[
        DGBLOCKS_PT_Assembly_Mode_Panel,
    ],
    block_loggers=Block_Loggers,
)

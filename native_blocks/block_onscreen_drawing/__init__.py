
import sys

import bpy # type: ignore
from typing import Optional


# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import block_core
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_constants import Block_Loggers, Block_RTC_Members
from .feature_draw_handler_manager import Wrapper_Draw_Handlers


# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-onscreen-drawing"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core"
]

# ==============================================================================================================================
# UI - Draw debugging panel
# ==============================================================================================================================

class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, _BLOCK_DECLARATION.block_id, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "FILE_3D")
        
    def draw(self, context):

        layout = self.layout
        all_rtc_draw_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)

        if not all_rtc_draw_handlers:
            layout.label(text="No active draw handlers", icon="INFO")
            return

        for (space, region, phase), handler_instance in all_rtc_draw_handlers.items():
            is_active = handler_instance._handle is not None
            shader_count = len(handler_instance.shaders)
            row = layout.row(align=True)
            row.label(text=f"{space.name} / {region} / {phase}")
            row.label(text=f"{shader_count} shader(s)")
            row.label(text="ON" if is_active else "OFF", icon="CHECKMARK" if is_active else "X")

# ==============================================================================================================================
# REQUIRED 
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__], # this __init__.py file
    block_id = "block-onscreen-draw", # unique block id
    block_dependencies = ["core-block"], # ids of blocks that this one depends on
    block_bpy_classes = [DGBLOCKS_PT_Debug_Drawing_Panel], # Blender-registerable classes
    block_feature_wrapper_classes = [Wrapper_Draw_Handlers],
    block_RTC_members = Block_RTC_Members,
    block_loggers = Block_Loggers,
)

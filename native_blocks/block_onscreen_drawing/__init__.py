
import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.generic_tools import force_redraw_ui
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
from .common_constants import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .feature_draw_handler_manager import Wrapper_Draw_Handlers


class DGBLOCKS_PG_Drawing_Props(bpy.types.PropertyGroup):
    """Container for block_onscreen_drawing persistent scene properties."""
    paceholder: bpy.props.IntProperty()  # type: ignore


class DGBLOCKS_OT_Toggle_Shader(bpy.types.Operator):
    bl_idname = "dgblocks.debug_toggle_shader"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    shader_uid: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):

        logger = get_logger(Block_Loggers.SHADER_BATCH_EVENTS)
        logger.info(f"toggle shader {self.shader_uid}")
        
        # _, shader_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", self.shader_uid)
        cached_shaders_dict = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        if self.shader_uid not in cached_shaders_dict:
            logger.error(f"Shader {self.shader_uid} not found")
            return {"FINISHED"}
        
        shader_instance = cached_shaders_dict[self.shader_uid]
        shader_instance.is_enabled = not shader_instance.is_enabled
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, cached_shaders_dict)
        force_redraw_ui(context)
        return {"FINISHED"}


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

            # Handler row
            row = layout.row(align=True)
            row.label(text=f"{space.name} / {region} / {phase}")
            row.label(text=f"{shader_count} shader(s)")
            row.label(text="ON" if is_active else "OFF", icon="CHECKMARK" if is_active else "X")

            # Per-shader telemetry rows (indented)
            for shader in handler_instance.shaders:
                box = layout.box()
                header_row = box.row(align=True)
                header_row.label(text=shader.shader_uid, icon="SHADING_RENDERED")
                op = header_row.operator("dgblocks.debug_toggle_shader", text = "ON" if shader.is_enabled else "OFF")
                op.shader_uid = shader.shader_uid
                # header_row.label(text="ON" if shader.is_enabled else "OFF")
                if shader.error_str is not None:
                    header_row.label(text="INVALID", icon="ERROR")
                stats_row = box.row(align=True)
                stats_row.label(text=f"Batches: {shader.batch_creation_count}  ({shader.batch_creation_duration_ms:.2f} ms last)")
                stats_row.label(text=f"Draw errors: {shader.draw_error_count}")

# ==============================================================================================================================
# REQUIRED 
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__], # this __init__.py file
    block_id = "block-onscreen-draw", # unique block id
    block_dependencies = ["core-block"], # ids of blocks that this one depends on
    block_bpy_classes = [
        DGBLOCKS_PG_Drawing_Props,
        DGBLOCKS_PT_Debug_Drawing_Panel,
        DGBLOCKS_OT_Toggle_Shader,
    ],
    block_feature_wrapper_classes = [Wrapper_Draw_Handlers],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_loggers = Block_Loggers,
)

def register_block_props():
    bpy.types.Scene.dgblocks_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Drawing_Props)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_drawing_props"):
        del bpy.types.Scene.dgblocks_drawing_props

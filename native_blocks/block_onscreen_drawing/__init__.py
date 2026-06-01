
import sys
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
from .common_constants import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .feature_draw_handler_manager import Wrapper_Draw_Handlers

# ==============================================================================================================================
# BL DATA — Shader is_enabled data mirror
# ==============================================================================================================================

def _callback_update_shader_is_enabled(self, context):
    """
    Propagate a UI-driven is_enabled toggle directly onto the live RTC Shader_Instance.
    The syncing flag prevents re-entrant loops when update_BL_with_mirrored_RTC_data
    is writing to the collection during a framework-initiated sync.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return
    shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
    if shaders is None:
        return
    shader = shaders.get(self.shader_uid)
    if shader is not None:
        shader.is_enabled = self.is_enabled


class DGBLOCKS_PG_Shader_Mirror(bpy.types.PropertyGroup):
    """
    One row per live Shader_Instance.  Mirrors the shader_uid (key) and
    is_enabled (toggle) fields so they survive saves, reloads, undo and redo.
    Analogous to DGBLOCKS_PG_Hook_Reference in block_core.
    """
    shader_uid: bpy.props.StringProperty(name="Shader UID")  # type: ignore
    is_enabled: bpy.props.BoolProperty(  # type: ignore
        default=True,
        name="Enabled",
        update=_callback_update_shader_is_enabled,
    )


class DGBLOCKS_PG_Drawing_Props(bpy.types.PropertyGroup):
    """Container for block_onscreen_drawing persistent scene properties."""
    managed_shaders: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror)  # type: ignore
    managed_shaders_selected_idx: bpy.props.IntProperty()  # type: ignore


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
                header_row.label(text="ON" if shader.is_enabled else "OFF")
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
        DGBLOCKS_PG_Shader_Mirror,
        DGBLOCKS_PG_Drawing_Props,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Draw_Handlers],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_loggers = Block_Loggers,
    block_data_mirrors = Block_Data_Mirrors,
)

def register_block_props():
    bpy.types.Scene.dgblocks_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Drawing_Props)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_drawing_props"):
        del bpy.types.Scene.dgblocks_drawing_props

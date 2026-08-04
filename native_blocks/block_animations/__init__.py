
import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui import ui_draw_block_panel_header

# Inter-block imports
# from .. import block_core          # noqa: F401
# from .. import block_onscreen_drawing  # noqa: F401
# from .. import block_timers        # noqa: F401
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_onscreen_drawing.common_declarations import Block_RTC_Members as ui_shader_RTC_members
from ..block_animations.data_structures import ANIM_DATA_TYPE_BATCH, ANIM_DATA_TYPE_UNIFORMS, Animation_Declaration

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .feature_animation_manager import Wrapper_Animation_Manager
from .helpers import _get_timer_definitions_from_animations

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# ==============================================================================================================================

def hook_get_timer_definitions():
    """
    Subscribed to block_timers' hook_get_timer_definitions.
    Returns one Timer_Definition per unique active animation framerate.
    block_timers creates (or re-creates) one bpy.app.timer per definition returned here.
    """
    return _get_timer_definitions_from_animations()

class DGBLOCKS_OT_Sample_Animation(bpy.types.Operator):
    bl_idname = "dgblocks.sample_animation"
    bl_label = "Sample Animation"
    bl_options = {"REGISTER"}
    
    def execute(self, context):
        
        # Get shaders instances, then create animations from them
        cached_shaders = Wrapper_Runtime_Cache.get_cache(ui_shader_RTC_members.SHADERS)
        new_animations = []
        for shader_instance in cached_shaders:
            if shader_instance.is_enabled:
                shifted_points = shader_instance._points.copy()
                shifted_points[:] += 1
                animation_instance = Animation_Declaration(
                    animation_uid = shader_instance.shader_uid,
                    target_shader_uid = shader_instance.shader_uid,
                    data_type = ANIM_DATA_TYPE_BATCH,
                    data_name = "_points",
                    end_state = shifted_points,
                    duration  = 3.0,
                    framerate = 10,
                )
                new_animations.append(animation_instance)
        Wrapper_Animation_Manager.add_animations(new_animations)

        return {"FINISHED"}



class DGBLOCKS_PT_Animation_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_Animation_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 10

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration = _BLOCK_DECLARATION,
        )

    def draw(self, context):
        layout = self.layout
        layout.operator("dgblocks.sample_animation")

# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                 = sys.modules[__name__],
    block_id                     = "block-animations",
    block_dependencies           = ["block-core", "block-onscreen-draw", "block-timers"],
    block_bpy_classes            = [DGBLOCKS_PT_Animation_Panel, DGBLOCKS_OT_Sample_Animation],
    block_feature_wrapper_classes= [Wrapper_Animation_Manager],
    block_loggers                = Block_Loggers,
    block_RTC_members            = Block_RTC_Members,
    icon                         = "TOOL_SETTINGS",
    documentation_url            = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

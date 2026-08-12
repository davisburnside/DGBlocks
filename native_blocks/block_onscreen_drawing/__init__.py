
import sys
import random
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.generic_tools import force_redraw_ui
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist, ui_draw_subpanel

# --------------------------------------------------------------
# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members # type: ignore

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .feature_shader_manager import Wrapper_Shader_Manager
from .data_structures import Shader_Declaration
from .BL_drawing_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Builtin_Shader_Names, Shader_Types
from .hook_subs import _hook_before_first_draw, _hook_get_shader_declarations, _hook_get_timer_definitions, _hook_post_startup
from .helpers import _clear_all_shaders, _rebuild_all_shaders
from .builtin_shaders_and_effects.custom_shader_billboard2D import Billboard_Shader
from .builtin_shaders_and_effects.custom_shader_polyline_dash import Polyline_Dash_Shader
from .builtin_shaders_and_effects.custom_shader_textbox_demo import Textbox_Demo_Shader
from .builtin_shaders_and_effects.demo_ui import DGBLOCKS_OT_Toggle_Demo_Animation, _ui_draw_shader_examples_subpanel

from .builtin_shaders_and_effects.demo_props import (
    DGBLOCKS_PG_Debug_Shader_Example_Props,
    DGBLOCKS_PG_Demo_Shader_Attribute,
    DGBLOCKS_PG_Demo_Shader_Common,
    DGBLOCKS_PG_Debug_Shader_Region_Toggles,
    DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_TEXTBOX,
    ATTR_DASHED_PHASE, ATTR_DASHED_COUNT,
    DEBUG_DRAW_REGION_TYPES, _EXAMPLE_LINEDASH_UID, _EXAMPLE_TEXTBOX_UID,
    _resolve_demo_shader_uid, _activate_demo_animation, ensure_demo_rows, 
    get_demo_row, region_type_is_enabled, demo_is_animatable, 
)

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS

def _cb_enable_drawing_changed(self, context):
    """
    Fired when the enable_drawing scene property changes.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    if context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
        _rebuild_all_shaders(event)
    else:
        _clear_all_shaders()

# ==============================================================================================================================
# BL PROPERTY GROUPS

class DGBLOCKS_PG_Shader_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live Shader_Instance.
    Stores only the uid key and read-only draw-location display fields
    (space / region / phase). This exists purely to back a UIList; it never drives RTC.

    is_enabled is RTC-only (on Shader_Instance) and is toggled through
    DGBLOCKS_OT_Toggle_Shader, which does not touch the undo stack.
    Populated and maintained by Wrapper_Shader_Manager._update_BL_with_mirrored_RTC_data().
    """
    shader_uid:  bpy.props.StringProperty()  # type: ignore
    draw_space:  bpy.props.StringProperty()  # type: ignore
    draw_region: bpy.props.StringProperty()  # type: ignore
    draw_phase:  bpy.props.StringProperty()  # type: ignore


class DGBLOCKS_PG_Onscreen_Drawing_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_onscreen_drawing.
    Stored on bpy.types.Scene.dgblocks_onscreen_drawing_props.
    """
    enable_drawing: bpy.props.BoolProperty(name="Enable Drawing", default=False, update=_cb_enable_drawing_changed) # type: ignore

    debug_props: bpy.props.PointerProperty(type = DGBLOCKS_PG_Debug_Shader_Example_Props) # type: ignore
    debug_show_examples: bpy.props.BoolProperty(name="Show Shader Examples", default=False) # type: ignore
    # Unified per-demo settings (task 4): one DGBLOCKS_PG_Demo_Shader_Common row per demo,
    # keyed by demo_id, each carrying show_shader / is_animating / animation_fps / scale plus a
    # nested CollectionProperty of shader-unique attributes. Seeded by ensure_demo_rows().
    demo_settings: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Demo_Shader_Common)  # type: ignore
    shader_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

def hook_before_first_draw():
    return _hook_before_first_draw()


def hook_get_shader_declarations():
    return _hook_get_shader_declarations()


def hook_get_timer_definitions():
    return _hook_get_timer_definitions()


def hook_post_startup():
    return _hook_post_startup()

# ==============================================================================================================================
# UI 

class DGBLOCKS_OT_Toggle_Shader(bpy.types.Operator):
    """Toggle a shader's visibility. is_enabled is RTC-only, so this must NOT enter the undo stack."""
    bl_idname = "dgblocks.toggle_shader"
    bl_label = "Toggle Shader"
    # INTERNAL hides it from search; omitting REGISTER/UNDO keeps it off the undo stack.
    bl_options = {"INTERNAL"}

    shader_uid: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        shader = Wrapper_Shader_Manager.get_shader(self.shader_uid)
        if shader is None:
            self.report({"WARNING"}, f"Shader '{self.shader_uid}' not found")
            return {"CANCELLED"}
        shader.is_enabled = not shader.is_enabled
        force_redraw_ui(only_3Dviewport = False)
        return {"FINISHED"}


class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    
    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration = _BLOCK_DECLARATION,
        )

    def draw(self, context):
        layout = self.layout
        drawing_props = context.scene.dgblocks_onscreen_drawing_props

        # Idempotently seed the per-demo settings rows (safe to call from draw).
        # ensure_demo_rows(drawing_props)

        # Master enable / disable toggle
        layout.prop(drawing_props, "enable_drawing", toggle=True)

        # Example / debug shaders grouped under a collapsible subpanel. Each demo is now its own
        # nested sub-subpanel with an eye toggle; per-demo animation toggles replace the old
        # "Sample Animations" button.
        ui_draw_subpanel(
            context, layout, "onscreen_shader_examples", "Shader Examples",
            _ui_draw_shader_examples_subpanel,
        )

        if not drawing_props.shader_mirror:
            layout.label(text="No active shaders", icon="INFO")
        else:
            draw_shared_uilist(context, layout, "shader_mirror")

# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS

def register_block_props():
    bpy.types.Scene.dgblocks_onscreen_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Onscreen_Drawing_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_onscreen_drawing_props"):
        del bpy.types.Scene.dgblocks_onscreen_drawing_props

# ==============================================================================================================================
# REQUIRED

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-onscreen-draw",
    block_dependencies = ["block-core", "block-timers"],
    block_bpy_classes = [
        # Nested PropertyGroups must register before the groups that point to them.
        DGBLOCKS_PG_Demo_Shader_Attribute,
        DGBLOCKS_PG_Demo_Shader_Common,
        DGBLOCKS_PG_Debug_Shader_Region_Toggles,
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Debug_Shader_Example_Props,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_OT_Toggle_Shader,
        DGBLOCKS_OT_Toggle_Demo_Animation,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Shader_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
    icon = "FILE_3D",
    documentation_url = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

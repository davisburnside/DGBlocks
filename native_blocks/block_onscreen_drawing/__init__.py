
import sys
import bpy


# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members # type: ignore
from ...addon_helpers.ui import ui_draw_block_panel_header, ui_draw_shared_debug_list, v2_draw_shared_uilist

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .feature_shader_manager import Wrapper_Shader_Manager
from .data_structures import Shader_Definition
from .BL_drawing_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Builtin_Shader_Names, Shader_Types

cache_key_shaders = Block_RTC_Members.SHADERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS

def _cb_is_enabled_changed(self, context):
    """
    Fired when the user toggles is_enabled on a shader_mirror row via the UIList.
    Immediately propagates the change to the matching live RTC Shader_Instance.

    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return

    logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)

    event = Enum_Sync_Events.PROPERTY_UPDATE
    FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_shaders)
    Wrapper_Shader_Manager.update_RTC_with_mirrored_BL_data(event, FWC_instance, data_mirror_instance)


def _cb_enable_drawing_changed(self, context):
    """
    Fired when the enable_drawing scene property changes.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    if self.enable_drawing:
        Wrapper_Shader_Manager.rebuild_all_shaders(event)
    else:
        Wrapper_Shader_Manager.clear_all_shaders()


def _cb_enable_viewport_debugging_changed(self, context):
    """
    Fired when the viewport debugging toggle changes.
    Rebuilds shaders so the debug borders are registered or removed.
    """
    if self.enable_drawing:
        event = Enum_Sync_Events.PROPERTY_UPDATE
        Wrapper_Shader_Manager.rebuild_all_shaders(event)

# ==============================================================================================================================
# BL PROPERTY GROUPS

class DGBLOCKS_PG_Shader_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live Shader_Instance.
    Stores the uid key, the user-editable is_enabled toggle, and read-only
    draw-location display fields (space / region / phase).
    Populated and maintained by Wrapper_Shader_Manager._sync_shaders_to_bl_mirror().
    """
    shader_uid:         bpy.props.StringProperty()  # type: ignore
    draw_space:  bpy.props.StringProperty()  # type: ignore
    draw_region: bpy.props.StringProperty()  # type: ignore
    draw_phase:  bpy.props.StringProperty()  # type: ignore
    is_enabled:  bpy.props.BoolProperty(     # type: ignore
        name="Enabled",
        default=True,
        update=_cb_is_enabled_changed,
    )


class DGBLOCKS_PG_Onscreen_Drawing_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_onscreen_drawing.
    Stored on bpy.types.Scene.dgblocks_onscreen_drawing_props.
    """
    enable_drawing: bpy.props.BoolProperty(  # type: ignore
        name="Enable Drawing",
        default=False,
        update=_cb_enable_drawing_changed,
    )
    enable_viewport_debugging: bpy.props.BoolProperty(  # type: ignore
        name="3D Viewport Debugging",
        default=False,
        update=_cb_enable_viewport_debugging_changed,
        description="Draws a rectangle along the boundary of each visible tab/menu/panel in the 3D viewport",
    )
    shader_mirror:       bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

def _debug_region_before_draw(shader_instance):
    region = bpy.context.region
    if region is None:
        return
    
    w, h = region.width, region.height
    last_dim = getattr(shader_instance, "_last_debug_dim", None)
    
    # Update points if dimensions have changed
    if last_dim != (w, h):
        points = [
            (1, 1), (w - 2, 1),
            (w - 2, 1), (w - 2, h - 2),
            (w - 2, h - 2), (1, h - 2),
            (1, h - 2), (1, 1)
        ]
        shader_instance.set_points(points)
        shader_instance._last_debug_dim = (w, h)
        
    shader_instance.set_uniform("color", (1.0, 0.0, 1.0, 1.0))  # Magenta


def hook_get_shader_definitions():
    """
    Adds debug bounding boxes for each region if enable_viewport_debugging is checked.
    """

    returned_shader_definitions = []
    props = bpy.context.scene.dgblocks_onscreen_drawing_props

    if props.enable_viewport_debugging:
        regions = [
            Draw_Region_Type.WINDOW,
            Draw_Region_Type.HEADER,
            Draw_Region_Type.UI,
            Draw_Region_Type.TOOLS,
            Draw_Region_Type.HUD,
        ]
        for region in regions:
            returned_shader_definitions.append(
                Shader_Definition(
                    shader_uid=f"DEBUG_REGION_BORDER_{region.value}",
                    shader_type=Shader_Types.LINES,
                    space=Draw_Space_Types.VIEW_3D,
                    region=region,
                    phase=Draw_Phase_type.POST_PIXEL,
                    builtin_shader_name=Builtin_Shader_Names.UNIFORM_COLOR,
                    builtin_shader_before_draw=_debug_region_before_draw,
                )
            )
    return returned_shader_definitions

# ==============================================================================================================================
# UI 

class DGBLOCKS_UL_Shader_List(bpy.types.UIList):
    bl_idname = "DGBLOCKS_UL_Shader_List"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        # Visibility toggle icon — clicking sets is_enabled via the BoolProperty
        eye_icon = "HIDE_OFF" if item.is_enabled else "HIDE_ON"
        row.prop(item, "is_enabled", text="", icon=eye_icon, emboss=False)
        row.label(text=item.shader_uid)
        row.label(text=f"{item.draw_space} / {item.draw_region} / {item.draw_phase}")


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
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name="FILE_3D",
        )

    def draw(self, context):
        layout = self.layout
        drawing_props = context.scene.dgblocks_onscreen_drawing_props

        # Master enable / disable toggle
        layout.prop(drawing_props, "enable_drawing", toggle=True)
        
        row = layout.row()
        row.enabled = drawing_props.enable_drawing
        row.prop(drawing_props, "enable_viewport_debugging", toggle=True)

        if not drawing_props.shader_mirror:
            layout.label(text="No active shaders", icon="INFO")
        

        # Per-shader list with is_enabled toggles
        # layout.template_list(
        #     "DGBLOCKS_UL_Shader_List", "",
        #     props, "shader_mirror",
        #     props, "shader_mirror_selected_idx",
        # )

        # ui_draw_shared_debug_list(
        #     context, layout, "BLOCKS_LIST", 
        #     drawing_props, "shader_mirror", "shader_mirror_selected_idx", 
        # )

        else:
            data_mirror_id = tuple(Wrapper_Shader_Manager.__name__, cache_key_shaders.name) # FWC & RTC names
            data_mirror_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_data_mirrors, "uid", data_mirror_id)
            v2_draw_shared_uilist(context, layout, data_mirror_instance)

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
    block_dependencies = ["block-core"],
    block_bpy_classes = [
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_UL_Shader_List,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Shader_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
)

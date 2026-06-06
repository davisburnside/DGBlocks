
import sys
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
from .common_constants import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .feature_shader_manager import Wrapper_Shader_Manager

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

def _cb_is_enabled_changed(self, context):
    """
    Fired when the user toggles is_enabled on a shader_mirror row via the UIList.
    Immediately propagates the change to the matching live RTC Shader_Instance.

    Blender records an undo step for the BoolProperty change automatically.
    On undo, Blender reverts the BL value and re-fires this callback, keeping
    the RTC in sync without any extra logic.

    Skipped when the syncing flag is set (prevents feedback loops during
    _sync_shaders_to_bl_mirror).
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return
    shader = Wrapper_Shader_Manager.get_shader(self.uid)
    if shader is not None:
        shader.is_enabled = self.is_enabled


def _cb_enable_drawing_changed(self, context):
    """
    Fired when the enable_drawing scene property changes.

    True  → full rebuild: collect definitions, create instances, fire first-draw hook.
    False → clear all draw handlers and shader instances.

    The BL shader_mirror is not cleared when drawing is disabled so that
    is_enabled preferences survive the toggle cycle.
    """
    if self.enable_drawing:
        Wrapper_Shader_Manager.rebuild_all_shaders()
    else:
        Wrapper_Shader_Manager.clear_all_shaders()


# ==============================================================================================================================
# BL PROPERTY GROUPS
# ==============================================================================================================================

class DGBLOCKS_PG_Shader_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live Shader_Instance.
    Stores the uid key, the user-editable is_enabled toggle, and read-only
    draw-location display fields (space / region / phase).
    Populated and maintained by Wrapper_Shader_Manager._sync_shaders_to_bl_mirror().
    """
    uid:         bpy.props.StringProperty()  # type: ignore
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
    shader_mirror:       bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_index: bpy.props.IntProperty()  # type: ignore


# ==============================================================================================================================
# HOOK SUBSCRIBERS
# Top-level functions whose names match Block_Hook_Sources members in block_core.
# Auto-discovered by Wrapper_Hooks at block registration time.
# ==============================================================================================================================

def hook_core_event_undo():
    """
    After undo: delegate to update_RTC_with_mirrored_BL_data, which checks whether the
    shader structure has actually changed before deciding to rebuild or only restore
    is_enabled values.  Avoids tearing down and recreating GPU resources when the undo
    step did not affect the drawing configuration.
    """
    try:
        Wrapper_Shader_Manager.update_RTC_with_mirrored_BL_data(Enum_Sync_Events.PROPERTY_UPDATE_UNDO)
    except Exception:
        pass


def hook_core_event_redo():
    """After redo: same smart sync as undo."""
    try:
        Wrapper_Shader_Manager.update_RTC_with_mirrored_BL_data(Enum_Sync_Events.PROPERTY_UPDATE_REDO)
    except Exception:
        pass


# ==============================================================================================================================
# UI LIST
# ==============================================================================================================================

class DGBLOCKS_UL_Shader_List(bpy.types.UIList):
    bl_idname = "DGBLOCKS_UL_Shader_List"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        # Visibility toggle icon — clicking sets is_enabled via the BoolProperty
        eye_icon = "HIDE_OFF" if item.is_enabled else "HIDE_ON"
        row.prop(item, "is_enabled", text="", icon=eye_icon, emboss=False)
        row.label(text=item.uid)
        row.label(text=f"{item.draw_space} / {item.draw_region} / {item.draw_phase}")


# ==============================================================================================================================
# UI PANEL
# ==============================================================================================================================

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
        props = context.scene.dgblocks_onscreen_drawing_props

        # Master enable / disable toggle
        layout.prop(props, "enable_drawing", toggle=True)

        if not props.shader_mirror:
            layout.label(text="No active shaders", icon="INFO")
            return

        # Per-shader list with is_enabled toggles
        layout.template_list(
            "DGBLOCKS_UL_Shader_List", "",
            props, "shader_mirror",
            props, "shader_mirror_index",
        )


# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS
# ==============================================================================================================================

def register_block_props():
    bpy.types.Scene.dgblocks_onscreen_drawing_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_Onscreen_Drawing_Props
    )


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_onscreen_drawing_props"):
        del bpy.types.Scene.dgblocks_onscreen_drawing_props


# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module=sys.modules[__name__],
    block_id="block-onscreen-draw",
    block_dependencies=["block-core"],
    block_bpy_classes=[
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_UL_Shader_List,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes=[Wrapper_Shader_Manager],
    block_hook_sources=Block_Hook_Sources,
    block_RTC_members=Block_RTC_Members,
    block_data_mirrors=Block_Data_Mirrors,
    block_loggers=Block_Loggers,
)

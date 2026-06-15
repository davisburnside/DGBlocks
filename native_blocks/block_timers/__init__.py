
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
from ..block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ...addon_helpers.ui import ui_draw_block_panel_header, draw_shared_uilist

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .feature_timer_manager import Wrapper_Timer_Manager
from .data_structures import Timer_Definition
from .helpers import _clear_all_timers, _rebuild_all_timers

cache_key_timers = Block_RTC_Members.TIMERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS

def _cb_is_enabled_changed(self, context):
    """
    Fired when the user toggles is_enabled on a timer_mirror row via the UIList.
    Immediately propagates the change to the matching live RTC Timer_Instance.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.TIMERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_timers)
    Wrapper_Timer_Manager._update_RTC_with_mirrored_BL_data(event, FWC_instance, data_mirror_instance)


def _cb_enable_timers_changed(self, context):
    """
    Fired when the enable_timers scene property changes.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.TIMERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    if self.enable_timers:
        _rebuild_all_timers(event)
    else:
        _clear_all_timers()

# ==============================================================================================================================
# BL PROPERTY GROUPS

class DGBLOCKS_PG_Timer_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live Timer_Instance.
    Stores the uid key, the frequency (display only), and the user-editable is_enabled toggle.
    Populated and maintained by Wrapper_Timer_Manager._update_BL_with_mirrored_RTC_data().
    """
    timer_uid:  bpy.props.StringProperty()          # type: ignore
    frequency:  bpy.props.FloatProperty(            # type: ignore
        name="Frequency (s)",
        default=1.0,
        min=0.0,
    )
    is_enabled: bpy.props.BoolProperty(             # type: ignore
        name="Enabled",
        default=True,
        update=_cb_is_enabled_changed,
    )


class DGBLOCKS_PG_Timers_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_timers.
    Stored on bpy.types.Scene.dgblocks_timers_props.
    """
    enable_timers: bpy.props.BoolProperty( 
        name="Enable Timers",
        default=False,
        update=_cb_enable_timers_changed,
    ) # type: ignore
    timer_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Timer_Mirror_Row)  # type: ignore
    timer_mirror_selected_idx: bpy.props.IntProperty() # type: ignore
    debug_mode_enabled: bpy.props.BoolProperty() # type: ignore

# ==============================================================================================================================
# UI

class DGBLOCKS_UL_Timer_List(bpy.types.UIList):
    bl_idname = "DGBLOCKS_UL_Timer_List"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        eye_icon = "HIDE_OFF" if item.is_enabled else "HIDE_ON"
        row.prop(item, "is_enabled", text="", icon=eye_icon, emboss=False)
        row.label(text=item.timer_uid)
        row.label(text=f"{item.frequency:.3f}s")


class DGBLOCKS_PT_Timers_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Timers_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name="TIME",
        )

    def draw(self, context):
        layout = self.layout
        timers_props = context.scene.dgblocks_timers_props

        # Master enable / disable toggle
        layout.prop(timers_props, "enable_timers", toggle=True)

        layout.prop(timers_props, "debug_mode_enabled", text = "Debug Mode")

        if not timers_props.timer_mirror:
            row = layout.row()
            row.enabled = timers_props.enable_timers
            row.label(text="No active timers", icon="INFO")
        else:
            draw_shared_uilist(context, layout, "timer_mirror")

# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS

def register_block_props():
    bpy.types.Scene.dgblocks_timers_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Timers_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_timers_props"):
        del bpy.types.Scene.dgblocks_timers_props

# ==============================================================================================================================
# REQUIRED

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-timers",
    block_dependencies = ["block-core"],
    block_bpy_classes = [
        DGBLOCKS_PG_Timer_Mirror_Row,
        DGBLOCKS_PG_Timers_Props,
        DGBLOCKS_UL_Timer_List,
        DGBLOCKS_PT_Timers_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Timer_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
)

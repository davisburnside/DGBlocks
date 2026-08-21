
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
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import (
    Block_Data_Mirrors,
    Block_Hook_Sources,
    Block_Loggers,
    Block_RTC_Members,
    Block_UIList_Configs,
)
from .feature_modal_manager import Wrapper_Modal_Manager
from .data_structures import Modal_Listener_Definition, Modal_Listener_End_Reason
from .helpers import (
    DGBLOCKS_OT_Modal_Event_Router,
    end_all_listeners,
)
from .workspace_tools import register_declared_workspace_tools, unregister_all_workspace_tools

cache_key_listeners = Block_RTC_Members.LISTENERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS

def _cb_is_enabled_changed(self, context):
    """
    Fired when the user toggles is_enabled on a listener_mirror row via the UIList.
    Immediately propagates the change to the matching live RTC listener instance.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.LISTENERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_listeners)
    Wrapper_Modal_Manager._update_RTC_with_mirrored_BL_data(event, FWC_instance, data_mirror_instance)


# ==============================================================================================================================
# BL PROPERTY GROUPS

class DGBLOCKS_PG_Modal_Listener_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live RTC_Modal_Listener_Instance.
    Stores the src_block_id key, the priority (display only), and the user-editable is_enabled
    toggle. Populated and maintained by Wrapper_Modal_Manager._update_BL_with_mirrored_RTC_data().
    """
    src_block_id: bpy.props.StringProperty()  # type: ignore
    priority:     bpy.props.IntProperty(name="Priority", default=0)  # type: ignore
    is_enabled:   bpy.props.BoolProperty(  # type: ignore
        name="Enabled",
        default=True,
        update=_cb_is_enabled_changed,
    )


class DGBLOCKS_PG_Modal_Events_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_modal_events.
    Stored on bpy.types.Scene.dgblocks_modal_events_props.
    """
    listener_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Modal_Listener_Row)  # type: ignore
    listener_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

def hook_post_startup():
    """Rebuild static tools and restart listeners after startup or a file load."""
    end_all_listeners(Modal_Listener_End_Reason.ROUTER_SHUTDOWN)
    register_declared_workspace_tools()
    Wrapper_Modal_Manager.repoll(Enum_Sync_Events.ADDON_INIT)

def hook_before_blocks_reload():
    end_all_listeners(Modal_Listener_End_Reason.ROUTER_SHUTDOWN)
    unregister_all_workspace_tools()

# ==============================================================================================================================
# UI

class DGBLOCKS_UL_Modal_Listener_List(bpy.types.UIList):
    bl_idname = "DGBLOCKS_UL_Modal_Listener_List"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        eye_icon = "HIDE_OFF" if item.is_enabled else "HIDE_ON"
        row.prop(item, "is_enabled", text="", icon=eye_icon, emboss=False)
        row.label(text=item.src_block_id)
        row.label(text=f"P{item.priority}")


class DGBLOCKS_PT_Modal_Events_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Modal_Events_Panel"
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
        modal_props = context.scene.dgblocks_modal_events_props

        if not modal_props.listener_mirror:
            layout.label(text="No modal listeners", icon="INFO")
        else:
            draw_shared_uilist(context, layout, "listener_mirror")

# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS

def register_block_props():
    bpy.types.Scene.dgblocks_modal_events_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Modal_Events_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_modal_events_props"):
        del bpy.types.Scene.dgblocks_modal_events_props

# ==============================================================================================================================
# REQUIRED

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-modal-events",
    block_dependencies = ["block-core"],
    block_bpy_classes = [
        DGBLOCKS_PG_Modal_Listener_Row,
        DGBLOCKS_PG_Modal_Events_Props,
        DGBLOCKS_OT_Modal_Event_Router,
        DGBLOCKS_UL_Modal_Listener_List,
        DGBLOCKS_PT_Modal_Events_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Modal_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
    icon = "MOUSE_LMB",
    documentation_url = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

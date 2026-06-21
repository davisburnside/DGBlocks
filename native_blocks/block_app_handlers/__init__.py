
import sys
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui import draw_shared_uilist, ui_draw_block_panel_header

# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# Intra-block imports
from .common_declarations import (
    Block_Data_Mirrors,
    Block_Hook_Sources,
    Block_Loggers,
    Block_RTC_Members,
    Block_UIList_Configs,
)
from .feature_app_handlers import Wrapper_App_Handlers
from .data_structures import App_Handler_Type, App_Handler_Subscription_Declaration

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# ==============================================================================================================================

def hook_post_startup():
    """
    Called once after full addon init. Triggers the first subscription poll so that
    downstream blocks' subscriptions are active before any Blender events fire.
    """
    Wrapper_App_Handlers.refresh_subscriptions()


# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

def _cb_is_enabled_changed(self, context):
    """
    Fired when the user toggles is_enabled in the handler status UIList.
    Guards against re-entrant sync, then forwards to Wrapper_App_Handlers.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.APP_HANDLER_STATUS_LIST):
        return
    Wrapper_App_Handlers.set_handler_enabled(self.handler_type_name, self.is_enabled)


# ==============================================================================================================================
# BL PROPERTY GROUPS
# ==============================================================================================================================

class DGBLOCKS_PG_App_Handler_Status_Row(bpy.types.PropertyGroup):
    """
    One persistent display row per active bpy.app.handler type.
    Rebuilt from RTC on every refresh_subscriptions() call.
    is_enabled is the only user-editable field; all others are read-only display.
    """
    handler_type_name: bpy.props.StringProperty(name="Handler Type")           # type: ignore
    is_enabled:        bpy.props.BoolProperty(                                  # type: ignore
        name   = "Enabled",
        default = True,
        update  = _cb_is_enabled_changed,
    )
    is_registered:           bpy.props.BoolProperty(default=False)              # type: ignore
    subscriber_count:        bpy.props.IntProperty(default=0)                   # type: ignore
    frequency_filter_seconds: bpy.props.FloatProperty(default=0.0)             # type: ignore


class DGBLOCKS_PG_App_Handlers_Props(bpy.types.PropertyGroup):
    """Scene-level property group for block_app_handlers."""

    handler_status_mirror: bpy.props.CollectionProperty(                        # type: ignore
        type = DGBLOCKS_PG_App_Handler_Status_Row,
    )
    handler_status_mirror_selected_idx: bpy.props.IntProperty()                 # type: ignore


# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Refresh_App_Handler_Subscriptions(bpy.types.Operator):
    """Re-poll all downstream blocks and reconcile active bpy.app.handlers."""
    bl_idname = "dgblocks.refresh_app_handler_subscriptions"
    bl_label  = "Refresh Handler Subscriptions"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            Wrapper_App_Handlers.refresh_subscriptions()
            status_list = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST)
            self.report({"INFO"}, f"App Handlers refreshed — {len(status_list)} type(s) active.")
        except Exception as e:
            self.report({"ERROR"}, f"Refresh failed: {e}")
        return {"FINISHED"}


# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_PT_App_Handlers_Panel(bpy.types.Panel):
    bl_label       = ""
    bl_idname      = "DGBLOCKS_PT_App_Handlers_Panel"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = addon_title
    bl_options     = {"DEFAULT_CLOSED"}
    bl_order       = 25

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name = "SCENE",
        )

    def draw(self, context):
        layout = self.layout
        props  = context.scene.dgblocks_app_handlers_props

        # Refresh button
        row = layout.row()
        row.scale_y = 1.4
        row.operator("dgblocks.refresh_app_handler_subscriptions", icon="FILE_REFRESH")

        layout.separator()

        status_list = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST)
        if not status_list:
            layout.label(text="No active handlers — refresh to poll subscribers", icon="INFO")
            return

        draw_shared_uilist(context, layout, "handler_status_mirror")


# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS
# ==============================================================================================================================

def register_block_props():
    bpy.types.Scene.dgblocks_app_handlers_props = bpy.props.PointerProperty(
        type = DGBLOCKS_PG_App_Handlers_Props,
    )


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_app_handlers_props"):
        del bpy.types.Scene.dgblocks_app_handlers_props


# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                  = sys.modules[__name__],
    block_id                      = "block-app-handlers",
    block_dependencies            = ["block-core"],
    block_bpy_classes             = [
        DGBLOCKS_PG_App_Handler_Status_Row,
        DGBLOCKS_PG_App_Handlers_Props,
        DGBLOCKS_PT_App_Handlers_Panel,
        DGBLOCKS_OT_Refresh_App_Handler_Subscriptions,
    ],
    block_feature_wrapper_classes = [Wrapper_App_Handlers],
    block_hook_sources            = Block_Hook_Sources,
    block_RTC_members             = Block_RTC_Members,
    block_data_mirrors            = Block_Data_Mirrors,
    block_loggers                 = Block_Loggers,
    block_uilist_configs          = Block_UIList_Configs,
)

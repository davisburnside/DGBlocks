
import time
import bpy

from ....addon_config.static_settings import Documentation_URLs, addon_title
from ....addon_helpers.ui.helpers import format_timestamp_for_ui, draw_shared_uilist, ui_draw_generic_instance_data, ui_draw_block_panel_header, ui_draw_static_list, ui_draw_subpanel
from ....addon_helpers.generic_tools import get_Wrapper_Runtime_Cache

# Sentinel passed as 'rtc_key' to dgblocks.copy_to_clipboard to request the whole Runtime Cache.
# Defined here (not in constants.py) because constants.py imports this module
RTC_COPY_ALL_KEY = "*"

# Block-mngr UIList funcs

def _uilist_blocks_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    icon = "WARNING_LARGE" if RTC_item.error_message else "CHECKMARK"
    sub.label(text = "", icon = icon)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = RTC_item.block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    version_str = ".".join([str(i) for i in RTC_item.block_version])
    sub.label(text = version_str)

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "debug_mode_enabled", text = "")

def _uilist_blocks_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    box = container.box()
    block_instance = get_Wrapper_Runtime_Cache().get_cache("REGISTRY_ALL_BLOCKS")[list_idx]
    if BL_item.is_valid:
        box.label(text = f"'{block_instance.block_id}' is active", icon='CHECKMARK')
    else:
        box.alert = True
        box.label(text = f"Error: {RTC_item.error_message}", icon='ERROR')
    box.label(text = f"Location: {block_instance.block_package_name}")
    box.label(text = f"TODO: button op to open folder")

# ==============================================================================================================================
# HOOKS UILIST FILTER
# ==============================================================================================================================

def _hooks_filter_items(context, uilist_config_instance, BL_colprop):
    """
    Filter callback for the Hooks UIList.
    When core_props.hooks_hide_unsub is True, hides hook sources with no subscribers.
    Returns list[bool], one entry per BL collection item (True = show, False = hide).
    """
    try:
        hide_unsub = context.scene.dgblocks_core_props.hooks_hide_unsub
    except AttributeError:
        return [True] * len(BL_colprop)

    if not hide_unsub:
        return [True] * len(BL_colprop)

    # Match BL rows to RTC records by hook name, never by list index.
    # The two lists are normally in sync, but a drift must not silently disable the filter
    _dirty_wrapper_RTC = get_Wrapper_Runtime_Cache()
    RTC_hook_sources = _dirty_wrapper_RTC.get_cache(uilist_config_instance.RTC_key)
    if not RTC_hook_sources:
        return [True] * len(BL_colprop)

    subscriber_counts = {h.hook_func_name: h.subscriber_count for h in RTC_hook_sources}

    result = []
    for BL_item in BL_colprop:
        # Unknown hook names stay visible, so nothing is ever hidden by accident
        count = subscriber_counts.get(BL_item.hook_func_name, 1)
        result.append(count > 0)
    return result



# ==============================================================================================================================
# HOOKS UILIST ROW + DETAILS
# ==============================================================================================================================

# Hooks-mngr UIList funcs
ui_structure_for_hook_sub_instance = {
    "Run Counts": [
        ("Success", "count_hook_propagate_success"),
        ("Failure", "count_hook_propagate_failure"),
        ("Skip from Status", "count_bypass_via_status"),
        ("Skip from Data Filter", "count_bypass_via_data_filter"),
        ("Skip from Freq. Filter", "count_bypass_via_frequency"),
    ],
    "Run Statistics":[
        ("Last Run Time", "last_run_timestamp", format_timestamp_for_ui),
        ("Last Run Duration (ns)", "duration_last_run"),
    ]
}

def _uilist_hooks_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    
    func_name = BL_item.hook_func_name
    cached_hook_subs = get_Wrapper_Runtime_Cache().get_cache("REGISTRY_ALL_HOOK_SUBSCRIBERS")

    if func_name not in cached_hook_subs:
        container.label(text="No subscriptions found.")
        return

    subs = cached_hook_subs[func_name]
    box = container.box()
    box.label(text=f"Subs for '{func_name}'")
    for hook_sub_instance in subs:
        kwargs = {"instance": hook_sub_instance, "structure": ui_structure_for_hook_sub_instance}
        ui_draw_subpanel(
            context, 
            box, 
            f"hook_sub_{hook_sub_instance.subscriber_block_id }", 
            hook_sub_instance.subscriber_block_id, 
            ui_draw_generic_instance_data, 
            **kwargs,
        )


def _uilist_hooks_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    
    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = BL_item.hook_func_name)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = BL_item.src_block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.label(text = str(RTC_item.subscriber_count))

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.label(text = str(RTC_item.trigger_count))

    sub = header.row()
    sub.ui_units_x = col_widths[4]
    sub.prop(BL_item, "is_hook_enabled", text = "")

# ==============================================================================================================================
# RTC MEMBER SNAPSHOT HELPERS
# ==============================================================================================================================

def _rtc_member_summary(cache_value) -> str:
    """Short 'shape' hint for one RTC member, e.g. 'list (7)' / 'dict (3)' / 'Global_Addon_State'."""

    if isinstance(cache_value, dict):
        return f"dict ({len(cache_value)})"
    if isinstance(cache_value, (list, tuple, set)):
        return f"{type(cache_value).__name__} ({len(cache_value)})"
    if cache_value is None:
        return "None"
    return type(cache_value).__name__


def ui_draw_rtc_members_snapshot(context, container):
    """
    One box per RTC member, each with a copy-to-clipboard button, plus a
    copy-everything button at the top. Built for grabbing fast RTC snapshots.

    Only the member NAME is handed to the operator — the string is generated on
    click, so panel redraws never pay for serializing the cache.
    """

    _dirty_wrapper_RTC = get_Wrapper_Runtime_Cache()

    row = container.row()
    row.scale_y = 1.3
    op = row.operator("dgblocks.copy_to_clipboard", text = "Copy Entire RTC", icon = "COPYDOWN")
    op.rtc_key = RTC_COPY_ALL_KEY

    all_cache_keys = _dirty_wrapper_RTC.get_all_cache_keys()
    if not all_cache_keys:
        container.label(text = "Runtime Cache is empty", icon = "INFO")
        return

    for cache_key in all_cache_keys:
        cache_value = _dirty_wrapper_RTC.get_cache(cache_key)

        box = container.box()
        row = box.row()

        sub = row.row()
        sub.alignment = "LEFT"
        sub.label(text = cache_key)

        sub = row.row()
        sub.alignment = "RIGHT"
        sub.label(text = _rtc_member_summary(cache_value))
        op = sub.operator("dgblocks.copy_to_clipboard", text = "", icon = "COPYDOWN")
        op.rtc_key = cache_key


# Logger-mngr UIList funcs
def _uilist_loggers_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):


    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = BL_item.logger_name)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = BL_item.src_block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.prop(BL_item, "level_name", text = "")


class DGBLOCKS_PT_Core_Block_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"DGBLOCKS_PT_Core_Block_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, "Block-Core", Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "FILE_3D")
        row = self.layout.row()
        row.alert = True
        row.operator("dgblocks.reload_all_blocks", text="Reload All", icon="FILE_REFRESH")


    def draw_subpanel_body(self, context, container):

        core_scene_props = context.scene.dgblocks_core_props
        grid = container.grid_flow(columns=2)
        grid.prop(core_scene_props, "addon_is_active")
        grid.prop(core_scene_props, "debug_log_all_RTC_BL_sync_actions")
        grid.prop(core_scene_props, "documentation_weblinks_enabled")
        op_rtc_clear = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Clear RTC")
        op_rtc_clear.target = "RTC"
        op_rtc_clear.action = "CLEAR"
        op_rtc_restore = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Restore RTC")
        op_rtc_restore.target = "RTC"
        op_rtc_restore.action = "RESTORE"
        grid.label(text = "TODO: Addon Data Folder path")


    def _draw_hooks_subpanel_body(self, context, container):
        """Draw body of the Hooks subpanel, including the hide-unsub filter checkbox."""
        core_scene_props = context.scene.dgblocks_core_props
        row = container.row()
        row.prop(core_scene_props, "hooks_hide_unsub", text="Hide hooks with no subscribers")
        draw_shared_uilist(context, container, "managed_hooks")

    def _draw_loggers_subpanel_body(self, context, container):
        """Draw body of the Loggers subpanel, including the datetime dropdown."""
        core_scene_props = context.scene.dgblocks_core_props
        row = container.row()
        row.prop(core_scene_props, "logger_include_datetime", text="Include Datetime")
        draw_shared_uilist(context, container, "managed_loggers")

    def draw(self, context):
        
        layout = self.layout
        core_scene_props = context.scene.dgblocks_core_props
    
        # General settings
        ui_draw_subpanel(context, layout, "general", "General Settings", self.draw_subpanel_body)

        # Blocks subpanel
        blocks_label = f"All Blocks ({len(core_scene_props.managed_blocks)})"
        ui_draw_subpanel(context, layout, "managed_blocks", blocks_label, draw_shared_uilist,
                         scene_data_path="managed_blocks")

        # Hooks subpanel (uses custom body to include the filter checkbox)
        hooks_label = f"All Hooks ({len(core_scene_props.managed_hooks)})"
        ui_draw_subpanel(context, layout, "managed_hooks", hooks_label, self._draw_hooks_subpanel_body)

        # Loggers subpanel
        loggers_label = f"All Loggers ({len(core_scene_props.managed_loggers)})"
        ui_draw_subpanel(context, layout, "managed_loggers", loggers_label, self._draw_loggers_subpanel_body)

        # RTC members subpanel (snapshot / clipboard tooling, no BL data behind it)
        rtc_member_count = len(get_Wrapper_Runtime_Cache().get_all_cache_keys())
        rtc_label = f"All RTC Members ({rtc_member_count})"
        ui_draw_subpanel(context, layout, "rtc_members", rtc_label, ui_draw_rtc_members_snapshot)

            
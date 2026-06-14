
import time
import bpy

from ....addon_config.static_settings import Documentation_URLs, addon_title
from ....addon_helpers.ui import format_timestamp_for_ui, draw_shared_uilist, ui_draw_generic_instance_data, ui_draw_block_panel_header, ui_draw_static_list, ui_draw_subpanel
from ....addon_helpers.generic_tools import get_Wrapper_Runtime_Cache

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
        ("Last Run Time", "last_run_timestamp_nanos", format_timestamp_for_ui),
        ("Last Run Duration (ns)", "duration_nanos_last_run"),
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


    def draw_subpanel_body(self, context, container):

        core_scene_props = context.scene.dgblocks_core_props
        grid = container.grid_flow(columns=2)
        grid.prop(core_scene_props, "addon_is_active")
        grid.prop(core_scene_props, "debug_mode_enabled")
        grid.prop(core_scene_props, "debug_log_all_RTC_BL_sync_actions")
        grid.prop(core_scene_props, "documentation_weblinks_enabled")
        op_rtc_clear = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Clear RTC")
        op_rtc_clear.target = "RTC"
        op_rtc_clear.action = "CLEAR"
        op_rtc_restore = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Restore RTC")
        op_rtc_restore.target = "RTC"
        op_rtc_restore.action = "RESTORE"
        grid.label(text = "TODO: Addon Data Folder path")


    def draw(self, context):
        
        layout = self.layout
        core_scene_props = context.scene.dgblocks_core_props
    
        # General settings
        ui_draw_subpanel(context, layout, "general", "General Settings", self.draw_subpanel_body)

        # Draw management subpanels for blocks, hooks, & loggers
        core_feature_drawing = [
            ("Blocks", core_scene_props.managed_hooks, "managed_blocks"),
            ("Hooks", core_scene_props.managed_hooks, "managed_hooks"),
            ("Loggers", core_scene_props.managed_loggers, "managed_loggers")
        ]
        for label_str, BL_colprop, colprop_name in core_feature_drawing:
            label_str = f"All {label_str} ({len(BL_colprop)})"
            kwargs = {"scene_data_path": colprop_name}
            ui_draw_subpanel(context, layout, colprop_name, label_str, draw_shared_uilist, **kwargs)
            
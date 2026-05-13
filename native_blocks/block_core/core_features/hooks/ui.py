# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from datetime import datetime
import bpy  # type: ignore
from .....addon_helpers.ui import ui_draw_list_headers

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_hook_subscribers = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS

# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Function Name", "Subscriber Block", "Is Enabled?")
col_widths = (2, 2, 1)


def _uilayout_draw_hooks_uilist_selection_detail(context, container):

    # Show disabled reason for selected alert row
    core_props = context.scene.dgblocks_core_props
    is_anything_selected = 0 <= core_props.managed_hooks_selected_idx < len(core_props.managed_hooks)
    if core_props.managed_hooks and is_anything_selected:
        selected_hook = core_props.managed_hooks[core_props.managed_hooks_selected_idx]

        # get mirrored hook RTC record for more data, like execution count
        all_RTC_hook_subscribers = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)
        hook_RTC_instance = next((h for h in all_RTC_hook_subscribers if h.hook_func_name == selected_hook.hook_func_name), None)
        if hook_RTC_instance:

            header_str = f"{hook_RTC_instance.hook_func_name}    ->    {hook_RTC_instance.subscriber_block_id}"
            details_box = container.box()
            panel_header, panel_body = details_box.panel(idname="_dummy_dgblocks_core_scene_selected_hook", default_closed=True)
            row = panel_header.row()
            row.alignment = "CENTER"
            row.label(text=header_str)
            if panel_body is not None:

                panel_body.separator(factor=0.5)
                row = panel_body.row()
                row.alignment = "LEFT"
                row.operator("dgblocks.debug_force_refresh_ui", text="", icon="FILE_REFRESH")
                row.label(text="Last Trigger")
                ts = datetime.fromtimestamp(hook_RTC_instance.timestamp_ms_last_attempt / 1000)
                row.label(text=ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])

                grid = panel_body.grid_flow(columns=2)

                total_run_count = hook_RTC_instance.count_hook_propagate_success + hook_RTC_instance.count_hook_propagate_failure
                grid.label(text="Avg Run Time (ms)")
                if total_run_count == 0:
                    grid.label(text="N/A")
                else:
                    grid.label(text=str((hook_RTC_instance.total_nanos_running_time) / float(total_run_count)))

                grid.label(text="Successful Runs")
                grid.label(text=str(hook_RTC_instance.count_hook_propagate_success))

                grid.label(text="Failed Runs")
                grid.label(text=str(hook_RTC_instance.count_hook_propagate_failure))

                grid.label(text="Bypassed Runs")
                grid.label(text=str(hook_RTC_instance.count_bypass_via_data_filter))


def _uilayout_draw_hooks_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_hooks_mgmt", default_closed=True)
    panel_header.label(text=f"All Hook Subscriptions ({len(context.scene.dgblocks_core_props.managed_hooks)})")
    if panel_body is not None:

        # Draw column headers - should match draw_item layout exactly
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw the UIList
        row = panel_body.row()
        row_count = len(core_props.managed_hooks)
        row.template_list(
            "DGBLOCKS_UL_Hooks",
            "",
            core_props, "managed_hooks",
            core_props, "managed_hooks_selected_idx",
            rows=row_count,
        )

        _uilayout_draw_hooks_uilist_selection_detail(context, panel_body)


class DGBLOCKS_UL_Hooks(bpy.types.UIList):
    """UIList to display RTC hooks with enable toggle and alert states."""

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):

        row = container.row(align=True)

        # Hook name
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.hook_func_name)

        # Subscriber block
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.label(text=item.subscriber_block_id)

        # Is enabled status
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.prop(item, "is_hook_enabled", text="", icon='CHECKBOX_HLT' if item.is_hook_enabled else 'CHECKBOX_DEHLT')

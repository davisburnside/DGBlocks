
import time
import bpy

from ....addon_config.static_settings import Documentation_URLs, addon_title
from ....addon_helpers.ui.helpers import format_timestamp_for_ui, draw_shared_uilist, ui_draw_generic_instance_data, ui_draw_block_panel_header, ui_draw_static_list, ui_draw_subpanel
from ....addon_helpers.generic_tools import get_Wrapper_Runtime_Cache
from ..core_features.unit_testing.data_structures import Unit_Test_Status

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


# ==============================================================================================================================
# UNIT TESTS UILIST ROW + DETAILS
# ==============================================================================================================================

_UNIT_TEST_STATUS_ICONS = {
    Unit_Test_Status.PASSED:  "CHECKMARK",
    Unit_Test_Status.FAILED:  "ERROR",
    Unit_Test_Status.ERROR:   "ERROR",
    Unit_Test_Status.SKIPPED: "TRACKING_CLEAR_BACKWARDS",
    Unit_Test_Status.NOT_RUN: "RADIOBUT_OFF",
}


def _summarize_test_cases(cases: list) -> str:
    """Short 'N/M passed' style summary, always computed live from current statuses — never cached."""
    if not cases:
        return "No tests"
    total = len(cases)
    passed = sum(1 for c in cases if c.status == Unit_Test_Status.PASSED)
    failed = sum(1 for c in cases if c.status in (Unit_Test_Status.FAILED, Unit_Test_Status.ERROR))
    not_run = sum(1 for c in cases if c.status == Unit_Test_Status.NOT_RUN)
    if not_run == total:
        return f"{total} not run"
    if failed:
        return f"{failed} failed / {total}"
    if not_run:
        return f"{passed}/{total} passed ({not_run} not run)"
    return f"{passed}/{total} passed"


def _uilist_unit_tests_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()
    block_cases = get_Wrapper_Runtime_Cache().get_cache("UNIT_TEST_CASE_CATALOG")
    block_cases = [c for c in block_cases if c.block_id == RTC_item.block_id]

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = RTC_item.label)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = format_timestamp_for_ui(RTC_item.last_run_at))

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    if RTC_item.collection_error:
        sub.alert = True
        sub.label(text = "Collection error", icon = "ERROR")
    else:
        sub.label(text = _summarize_test_cases(block_cases))

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "is_enabled", text = "")


def _uilist_unit_tests_draw_test_row(container, case):
    """One label + [?] + 'Run' button row for a single test; failed/errored tests get an extra red line below."""
    row = container.row(align = True)
    split = row.split(factor = 0.6)
    label_text = case.short_label
    if case.cold_start_only:
        label_text += "  (headless only)"
    split.label(text = label_text, icon = _UNIT_TEST_STATUS_ICONS.get(case.status, "RADIOBUT_OFF"))

    controls = split.row(align = True)
    doc_op = controls.operator("dgblocks.show_unit_test_docstring", text = "", icon = "QUESTION")
    doc_op.test_id = case.test_id

    button_area = controls.row()
    # Greyed out rather than hidden: a cold_start_only test only makes sense as part of a
    # genuinely fresh process (see Unit_Test_Suite_Declaration.cold_start_only) — clicking
    # Run on it inside this already-live session would either no-op or be meaningless.
    button_area.enabled = not case.cold_start_only
    op = button_area.operator("dgblocks.run_one_unit_test", text = "Run", icon = "PLAY")
    op.test_id = case.test_id

    if case.status in (Unit_Test_Status.FAILED, Unit_Test_Status.ERROR) and case.error_text:
        err_row = container.row()
        err_row.alert = True
        err_row.label(text = case.error_text, icon = "ERROR")


def _uilist_unit_tests_draw_group_body(context, container, block_id, suite_group, cases):

    group_row = next(
        (g for g in get_Wrapper_Runtime_Cache().get_cache("UNIT_TEST_GROUP_ROWS")
         if g.block_id == block_id and g.suite_group == suite_group),
        None,
    )
    info_row = container.row()
    info_row.label(text = _summarize_test_cases(cases))
    if group_row is not None:
        info_row.label(text = f"Last run: {format_timestamp_for_ui(group_row.last_run_at)}")
    button_area = info_row.row()
    button_area.enabled = not all(c.cold_start_only for c in cases) if cases else False
    op = button_area.operator("dgblocks.run_group_unit_tests", text = "Run Group", icon = "PLAY")
    op.block_id = block_id
    op.suite_group = suite_group

    for case in cases:
        _uilist_unit_tests_draw_test_row(container, case)


def _uilist_unit_tests_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    block_id = RTC_item.block_id
    box = container.box()

    if RTC_item.collection_error:
        box.alert = True
        box.label(text = RTC_item.collection_error, icon = "ERROR")

    all_cases = [c for c in get_Wrapper_Runtime_Cache().get_cache("UNIT_TEST_CASE_CATALOG") if c.block_id == block_id]

    row = box.row()
    row.label(text = _summarize_test_cases(all_cases))
    button_area = row.row()
    button_area.enabled = not all(c.cold_start_only for c in all_cases) if all_cases else False
    op = button_area.operator("dgblocks.run_block_unit_tests", text = "Run All In Block", icon = "PLAY")
    op.block_id = block_id

    if not all_cases:
        box.label(text = "No tests discovered for this block", icon = "INFO")
        return

    distinct_groups = []
    for case in all_cases:
        if case.suite_group not in distinct_groups:
            distinct_groups.append(case.suite_group)

    # Only worth a stack of subpanels when a block actually has >1 group — otherwise flatten
    if len(distinct_groups) <= 1:
        for case in all_cases:
            _uilist_unit_tests_draw_test_row(box, case)
        return

    for suite_group in distinct_groups:
        group_cases = [c for c in all_cases if c.suite_group == suite_group]
        kwargs = {"block_id": block_id, "suite_group": suite_group, "cases": group_cases}
        ui_draw_subpanel(
            context, box,
            f"unit_test_group_{block_id}_{suite_group}",
            f"{suite_group} ({_summarize_test_cases(group_cases)})",
            _uilist_unit_tests_draw_group_body,
            **kwargs,
        )


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

    def _draw_unit_tests_subpanel_body(self, context, container):
        """Draw body of the Unit Tests subpanel: run-all/refresh controls, last-run summary, then the UIList."""
        row = container.row()
        row.scale_y = 1.3
        row.operator("dgblocks.run_all_unit_tests", text = "Run All Unit Tests", icon = "PLAY")
        row.operator("dgblocks.refresh_unit_test_catalog", text = "", icon = "FILE_REFRESH")

        last_report = get_Wrapper_Runtime_Cache().get_cache("LAST_UNIT_TEST_REPORT")
        summary_row = container.row()
        if last_report is None:
            summary_row.label(text = "Never run", icon = "INFO")
        else:
            all_cases = get_Wrapper_Runtime_Cache().get_cache("UNIT_TEST_CASE_CATALOG")
            summary_row.label(
                text = f"Last full run: {format_timestamp_for_ui(last_report.finished_at)} — {_summarize_test_cases(all_cases)}"
            )

        draw_shared_uilist(context, container, "unit_test_block_rows")

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

        # Unit Tests subpanel
        unit_tests_label = f"Unit Tests ({len(core_scene_props.unit_test_block_rows)})"
        ui_draw_subpanel(context, layout, "unit_tests", unit_tests_label, self._draw_unit_tests_subpanel_body)

        # RTC members subpanel (snapshot / clipboard tooling, no BL data behind it)
        rtc_member_count = len(get_Wrapper_Runtime_Cache().get_all_cache_keys())
        rtc_label = f"All RTC Members ({rtc_member_count})"
        ui_draw_subpanel(context, layout, "rtc_members", rtc_label, ui_draw_rtc_members_snapshot)

            
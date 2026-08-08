
import bpy

# Addon-level imports
from ....addon_helpers.data_tools import create_simplified_list_from_csv_string
from ....addon_helpers.ui.helpers import create_ui_box_with_header, uilayout_section_separator

# Inter-block imports
from ...block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ...block_core.core_helpers.constants import _BLOCK_ID as core_block_id, Core_Runtime_Cache_Members
from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache, get_actual_rtc_key # type: ignore

# Intra-block imports
from .constants import Block_Hook_Sources


def _enable_icon(is_enabled: bool) -> str:
    return "HIDE_OFF" if is_enabled else "HIDE_ON"


def uilayout_draw_debug_settings(context: bpy.context, container: bpy.types.UILayout):

    # Call drawing functions in downstream blocks which are hooked for hook_debug_uilayout_draw_console_print_settings.
    # Each block can have its own presentation logic. This logic is triggered from a hook every screen-draw call.
    drawing_hook_func_name = Block_Hook_Sources.hook_debug_uilayout_draw_console_print_settings
    cached_hook_subs = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS)
    func_name = get_actual_rtc_key(Block_Hook_Sources.hook_debug_get_state_data_to_print)
    if func_name in cached_hook_subs:
        for hook_sub_instance in cached_hook_subs[func_name]:
            uilayout_section_separator(container, extra_space = 0)
            block_id = hook_sub_instance.subscriber_block_id
            internal_panel_header, internal_panel_body = container.panel(idname = f"_dummy_dgblocks_console_print_{block_id}", default_closed = True)
            internal_panel_header.alignment = "CENTER"
            internal_panel_header.label(text = f"Print {block_id.upper()} State")
            if internal_panel_body:

                # Drawing is handled inside the hook func, using ui_container
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name = drawing_hook_func_name,
                    subscriber_block_id = block_id,
                    ui_container = internal_panel_body
                )


def _draw_general_section(context, body, debug_props):
    grid = body.grid_flow(columns = 2)
    box_l = grid.box()
    box_l.prop(debug_props, "debug_console_print_should_clear_previous_output")
    box_l.prop(debug_props, "debug_console_print_min_verbosity")
    box_l.prop(debug_props, "debug_console_print_json_indent_width")
    box_l.prop(debug_props, "debug_console_print_filter_data_max_rows_in_each_container")
    box_r = grid.box()
    box_r.prop(debug_props, "debug_console_print_depth_to_truncate")
    box_r.prop(debug_props, "debug_console_print_include_data_type")
    box_r.prop(debug_props, "debug_console_print_include_memory_address")
    box_r.prop(debug_props, "debug_console_print_include_memory_size")
    box_r.prop(debug_props, "debug_console_print_show_filter_indices")


def _draw_keys_section(context, body, debug_props):
    enabled = debug_props.debug_console_print_filter_key_enabled
    header = body.row(align = True)
    header.prop(debug_props, "debug_console_print_filter_key_enabled", text = "Enable Key Filter")
    header.label(text = "", icon = _enable_icon(enabled))

    col = body.column()
    col.enabled = enabled
    col.label(text = "Use comma-separated wildcard strings.")
    col.label(text = "Whitespace & capitalization are ignored.")
    col.label(text = "A branch is kept if any descendant key matches.")
    box = col.box()
    grid = box.grid_flow(columns = 1)
    grid.prop(debug_props, "debug_console_print_filter_key_to_include")
    grid.prop(debug_props, "debug_console_print_filter_key_to_exclude")


def _draw_numeric_filter(context, body, debug_props):
    enabled = debug_props.debug_console_print_numeric_filter_enabled
    box = create_ui_box_with_header(context, body, "Numeric Data Filter (AND-combined)", icon = _enable_icon(enabled))
    header = box.row(align = True)
    header.prop(debug_props, "debug_console_print_numeric_filter_enabled", text = "Enable")
    header.prop(debug_props, "debug_console_print_numeric_filter_mode", text = "")

    col = box.column()
    col.enabled = enabled
    for i, f in enumerate(debug_props.debug_console_print_numeric_filters):
        row = col.row(align = True)
        row.prop(f, "operation", text = "")
        row.prop(f, "value", text = "")
        op = row.operator("dgblocks.debug_console_print_numeric_filter_remove", text = "", icon = "X")
        op.index = i
    col.operator("dgblocks.debug_console_print_numeric_filter_add", text = "Add Numeric Filter", icon = "ADD")


def _draw_string_filter(context, body, debug_props):
    enabled = debug_props.debug_console_print_string_filter_enabled
    box = create_ui_box_with_header(context, body, "String Data Filter (OR-combined)", icon = _enable_icon(enabled))
    header = box.row(align = True)
    header.prop(debug_props, "debug_console_print_string_filter_enabled", text = "Enable")
    header.prop(debug_props, "debug_console_print_string_filter_mode", text = "")

    col = box.column()
    col.enabled = enabled
    for i, f in enumerate(debug_props.debug_console_print_string_filters):
        row = col.row(align = True)
        row.prop(f, "operation", text = "")
        row.prop(f, "text", text = "")
        op = row.operator("dgblocks.debug_console_print_string_filter_remove", text = "", icon = "X")
        op.index = i
    col.operator("dgblocks.debug_console_print_string_filter_add", text = "Add String Filter", icon = "ADD")


def _draw_data_section(context, body, debug_props):
    _draw_numeric_filter(context, body, debug_props)
    uilayout_section_separator(body, extra_space = 0)
    _draw_string_filter(context, body, debug_props)


def ui_draw_filter_settings(context: bpy.context, container: bpy.types.UILayout):

    debug_props = context.scene.dgblocks_debug_console_print_props

    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_print_console_t2", default_closed = True)
    panel_header.label(text = "Settings")
    if panel_body is None:
        return

    # Single radio-button range shared by all three sections.
    radio = panel_body.row(align = True)
    radio.prop(debug_props, "debug_console_print_active_filter_section", expand = True)
    uilayout_section_separator(panel_body, extra_space = 0)

    section = debug_props.debug_console_print_active_filter_section
    if section == "GENERAL":
        _draw_general_section(context, panel_body, debug_props)
    elif section == "KEYS":
        _draw_keys_section(context, panel_body, debug_props)
    elif section == "DATA":
        _draw_data_section(context, panel_body, debug_props)

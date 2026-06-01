
import bpy

# Addon-level imports
from ....addon_helpers.data_tools import  create_simplified_list_from_csv_string
from ....addon_helpers.ui import create_ui_box_with_header, uilayout_section_separator

# Inter-block imports
from ...block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ...block_core.core_helpers.constants import _BLOCK_ID as core_block_id, Core_Runtime_Cache_Members
from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache, get_actual_rtc_key # type: ignore

# Intra-block imports
from .constants import Block_Hook_Sources

def uilayout_draw_debug_settings(context:bpy.context, container:bpy.types.UILayout):
    
    # Call drawing functions in downstrean blocks which are hooked for function hook_debug_uilayout_draw_console_print_settings
    # Each block can have it's own presentation logic. This logic is triggered from a hook every screen-draw call (many times per second)
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

def ui_draw_filter_settings(context:bpy.context, container:bpy.types.UILayout):
    
    debug_props = context.scene.dgblocks_debug_console_print_props
    
    # For console prints  
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_print_console_t2", default_closed=True)
    panel_header.label(text = "Filter settings")
    if panel_body is not None:  
        
        # General Settings
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_general_console_print_settings", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"General Settings")
        if internal_panel_body:
            grid = internal_panel_body.grid_flow(columns=2)
            box_l = grid.box()
            box_l.prop(debug_props, "debug_console_print_should_clear_previous_output")
            box_l.prop(debug_props, "debug_console_print_min_verbosity")
            box_l.prop(debug_props, "debug_console_print_json_indent_width")
            box_r = grid.box()
            box_r.prop(debug_props, "debug_console_print_include_memory_address")
            box_r.prop(debug_props, "debug_console_print_include_data_type")
            
        uilayout_section_separator(panel_body, extra_space = 0)
        
        # Key Filtering
        inclusion_filter_keys = create_simplified_list_from_csv_string(debug_props.debug_console_print_filter_key_to_include)
        inclusion_filter_on = len(inclusion_filter_keys) > 0 and debug_props.debug_console_print_filter_key_inclusion_level != "OFF"
        exclusion_filter_keys = create_simplified_list_from_csv_string(debug_props.debug_console_print_filter_key_to_exclude)
        exclusion_filter_on = len(exclusion_filter_keys) > 0 and debug_props.debug_console_print_filter_key_exclusion_level != "OFF"
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_filter_console_print_keys", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Filter by Dict Keys")
        internal_panel_header.label(text = "", icon = "HIDE_OFF" if (inclusion_filter_on or exclusion_filter_on) else "HIDE_ON")
        if internal_panel_body:
            internal_panel_body.label(text =  "Use Comma-Separated Wildcards Strings.")
            internal_panel_body.label(text =  "Whitespace & capitilization are ignored.")
            internal_panel_body.label(text =  "Only dicts are filtered, tables & lists untouched.")
            box = internal_panel_body.box()
            grid = box.grid_flow(columns=2)
            include_filter_icon = "HIDE_OFF" if inclusion_filter_on > 0 else "HIDE_ON"
            row = grid.row()
            row.alignment = "CENTER"
            row.label(text = "Keys to Include")
            row.label(text = "", icon = include_filter_icon)
            grid.prop(debug_props, "debug_console_print_filter_key_to_include", text = "")
            grid.prop(debug_props, "debug_console_print_filter_key_inclusion_level", text = "")
            exclude_filter_icon = "HIDE_OFF" if exclusion_filter_on > 0 else "HIDE_ON"
            row = grid.row()
            row.alignment = "CENTER"
            row.label(text = "Keys to Exclude")
            row.label(text = "", icon = exclude_filter_icon)
            grid.prop(debug_props, "debug_console_print_filter_key_to_exclude", text = "")
            grid.prop(debug_props, "debug_console_print_filter_key_exclusion_level", text = "")
               
        uilayout_section_separator(panel_body, extra_space = 0)    
            
        # Data Filtering
        has_container_filter = debug_props.debug_console_print_filter_data_max_rows_in_each_container > 0 or debug_props.debug_console_print_depth_to_truncate > 0
        has_numeric_filter = debug_props.debug_console_print_data_numeric_filter_level != "OFF"
        internal_panel_header, internal_panel_body = panel_body.panel(idname = f"_dummy_dgblocks_filter_console_print_values", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Filter by Data")
        internal_panel_header.label(text = "", icon = "HIDE_OFF" if (has_container_filter or has_numeric_filter) else "HIDE_ON")
        if internal_panel_body:
            box = create_ui_box_with_header(context, internal_panel_body, ["Structural (list / set / dict) Filters", "Disabled when = 0"], icon = "HIDE_OFF" if has_container_filter > 0 else "HIDE_ON")
            grid = box.grid_flow(columns=2)
            grid.prop(debug_props, "debug_console_print_filter_data_max_rows_in_each_container")
            grid.prop(debug_props, "debug_console_print_depth_to_truncate")
            box = create_ui_box_with_header(context, internal_panel_body, "Numerical Data Filter", icon = "HIDE_OFF" if has_numeric_filter > 0 else "HIDE_ON")
            grid = box.grid_flow(columns=3)
            grid.alignment = "EXPAND"
            include_filter_icon = "HIDE_OFF" if inclusion_filter_on > 0 else "HIDE_ON"
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_level", text = "")
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_operation", text = "")
            grid.prop(debug_props, "debug_console_print_data_numeric_filter_value", text = "")
            
        uilayout_section_separator(panel_body, extra_space = 0)


import bpy # type: ignore

# Addon-level imports
from ....addon_helpers.data_tools import  create_simplified_list_from_csv_string
from ....addon_helpers.ui import create_ui_box_with_header, uilayout_section_separator

# Inter-block imports
from ...block_core.core_features.hooks import Wrapper_Hooks
from ...block_core.core_helpers.constants import _BLOCK_ID as core_block_id

# Intra-block imports
from .constants import Block_Hook_Sources, Core_Debugging_Print_Options

def uilayout_draw_core_block_console_print_panel(context:bpy.context, container:bpy.types.UILayout, block_id:str):
    
    debug_settings = context.scene.dgblocks_debug_console_print_props
    button_scale = 1.5
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All Hook Data (Table, Unfiltered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.HOOK_SUBSCRIBERS
    split = box.split()
    row_l = split.row()
    row_r = split.row()
    # row_l.label(text = "Sort by")
    row_l.prop(debug_settings, "debug_block_hooks_table_sort_by") 
    # row_r.prop(debug_settings, "debug_block_hooks_table_include_unused") 

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All RTC Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_RTC_MEMBERS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Scene Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_BL_SCENE_PROPS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Preferences Data (JSONified, Filtered)")
    op.source_block_id = block_id
    op.other_input = Core_Debugging_Print_Options.ALL_BLOCKS_BL_PREFERENCES_PROPS

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "UNIT TESTS")
    op.source_block_id = "TEST"

def uilayout_draw_debug_settings(context:bpy.context, container:bpy.types.UILayout):
    
    debug_props = context.scene.dgblocks_debug_console_print_props
    
    box = container.box()

    # Call drawing function for core-block. Since core-block is known dependency of this block, it's reference can be hardcoded here, unlike blocks in the next step
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_print_console", default_closed=True)
    panel_header.label(text = f"Print {core_block_id.upper()} State")
    if panel_body is not None:  
        uilayout_draw_core_block_console_print_panel(context, panel_body, core_block_id)

    # Call drawing functions in downstrean blocks which are hooked for function hook_debug_uilayout_draw_console_print_settings
    # Each block can have it's own presentation logic. This logic is triggered from a hook every screen-draw call (many times per second)
    hook_func_name = Block_Hook_Sources.DEBUG_UI_DRAW_FOR_BLOCK_CONSOLE_PRINT
    all_blocks_metadata_for_hook = Wrapper_Hooks.get_subscriber_blocks_of_hook(hook_func_name) # get_hooked_blocks_metadata_for_func(hook_func_name
    for idx, block_hook_metadata in enumerate(all_blocks_metadata_for_hook):
        uilayout_section_separator(container, extra_space = 0)
        block_id = block_hook_metadata.subscriber_block_module._BLOCK_ID
        internal_panel_header, internal_panel_body = container.panel(idname = f"_dummy_dgblocks_console_print_{block_id}", default_closed = True)
        internal_panel_header.alignment = "CENTER"
        internal_panel_header.label(text = f"Print {block_id.upper()} State")
        if internal_panel_body: 
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name = hook_func_name, 
                subscriber_block_id = block_id, 
                ui_container = internal_panel_body
            )

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

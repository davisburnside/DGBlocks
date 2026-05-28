import os
import sys
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config.static_settings import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix
from ...addon_helpers.generic_tools import get_self_block_module, clear_console
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import block_core
from ..block_core.core_features.loggers.feature_wrapper import Core_Block_Loggers, get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..block_core.core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .helpers.constants import Block_Hook_Sources, debug_console_print_dict_key_filter_items, debug_console_print_data_filter_items, debug_sort_hooks_choice_items, numeric_comparison_enum_items
from .helpers.text_formatting import extract_core_block_data_to_print, make_pretty_json_string_from_data
from .helpers.ui_drawing import uilayout_draw_debug_settings

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-debug-console-print" # Defined in constants, To Prevent circular imports. Other Blocks can assign directly
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = ["block-core"] 

# ==============================================================================================================================
# BLENDER DATA FOR BLOCK
# ==============================================================================================================================

class DGBLOCKS_PG_Debug_Props_Profile(bpy.types.PropertyGroup):
    # Affects console printing for state data of blocks

    # General settings
    debug_console_print_should_clear_previous_output: bpy.props.BoolProperty(default = True, name = "Clear Previous Logs?") # type: ignore
    debug_console_print_min_verbosity: bpy.props.BoolProperty(default = False, name = "Minimize Verbosity?") # type: ignore
    debug_console_print_json_indent_width: bpy.props.IntProperty(default = 4, min = 0, max=16, name = "JSON Indent Size") # type: ignore
    debug_console_print_include_memory_address: bpy.props.BoolProperty(default = False, name = "Show Memory address?") # type: ignore
    debug_console_print_include_data_type: bpy.props.BoolProperty(default = False, name = "Show Data Type?") # type: ignore

    # Dict key filter
    debug_console_print_filter_key_to_include: bpy.props.StringProperty(name = "Keys to Include", options = {"TEXTEDIT_UPDATE"}) # type: ignore
    debug_console_print_filter_key_to_exclude: bpy.props.StringProperty(name = "Keys to Exclude", options = {"TEXTEDIT_UPDATE"}) # type: ignore
    debug_console_print_filter_key_inclusion_level: bpy.props.EnumProperty(
            items= debug_console_print_dict_key_filter_items,
            name = "Filter Level",
            default="FULL") # type: ignore
    debug_console_print_filter_key_exclusion_level: bpy.props.EnumProperty(
            items=debug_console_print_dict_key_filter_items,
            name = "Filter Level",
            default="FULL") # type: ignore
    
    # Data filter
    debug_console_print_filter_data_max_rows_in_each_container: bpy.props.IntProperty(default = 0, min = 0, name = "Max Rows to Print") # type: ignore
    debug_console_print_depth_to_truncate: bpy.props.IntProperty(default = 2, min = 0, name = "Max Depth to Search") # type: ignore
    
    # Numeric Data filter
    debug_console_print_data_numeric_filter_level: bpy.props.EnumProperty(
            items = debug_console_print_data_filter_items,
            default="OFF") # type: ignore
    debug_console_print_data_numeric_filter_value: bpy.props.FloatProperty(default = 0) # type: ignore
    debug_console_print_data_numeric_filter_operation: bpy.props.EnumProperty(items = numeric_comparison_enum_items) # type: ignore

    # Table Column Sorting
    debug_block_hooks_table_sort_by: bpy.props.EnumProperty(items = debug_sort_hooks_choice_items, name = "Sort By") # type: ignore

# ==============================================================================================================================
# OPERATORS 
# ==============================================================================================================================

class DGBLOCKS_OT_Debug_Console_Print_Block_Diagnostics(bpy.types.Operator):
    bl_idname = "dgblocks.debug_console_print_block_diagnostics"
    bl_label = "Print Block Diagnostics Data to Console"
    bl_options = {"REGISTER"}
    
    source_block_id: bpy.props.StringProperty() # type: ignore 
    other_input: bpy.props.StringProperty() # type: ignore 
    
    # This operator can always be executed, even when add
    def execute(self, context):
        
        # Clear previous logs, if needed
        core_block_props = context.scene.dgblocks_debug_console_print_props
        if core_block_props.debug_console_print_should_clear_previous_output:
            clear_console()

        # When printing for core-block (Hook Tables & RTC JSON), the "get data" function is inside this block
        if self.source_block_id == block_core._BLOCK_DECLARATION.block_id:
            raw_data_to_print = extract_core_block_data_to_print(context, self.other_input)
        
        # When printing for other blocks, the "get data" function is extracted from that subscriber block with a hook
        else:
            raw_data_to_print = Wrapper_Hooks.run_hooked_funcs(
                hook_func_name = Block_Hook_Sources.hook_debug_get_state_data_to_print, 
                subscriber_block_id = self.source_block_id, 
                context = context,
                other_input = self.other_input
            )

        # Format, filter, prettify, then print
        string_to_print = make_pretty_json_string_from_data(
                raw_data_to_print, 
                filter_inclusion_dict_keys_raw_str = core_block_props.debug_console_print_filter_key_to_include,
                filter_exclusion_dict_keys_raw_str = core_block_props.debug_console_print_filter_key_to_exclude,
                filter_inclusion_dict_keys_level = core_block_props.debug_console_print_filter_key_inclusion_level,
                filter_exclusion_dict_keys_level = core_block_props.debug_console_print_filter_key_exclusion_level,
                filter_numerical_op = core_block_props.debug_console_print_data_numeric_filter_operation,
                filter_numerical_value = core_block_props.debug_console_print_data_numeric_filter_value,
                filter_numerical_level = core_block_props.debug_console_print_data_numeric_filter_level,
                max_rows_of_each_container = core_block_props.debug_console_print_filter_data_max_rows_in_each_container,
                max_depth_of_container_search = core_block_props.debug_console_print_depth_to_truncate,
                min_verbosity = core_block_props.debug_console_print_min_verbosity,
                show_type_labels = core_block_props.debug_console_print_include_data_type,
                show_memory_address = core_block_props.debug_console_print_include_memory_address,
                show_memory_duplicates = core_block_props.debug_console_print_include_memory_address,
                indent=core_block_props.debug_console_print_json_indent_width)
        
        print(string_to_print)
            
        return {"FINISHED"}

# ==============================================================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
# ==============================================================================================================================

class DGBLOCKS_PT_Debugging_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"DGBLOCKS_PT_Debugging_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")

    def draw(self, context):
        uilayout_draw_debug_settings(context, self.layout)

# ==============================================================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Debug_Props_Profile,
    DGBLOCKS_OT_Debug_Console_Print_Block_Diagnostics,
    DGBLOCKS_PT_Debugging_Panel,
]


# ==============================================================================================================================
# REQUIRED 
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__], # this __init__.py file
    block_id = "block-debug-console", # unique block id
    block_dependencies = ["block-core"], # ids of blocks that this one depends on
    block_bpy_classes = _block_classes_to_register, # Blender-registerable classes
    block_loggers = Core_Block_Loggers,
)

def register_block_props():
    bpy.types.Scene.dgblocks_debug_console_print_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Debug_Props_Profile)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_debug_console_print_props"):
        del bpy.types.Scene.dgblocks_debug_console_print_props

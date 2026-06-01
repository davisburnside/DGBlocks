import os
import sys
import bpy # type: ignore

# Addon-level imports
from ...addon_config.static_settings import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix
from ...addon_helpers.generic_tools import get_self_block_module, clear_console
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_helpers.text_formatting_tools import make_pretty_json_string_from_data
from ...addon_helpers.ui import ui_draw_block_panel_header

# Inter-block imports
from .. import block_core
from ..block_core.core_features.loggers.feature_wrapper import Core_Block_Loggers, get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..block_core.core_helpers.debugging import debug_sort_hooks_choice_items

# Intra-block imports
from .helpers.constants import (
    Block_Hook_Sources,
    debug_console_print_filter_section_items,
    debug_console_print_filter_mode_items,
    numeric_comparison_enum_items,
    string_comparison_enum_items,
)
from .helpers.ui import ui_draw_filter_settings, uilayout_draw_debug_settings

_BLOCK_ID = "block-debug-console-print" # Defined in constants, To Prevent circular imports. Other Blocks can assign directly

# ==============================================================================================================================
# SUPPORT CLASSES
# ==============================================================================================================================

class DGBLOCKS_PG_Numeric_Filter(bpy.types.PropertyGroup):
    # One numeric leaf-value comparison. Multiple rows are AND-combined (e.g. ">= 0" and "< 5").
    operation: bpy.props.EnumProperty(items = numeric_comparison_enum_items, name = "Op") # type: ignore
    value: bpy.props.FloatProperty(default = 0.0, name = "Value") # type: ignore


class DGBLOCKS_PG_String_Filter(bpy.types.PropertyGroup):
    # One string leaf-value comparison. Multiple rows are OR-combined. Case-insensitive.
    operation: bpy.props.EnumProperty(items = string_comparison_enum_items, name = "Op") # type: ignore
    text: bpy.props.StringProperty(default = "", name = "Text") # type: ignore


class DGBLOCKS_PG_Debug_Props_Profile(bpy.types.PropertyGroup):
    # Affects console printing for state data of blocks

    # Which filter section the single radio range currently shows
    debug_console_print_active_filter_section: bpy.props.EnumProperty(
            items = debug_console_print_filter_section_items,
            name = "Settings Section",
            default = "GENERAL") # type: ignore

    # General settings
    debug_console_print_should_clear_previous_output: bpy.props.BoolProperty(default = True, name = "Clear Previous Logs?") # type: ignore
    debug_console_print_min_verbosity: bpy.props.BoolProperty(default = False, name = "Minimize Verbosity?") # type: ignore
    debug_console_print_json_indent_width: bpy.props.IntProperty(default = 4, min = 0, max=16, name = "JSON Indent Size") # type: ignore
    debug_console_print_include_memory_address: bpy.props.BoolProperty(default = False, name = "Show Memory address?") # type: ignore
    debug_console_print_include_memory_size: bpy.props.BoolProperty(default = False, name = "Show Memory Size (KB)?") # type: ignore
    debug_console_print_include_data_type: bpy.props.BoolProperty(default = False, name = "Show Data Type?") # type: ignore
    debug_console_print_filter_data_max_rows_in_each_container: bpy.props.IntProperty(default = 0, min = 0, name = "Max Rows to Print") # type: ignore
    debug_console_print_depth_to_truncate: bpy.props.IntProperty(default = 2, min = 0, name = "Max Depth to Search") # type: ignore

    # Dict key filter
    debug_console_print_filter_key_enabled: bpy.props.BoolProperty(default = False, name = "Enable Key Filter") # type: ignore
    debug_console_print_filter_key_to_include: bpy.props.StringProperty(name = "Keys to Include", options = {"TEXTEDIT_UPDATE"}) # type: ignore
    debug_console_print_filter_key_to_exclude: bpy.props.StringProperty(name = "Keys to Exclude", options = {"TEXTEDIT_UPDATE"}) # type: ignore

    # Numeric data filter (multiple rows, AND-combined)
    debug_console_print_numeric_filter_enabled: bpy.props.BoolProperty(default = False, name = "Enable Numeric Filter") # type: ignore
    debug_console_print_numeric_filter_mode: bpy.props.EnumProperty(items = debug_console_print_filter_mode_items, default = "INCLUDE", name = "Mode") # type: ignore
    debug_console_print_numeric_filters: bpy.props.CollectionProperty(type = DGBLOCKS_PG_Numeric_Filter) # type: ignore
    debug_console_print_numeric_filters_selected_idx: bpy.props.IntProperty() # type: ignore

    # String data filter (multiple rows, OR-combined)
    debug_console_print_string_filter_enabled: bpy.props.BoolProperty(default = False, name = "Enable String Filter") # type: ignore
    debug_console_print_string_filter_mode: bpy.props.EnumProperty(items = debug_console_print_filter_mode_items, default = "INCLUDE", name = "Mode") # type: ignore
    debug_console_print_string_filters: bpy.props.CollectionProperty(type = DGBLOCKS_PG_String_Filter) # type: ignore
    debug_console_print_string_filters_selected_idx: bpy.props.IntProperty() # type: ignore

    # Table Column Sorting
    debug_block_hooks_table_sort_by: bpy.props.EnumProperty(items = debug_sort_hooks_choice_items, name = "Sort By") # type: ignore


class DGBLOCKS_OT_Debug_Console_Print_Numeric_Filter_Add(bpy.types.Operator):
    bl_idname = "dgblocks.debug_console_print_numeric_filter_add"
    bl_label = "Add Numeric Filter"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        props = context.scene.dgblocks_debug_console_print_props
        props.debug_console_print_numeric_filters.add()
        props.debug_console_print_numeric_filters_selected_idx = len(props.debug_console_print_numeric_filters) - 1
        return {"FINISHED"}


class DGBLOCKS_OT_Debug_Console_Print_Numeric_Filter_Remove(bpy.types.Operator):
    bl_idname = "dgblocks.debug_console_print_numeric_filter_remove"
    bl_label = "Remove Numeric Filter"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty(default = -1) # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_debug_console_print_props
        collection = props.debug_console_print_numeric_filters
        idx = self.index if self.index >= 0 else props.debug_console_print_numeric_filters_selected_idx
        if 0 <= idx < len(collection):
            collection.remove(idx)
            props.debug_console_print_numeric_filters_selected_idx = min(idx, len(collection) - 1)
        return {"FINISHED"}


class DGBLOCKS_OT_Debug_Console_Print_String_Filter_Add(bpy.types.Operator):
    bl_idname = "dgblocks.debug_console_print_string_filter_add"
    bl_label = "Add String Filter"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        props = context.scene.dgblocks_debug_console_print_props
        props.debug_console_print_string_filters.add()
        props.debug_console_print_string_filters_selected_idx = len(props.debug_console_print_string_filters) - 1
        return {"FINISHED"}


class DGBLOCKS_OT_Debug_Console_Print_String_Filter_Remove(bpy.types.Operator):
    bl_idname = "dgblocks.debug_console_print_string_filter_remove"
    bl_label = "Remove String Filter"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty(default = -1) # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_debug_console_print_props
        collection = props.debug_console_print_string_filters
        idx = self.index if self.index >= 0 else props.debug_console_print_string_filters_selected_idx
        if 0 <= idx < len(collection):
            collection.remove(idx)
            props.debug_console_print_string_filters_selected_idx = min(idx, len(collection) - 1)
        return {"FINISHED"}


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

        kwargs = {"other_input": self.other_input}
        raw_data_to_print = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name = Block_Hook_Sources.hook_debug_get_state_data_to_print,
            subscriber_block_id = self.source_block_id,
            **kwargs
        )

        # Flatten the CollectionProperty filter rows into plain python tuples for the formatter
        numeric_filters = [(row.operation, row.value) for row in core_block_props.debug_console_print_numeric_filters]
        string_filters = [(row.operation, row.text) for row in core_block_props.debug_console_print_string_filters]

        # Format, filter, prettify, then print
        string_to_print = make_pretty_json_string_from_data(
                raw_data_to_print,
                filter_keys_enabled = core_block_props.debug_console_print_filter_key_enabled,
                filter_inclusion_dict_keys_raw_str = core_block_props.debug_console_print_filter_key_to_include,
                filter_exclusion_dict_keys_raw_str = core_block_props.debug_console_print_filter_key_to_exclude,
                numeric_filter_enabled = core_block_props.debug_console_print_numeric_filter_enabled,
                numeric_filter_mode = core_block_props.debug_console_print_numeric_filter_mode,
                numeric_filters = numeric_filters,
                string_filter_enabled = core_block_props.debug_console_print_string_filter_enabled,
                string_filter_mode = core_block_props.debug_console_print_string_filter_mode,
                string_filters = string_filters,
                max_rows_of_each_container = core_block_props.debug_console_print_filter_data_max_rows_in_each_container,
                max_depth_of_container_search = core_block_props.debug_console_print_depth_to_truncate,
                min_verbosity = core_block_props.debug_console_print_min_verbosity,
                show_type_labels = core_block_props.debug_console_print_include_data_type,
                show_memory_address = core_block_props.debug_console_print_include_memory_address,
                show_memory_duplicates = core_block_props.debug_console_print_include_memory_address,
                show_memory_size = core_block_props.debug_console_print_include_memory_size,
                indent = core_block_props.debug_console_print_json_indent_width)

        print(string_to_print)

        return {"FINISHED"}


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
        ui_draw_filter_settings(context, self.layout)
        uilayout_draw_debug_settings(context, self.layout)

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Numeric_Filter,
    DGBLOCKS_PG_String_Filter,
    DGBLOCKS_PG_Debug_Props_Profile,
    DGBLOCKS_OT_Debug_Console_Print_Numeric_Filter_Add,
    DGBLOCKS_OT_Debug_Console_Print_Numeric_Filter_Remove,
    DGBLOCKS_OT_Debug_Console_Print_String_Filter_Add,
    DGBLOCKS_OT_Debug_Console_Print_String_Filter_Remove,
    DGBLOCKS_OT_Debug_Console_Print_Block_Diagnostics,
    DGBLOCKS_PT_Debugging_Panel,
]


# ==============================================================================================================================
# REQUIRED 
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__], # this __init__.py file
    block_id = _BLOCK_ID, # unique block id
    block_dependencies = ["block-core"], # ids of blocks that this one depends on
    block_bpy_classes = _block_classes_to_register, # Blender-registerable classes
    block_hook_sources = Block_Hook_Sources,
)

def register_block_props():
    bpy.types.Scene.dgblocks_debug_console_print_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Debug_Props_Profile)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_debug_console_print_props"):
        del bpy.types.Scene.dgblocks_debug_console_print_props

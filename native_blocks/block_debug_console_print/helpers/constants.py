
from enum import Enum, StrEnum, auto
import bpy

from ....addon_helpers.data_structures import Hook_Source_Declaration

class Block_Hook_Sources(Enum):

    hook_debug_get_state_data_to_print = Hook_Source_Declaration({})
    hook_debug_uilayout_draw_console_print_settings = Hook_Source_Declaration({"ui_container": bpy.types.UILayout})


debug_console_print_dict_key_filter_items = [
        ("OFF", "Filter Disabled", "Filter Disabled"), 
        ("LEAF", "Filter only Leaf Nodes", "Filter only Leaf Node"),
        ("BRANCH", "Filter only Branch Nodes", ""),
        ("FULL", "Filter all Nodes", "Filter all Nodes")]

debug_console_print_data_filter_items = [
        ("OFF", "Filter Off", "Filter is Disabled"), 
        ("FILTER-INCLUDE", "Include Numbers", "Only Include values"),
        ("FILTER-EXCLUDE", "Exclude Numbers", "Exclude values")]

numeric_comparison_enum_items = [
        (">", ">", ">"), 
        (">=", ">=", ">="),
        ("==", "==", "=="), 
        ("!=", "!=", "!="), 
        ("<=", "<=", "<="), 
        ("<", "<", "<")]

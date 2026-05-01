
from enum import Enum, StrEnum, auto
import bpy

class Block_Hook_Sources(Enum):

    DEBUG_GET_BLOCK_DATA = ("hook_debug_get_state_data_to_print", {})
    DEBUG_UI_DRAW_FOR_BLOCK_CONSOLE_PRINT = ("hook_debug_uilayout_draw_console_print_settings", {"layout": bpy.types.UILayout})


debug_sort_hooks_choice_items = [
    ("timestamp_ms_last_attempt", "Time Last Called", "Time Last Called"),
    ("is_hook_enabled", "Is Enabled", "Is Enabled"),
    ("count_hook_propagate_success", "Success Count", "Number of successful hook calls"),
    ("count_hook_propagate_failure", "Failure Count", "Number of hook calls that raised an exception"),
    ("count_bypass_via_data_filter", "Bypass: Data Filter", "Bypassed by @hook_data_filter predicate"),
    ("count_bypass_via_status", "Bypass: Status", "Bypassed by manual flag or re-entrancy guard"),
    ("count_bypass_via_frequency", "Bypass: Frequency", "Bypassed by min_ms_between_runs rate limit"),
    ("average_runtime", "(ms) Avg Exec Time", "Average execution time per successful call"),
]

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

class Core_Debugging_Print_Options(StrEnum):
    HOOK_SOURCES = auto()
    HOOK_SUBSCRIBERS = auto()
    ALL_BLOCKS_RTC_MEMBERS = auto()
    ALL_BLOCKS_BL_SCENE_PROPS = auto()
    ALL_BLOCKS_BL_PREFERENCES_PROPS = auto()
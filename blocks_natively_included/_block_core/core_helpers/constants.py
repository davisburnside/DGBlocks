
from enum import Enum, StrEnum, auto
from types import ModuleType
from typing import Any, Callable, Dict, Optional
import bpy #type: ignore

from ....addon_data_structures import Global_Addon_State

_BLOCK_ID = "block-core"

#=================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
# Enum classes are used to allow typing & autocomplete, minimizing "magic-strings" antipattern
# Enum class values must have both unique names & unique values. Non-unique values cause names to become aliases of each other
#=================================================================================

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Core_Block_Hook_Sources(Enum):
    CORE_EVENT_POST_REG_INIT = ("hook_post_register_init", {"context": bpy.types.Context, "some_str": str})
    CORE_EVENT_POST_UNDO = ("hook_core_event_undo", {"context": bpy.types.Context, "some_str": str})
    CORE_EVENT_POST_REDO = ("hook_core_event_redo", {"context": bpy.types.Context, "some_str": str})
    CORE_EVENT_BLOCK_REGISTERED = ("hook_block_registered", {"block_name": str, "block_version": tuple})
    CORE_EVENT_BLOCK_UNREGISTERED = ("hook_block_unregistered", {"block_name": str, "block_version": tuple})

# name = logger ID
# value[0] = logger display name & default level
# value[1] = logger display name & default level
class Core_Block_Loggers(Enum):
    ROOT = ("root", "DEBUG")
    HOOKS = ("hooks", "DEBUG")
    BLOCK_MGMT = ("core-events", "DEBUG")
    REGISTRATE = ("register", "DEBUG")
    POST_REGISTRATE = ("post-reg", "DEBUG")
    UI = ("ui", "WARNING")

# name = RTC Member ID 
# value[0] = actual RTC dict key
# value[1] = default data for RTC key
class Core_Runtime_Cache_Members(Enum):
    ADDON_METADATA = ("ADDON_METADATA", Global_Addon_State)
    REGISTRY_ALL_BLOCKS = ("REGISTRY_ALL_BLOCKS", [])
    REGISTRY_ALL_FEATURE_WRAPPERS = ("REGISTRY_ALL_FEATURE_WRAPPERS", [])
    REGISTRY_ALL_HOOK_SOURCES = ("REGISTRY_ALL_HOOK_SOURCES", [])
    REGISTRY_ALL_HOOK_SUBSCRIBERS = ("REGISTRY_ALL_HOOK_SUBSCRIBERS", [])
    REGISTRY_ALL_LOGGERS = ("REGISTRY_ALL_LOGGERS", [])
    META_REGISTRIES_BEING_SYNCED = ("META_REGISTRIES_BEING_SYNCED", [])
    UI_ALERTS = ("UI_ALERTS", {})
    UI_WORDWRAP_WIDTHS = ("UI_WORDWRAP_WIDTHS", {})
    
#=================================================================================
# OTHER
#=================================================================================

log_timestring_format = "%Y-%m-%d %H:%M:%S"

# Must match fields in RTC_Hook_Subscriber_Instance
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

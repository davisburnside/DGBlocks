
from enum import Enum, StrEnum, auto
from types import ModuleType
from typing import Any, Callable, Dict, Optional
import bpy #type: ignore

from ....addon_helpers.data_structures import Global_Addon_State, Abstract_Feature_Wrapper

_BLOCK_ID = "block-core"

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
# Enum classes are used to allow typing & autocomplete, minimizing "magic-strings" antipattern
# Enum class values must have both unique names & unique values. Non-unique values cause names to become aliases of each other
# ==============================================================================================================================

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Core_Block_Hook_Sources(Enum):
    CORE_EVENT_POST_UNDO = ("hook_core_event_undo", {})
    CORE_EVENT_POST_REDO = ("hook_core_event_redo", {})
    CORE_EVENT_BLOCKS_REGISTERED = ("hook_block_registered", {"block_instances": list})
    CORE_EVENT_BLOCKS_UNREGISTERED = ("hook_block_unregistered", {"block_instances": list})

# name = logger ID
# value[0] = logger display name & default level
# value[1] = logger display name & default level
class Core_Block_Loggers(Enum):
    ROOT = ("root", "DEBUG")
    HOOKS = ("hooks", "DEBUG")
    BLOCK_MGMT = ("core-events", "DEBUG")
    DATA_SYNC = ("data-sync", "DEBUG")
    REGISTRATE = ("register", "DEBUG")
    POST_REGISTRATE = ("post-reg", "DEBUG")
    UI = ("ui", "WARNING")

# name = RTC Member ID 
# value[0] = actual RTC dict key
# value[1] = default data for RTC key
class Core_Runtime_Cache_Members(Enum):
    ADDON_METADATA = ("ADDON_METADATA", Global_Addon_State)
    REGISTRY_ALL_BLOCKS = ("REGISTRY_ALL_BLOCKS", [])
    REGISTRY_ALL_FWCS = ("REGISTRY_ALL_FWCS", [])
    REGISTRY_ALL_HOOK_SOURCES = ("REGISTRY_ALL_HOOK_SOURCES", [])
    REGISTRY_ALL_HOOK_SUBSCRIBERS = ("REGISTRY_ALL_HOOK_SUBSCRIBERS", [])
    REGISTRY_ALL_LOGGERS = ("REGISTRY_ALL_LOGGERS", [])
    META_REGISTRIES_BEING_SYNCED = ("META_REGISTRIES_BEING_SYNCED", [])
    UI_ALERTS = ("UI_ALERTS", {})
    UI_WORDWRAP_WIDTHS = ("UI_WORDWRAP_WIDTHS", {})
    
# ==============================================================================================================================
# OTHER
# ==============================================================================================================================

log_timestring_format = "%Y-%m-%d %H:%M:%S"

from enum import Enum, StrEnum, auto
from types import ModuleType
from typing import Any, Callable, Dict, Optional
import bpy #type: ignore

from ....addon_helpers.data_structures import Global_Addon_State, Hook_Source_Definition, Logger_Definition, RTC_Member_Definition, RTC_Member_Data_Mirror_Definition

_BLOCK_ID = "block-core"

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members

class Core_Block_Loggers(Enum):
    HOOKS = Logger_Definition("INFO")
    BLOCK_MGMT = Logger_Definition("DEBUG")
    RTC_DATA_SYNC = Logger_Definition("DEBUG")
    REGISTRATE = Logger_Definition("DEBUG")
    POST_REGISTRATE = Logger_Definition("DEBUG")
    UI = Logger_Definition("WARNING")
    TRACKED_DATABLOCK_TYPES = Logger_Definition("DEBUG")
    SCENE_MONITOR = Logger_Definition("DEBUG")

class Core_Block_Hook_Sources(Enum):
    hook_core_event_undo = Hook_Source_Definition({})
    hook_core_event_redo = Hook_Source_Definition({})
    hook_block_registered = Hook_Source_Definition({"block_instances": list})
    hook_block_unregistered = Hook_Source_Definition({"block_instances": list})
    SCENE_MONITOR_SCENE_CHANGED = Hook_Source_Definition({"old_scene": str, "new_scene": str})
    SCENE_MONITOR_ACTIVE_SCENE_CHANGED = Hook_Source_Definition({"old_id": tuple, "new_id": tuple})
    SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED = Hook_Source_Definition({"old_id": tuple, "new_id": tuple})
    SCENE_MONITOR_ACTIVE_MODE_CHANGED = Hook_Source_Definition({"old_id": tuple, "new_id": tuple})
    SCENE_MONITOR_ACTIVE_OBJ_CHANGED = Hook_Source_Definition({"old_id": tuple, "new_id": tuple})

class Core_Runtime_Cache_Members(Enum):
    ADDON_METADATA = RTC_Member_Definition(Global_Addon_State())
    REGISTRY_ALL_BLOCKS = RTC_Member_Definition([])
    REGISTRY_ALL_FWCS = RTC_Member_Definition([])
    REGISTRY_ALL_HOOK_SOURCES = RTC_Member_Definition([])
    REGISTRY_ALL_HOOK_SUBSCRIBERS = RTC_Member_Definition([])
    REGISTRY_ALL_LOGGERS = RTC_Member_Definition([])
    META_REGISTRIES_BEING_SYNCED = RTC_Member_Definition([])

class Core_Data_Mirrors(Enum):
    HOOKS_LIST = RTC_Member_Data_Mirror_Definition(
        RTC_key = "REGISTRY_ALL_BLOCKS",
        FWC_name = "Wrapper_Hooks",
        mirrored_key_field_names = ["hook_func_name", "subscriber_block_id"], 
        mirrored_data_field_names = ["src_block_id", "is_hook_enabled"],
        default_data_path_in_scene = "dgblocks_core_props.managed_blocks",
    )
    LOGGERS_LIST = RTC_Member_Data_Mirror_Definition(
        RTC_key = "REGISTRY_ALL_LOGGERS",
        FWC_name = "Wrapper_Loggers",
        mirrored_key_field_names = ["logger_name"], 
        mirrored_data_field_names = ["level_name", "src_block_id"],
        default_data_path_in_scene = "dgblocks_core_props.managed_loggers",
    )
    BLOCK_MGMT_LIST = RTC_Member_Data_Mirror_Definition(
        RTC_key = "REGISTRY_ALL_BLOCKS",
        FWC_name = "Wrapper_Control_Plane",
        mirrored_key_field_names = ["block_id"], 
        mirrored_data_field_names = ["should_block_be_enabled", "is_block_enabled", "is_block_valid", "is_block_dependencies_valid_and_enabled", "block_disabled_reason"],
        default_data_path_in_scene = "dgblocks_core_props.managed_blocks",
    )

# ==============================================================================================================================
# OTHER
# ==============================================================================================================================

log_timestring_format = "%Y-%m-%d %H:%M:%S"
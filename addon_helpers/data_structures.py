
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from types import ModuleType
from typing import Callable, Optional, Type
from addon_helpers.FWC_abstracts import Abstract_Feature_Wrapper
import bpy # type: ignore

# ==============================================================================================================================
# ADDON STATE

@dataclass
class Global_Addon_State():
    POST_REG_INIT_HAS_RUN: bool = False
    ADDON_STARTED_SUCCESSFULLY: bool = False
    CURRENT_MODE: str = None
    CURRENT_SCENE_ID: tuple[str, str] = None # (name, session_uid)
    CURRENT_WORKSPACE_ID: tuple[str, str] = None # (name, session_uid)
    CURRENT_ACTIVE_OBJ: tuple[str, str] = None # (name, session_uid)

# ==============================================================================================================================
# CORE FEATURES

@dataclass(eq=False)
class Hook_Source_Declaration():
    arg_types: dict[str, any]
    hook_func_name: str = field(default = None)

@dataclass(eq=False)
class Logger_Declaration():
    default_level: str
    logger_name: str = field(default = None)

@dataclass(eq=False)
class RTC_Member_Declaration():
    default_value: any
    cache_key: str = field(default = None)

@dataclass(eq=False)
class RTC_Member_Data_Mirror_Declaration():
    RTC_key: str
    FWC_name: str
    mirrored_key_field_names: list[str]
    mirrored_data_field_names: list[str]
    default_data_path_in_scene: Optional[str]


@dataclass(eq=False)
class Block_Declaration():
    block_id: str
    block_dependencies: list[str]
    block_bpy_classes: list[bpy.types]
    block_feature_wrapper_classes: list[Callable]
    block_loggers: Enum
    block_hook_sources: Enum
    block_RTC_members: Enum
    block_data_mirrors: Enum

# ==============================================================================================================================
# COMMON ENUMS

class Enum_Sync_Events(StrEnum):
    ADDON_INIT = auto()
    ADDON_SHUTDOWN = auto()
    PROPERTY_UPDATE = auto()
    PROPERTY_UPDATE_UNDO = auto()
    PROPERTY_UPDATE_REDO = auto()
    FORCE_RESTORE_RTC = auto()
    
class Enum_Sync_Actions(StrEnum):
    CREATE = auto()
    REMOVE = auto()
    EDIT = auto()
    MOVE = auto()



# ==============================================================================================================================
# FEATURE WRAPPER SUPPORT CLASSES
# ==============================================================================================================================

@dataclass 
class RTC_FWC_Data_Mirror_Instance:
    
    RTC_key: str # cache key, must be unique
    RTC_member_type: str # enum <"list"> / <"dict">
    mirrored_key_field_names: list[str] # determines unique, canonical records. Field values must be str, int, tuple...
    mirrored_data_field_names: list[str] # fields synced between BL & RTC records when key_fields match

    # If None, the FWC must implement 'update_BL_with_mirrored_RTC_data' or 'update_RTC_with_mirrored_BL_data'
    default_data_path_in_scene: Optional[str] = field(default = None)

    # Updates for every sync attempt
    timestamp_last_BL_data_refresh: int = field(default = -1)
    timestamp_last_RTC_data_refresh: int = field(default = -1)

    # Validation happens a few steps after creation, once bpy is available
    is_valid:bool = field(default = True)
    error_reason: str = field(default = None)

@dataclass
class RTC_FWC_Instance:
    src_block_id: str
    feature_name: str
    actual_class: Type[Abstract_Feature_Wrapper]
    has_BL_mirrored_data: bool
    data_mirrors: list[Type[RTC_FWC_Data_Mirror_Instance]] = field(default = list)

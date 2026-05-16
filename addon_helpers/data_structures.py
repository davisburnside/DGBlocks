
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import Optional, Type
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
# CORE FEATURE DEFINITIONS

@dataclass(eq=False)
class Hook_Source_Definition():
    arg_types: dict[str, any]

@dataclass(eq=False)
class Logger_Definition():
    default_level: str

@dataclass(eq=False)
class RTC_Member_Definition():
    default_value: any

@dataclass(eq=False)
class RTC_Member_Data_Mirror_Definition():
    RTC_key: str
    FWC_name: str
    mirrored_key_field_names: list[str]
    mirrored_data_field_names: list[str]
    default_data_path_in_scene: Optional[str]

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
# FEATURE WRAPPER ABSTRACT PARENT CLASSES
# ==============================================================================================================================

# Addon Features (logging, event-listeners, hooks...) are often bundled into a single wrapper class that inherits from these Abstract classes
# These special classes are labeled 'FWC' (Feature-Wrapper Classes)
#
# FWCs always inherit from 'Abstract_Feature_Wrapper'. They can optionally inherit the other 2 abstact classes
# Each abstract class contains class (not instance) functions which must be present in the child.
# Some FWC function implenentations can have flexible arg/return values. Others are totally fixed. The func docstrings will reveal which
#
# Features are formalized using specific classes, & stored in specific RTC registries, to allow background logic to keep data up-to-date & improve developer experience
# The developer is free to break away from "should" named-patterns, not "Musts". 
# Note that breaking these patterns will likely prevent BL<-->RTC data-sync & other convenience tools from working for a feature

class Abstract_Feature_Wrapper(ABC):
    # Inhertited by all FWCs. 
    # Each FWC's Init/Destroy functions are automatically called during startup/shutdown events by Wrapper_Control_Plane.

    @classmethod
    @abstractmethod
    def init_pre_bpy(cls) -> bool: 
        # Is automatically called during register_block_components for all registered features
        # Must have no extra arguments
        # Must return True if init is successful
        raise NotImplementedError("Please Implement this method")
        pass
    
    @classmethod
    @abstractmethod
    def init_post_bpy(cls, **kwargs):
        # Should be called from post-init hook function in each block
        raise NotImplementedError("Please Implement this method")
        pass
    
    @classmethod
    @abstractmethod
    def destroy_wrapper(cls):
        # Is automatically called during unregister_block_components for all registered features
        # Must have no extra arguments
        raise NotImplementedError("Please Implement this method")
        pass


class Abstract_BL_RTC_List_Syncronizer(ABC):
    # These 2 functions are only required if an FWC has at least 1 data-mirror instance with a non-default sync.
    
    @classmethod
    @abstractmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        # Used by Wrapper_Control_Plane on undo/redo/load, and by certain property update callbacks
        # Rebuild an RTC list from the child propertygroup of a parent propertygroup/datablock. Blender is the source of truth
        # Args must match exactly
        # Returns are ignored
        pass

    @classmethod
    @abstractmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events): 
        # Used when RTC data need to be persisted into Blender
        # RTC data overwries scene/obj/datablock properties. Data is reused/modified instead of recreated, when possible
        # Args must match exactly
        # Returns are ignored
        pass


class Abstract_Datawrapper_Instance_Manager(ABC):
    # CRUD-style instance management funcs. Inhertited only by wrappers that hold 0-to-many instances of a @dataclass
    # Examples:                 block-stable-timers, block-stable-events, block-ui-shaders, block-core feature wrappers(loggers, RTC, Hooks)...
    # Examples not used by:     block-stable-modal (Only a single modal)

    @classmethod
    @abstractmethod
    def create_instance(cls, **kwargs) -> any:
        # Can have arbitrary args
        # Should return instance
        pass
    
    @classmethod
    @abstractmethod
    def destroy_instance(cls, **kwargs):
        # Can have arbitrary args
        # Should return None
        pass

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

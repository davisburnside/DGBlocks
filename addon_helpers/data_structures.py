
from abc import ABC, abstractmethod
from dataclasses import KW_ONLY, dataclass, field
from enum import Enum, StrEnum, auto
from types import ModuleType
from typing import Callable, Optional, Type
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

class String_Comparable_Mixin(Enum):
    """Mixin: members compare equal to their .name as a string."""
    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.name)

@dataclass(eq=False)
class Hook_Source_Declaration:
    arg_types: dict[str, any] = field(default_factory = dict)


@dataclass(eq=False)
class Logger_Declaration:
    default_level: str


@dataclass(eq=False)
class RTC_Member_Declaration:
    default_value: any = field(default_factory = list)



@dataclass(eq=False)
class Block_Declaration:
    block_module: ModuleType # the block/package's main __init__.py file
    block_id: str
    block_version: tuple[int,int,int] = field(default = tuple([1,0,0]))
    block_dependencies: list[str] = field(default_factory = list)
    block_bpy_classes: list[bpy.types] = field(default_factory = list)
    block_feature_wrapper_classes: list[Callable] = field(default_factory = list)
    block_loggers: Enum = field(default_factory = list)
    block_hook_sources: Enum = field(default_factory = list)
    block_RTC_members: Enum = field(default_factory = list)
    block_data_mirrors: Enum = field(default_factory = list)
    block_uilist_configs: Enum = field(default_factory = list)

# ==============================================================================================================================
# COMMON ENUMS

class Enum_Sync_Events(StrEnum):
    ADDON_INIT = auto()
    ADDON_SHUTDOWN = auto()
    PROPERTY_UPDATE = auto()
    PROPERTY_UPDATE_UNDO = auto()
    PROPERTY_UPDATE_REDO = auto()

# ==============================================================================================================================
# FEATURE WRAPPER ABSTRACT CLASSES
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

class Abstract_Datawrapper_Instance_Manager(ABC):
    # CRUD-style instance management funcs. Inhertited only by wrappers that hold 0-to-many instances of a @dataclass

    @classmethod
    @abstractmethod
    def _create_instance(cls, event: Enum_Sync_Events, **kwargs):
        # Can have arbitrary args
        raise NotImplementedError("Child class must implement this function")

    @classmethod
    @abstractmethod
    def _remove_instance(cls, event: Enum_Sync_Events, **kwargs):
        # Can have arbitrary args
        raise NotImplementedError("Child class must implement this function")


class Abstract_BL_RTC_List_Syncronizer(ABC):
    # These 2 functions are only required if an FWC has at least 1 data-mirror instance with a non-default sync.

    @classmethod
    @abstractmethod
    def _update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events, FWC_instance, data_mirror_instance):
        # Used by Wrapper_Control_Plane on undo/redo/load, and by certain property update callbacks
        # Rebuild an RTC list from a mirrored collectionproperty. Data should be moved/reused/modified instead of recreated, when possible
        raise NotImplementedError("Child class must implement this function")

    @classmethod
    @abstractmethod
    def _update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events, FWC_instance, data_mirror_instance):
        # Used when RTC data need to be persisted into Blender
        # RTC data overwrites a mirrored collectionproperty. Data should be moved/reused/modified instead of recreated, when possible
        raise NotImplementedError("Child class must implement this function")


class Abstract_Feature_Wrapper(ABC):
    # Inhertited by all FWCs. 
    # Each FWC's Init/Destroy functions are automatically called during startup/shutdown events by Wrapper_Control_Plane.

    @classmethod
    @abstractmethod
    def _init_wrapper(cls) -> bool:
        # Is automatically called during register_block_components for all registered features
        # Must have no extra arguments
        raise NotImplementedError("Child class must implement this function")

    @classmethod
    @abstractmethod
    def _remove_wrapper(cls):
        # Is automatically called during unregister_block_components for all registered features
        # Must have no extra arguments
        raise NotImplementedError("Child class must implement this function")


class Abstract_Shared_UIList_Draw(ABC):

    @classmethod
    @abstractmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        # if shared_uilist_instance.scene_colprop_path is None:
        #     return shared_uilist_instance.scene_colprop_path
        
        # error_str = f"'shared_uilist_instance.scene_colprop_path' is None. FWC '{shared_uilist_instance.FWC_name}' must implement this function"
        raise NotImplementedError("Child class must implement this function")


# ==============================================================================================================================
# SUPPORT CLASSES FOR FWCS
# ==============================================================================================================================


@dataclass(eq=False)
class Shared_UIList_Declaration:
    col_names: list[str]
    col_widths: list[int]

    scene_parent_path: str
    scene_colprop_path: str
    scene_colprop_path_UIList_selection_idx_path: str

    callback_draw_row: Callable
    callback_draw_details_section: Callable

    RTC_key: Optional[str] = field(default = None)

    # Optional: called in filter_items to hide/show rows.
    # Signature: callback_filter_items(context, uilist_config_instance, BL_colprop) -> list[bool]
    # Return a list of bool (True = show, False = hide), one entry per BL collection item.
    # If None, all items are shown (default Blender behaviour).
    callback_filter_items: Optional[Callable] = field(default = None)

@dataclass
class Shared_UIList_Instance(Shared_UIList_Declaration):
    _: KW_ONLY  # everything after this is keyword-only, solving the default ordering problem

@dataclass(eq=False)
class RTC_Member_Data_Mirror_Declaration:

    RTC_key: str # Must be unique among all data mirrors
    FWC_name: str # Uniqueness not required
    mirrored_key_field_names: list[str] # determines unique, canonical records. Field values must be str, int, tuple...
    mirrored_data_field_names: list[str] # fields synced between BL & RTC records when key_fields match

    scene_colprop_path: Optional[str] = field(default = None) # If None, the FWC must implement '_update_BL_with_mirrored_RTC_data' or '_update_RTC_with_mirrored_BL_data'

@dataclass 
class RTC_FWC_Data_Mirror_Instance(RTC_Member_Data_Mirror_Declaration):
    _: KW_ONLY  # everything after this is keyword-only, solving the default ordering problem
    uid: tuple[str, str] # Built from RTC key and FWC Name

    # RTC_member_type: str # enum <"list"> / <"dict">
    RTC_member_type: str 

    # Updates for every sync attempt
    timestamp_last_BL_data_refresh: int = field(default = -1)
    timestamp_last_RTC_data_refresh: int = field(default = -1)

    # Validation happens a few steps after creation, once bpy is available
    error_reason: str = field(default = None)

# Unlike most Instances, FWCs have no associated declaration class. They are referenced directly during registration
@dataclass
class RTC_FWC_Instance:
    src_block_id: str
    feature_name: str
    actual_class: Abstract_Feature_Wrapper


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
import bpy # type: ignore

@dataclass
class Global_Addon_State():
    POST_REG_INIT_HAS_RUN: bool = False
    ADDON_STARTED_SUCCESSFULLY: bool = False
    SESSION_EVENTS: list = field(default_factory = list)

# ==============================================================================================================================
# COMMON ENUMS
# ==============================================================================================================================

class Enum_Log_Levels(Enum):
    DEBUG = ("DEBUG", "Debug", "Show all messages", 10)
    INFO = ("INFO", "Info", "Show info and above", 20)
    WARNING = ("WARNING", "Warning", "Show warnings and above", 30)
    ERROR = ("ERROR", "Error", "Show errors and above", 40)
    CRITICAL = ("CRITICAL", "Critical", "Show only critical errors", 50)
    
    @property
    def desc(self):
        return self.value[2]@property
    
    @property
    def weight(self):
        return self.value[3]@property
    
    @classmethod# Used by scene_loggers.level.items
    def tuple_enum_items(cls):
        """Helper to return tuples for Blender: (identifier, name, description)"""
        # We only take the first 3 elements for the UI
        return [item.value[:3] for item in cls]

class Enum_Sync_Events(StrEnum):
    ADDON_INIT = auto()
    ADDON_SHUTDOWN = auto()
    PROPERTY_UPDATE = auto()
    PROPERTY_UPDATE_UNDO = auto()
    PROPERTY_UPDATE_REDO = auto()
    

class Enum_Sync_Actions(StrEnum):
    CREATE = auto()
    REMOVE = auto()
    EDIT = auto()
    MOVE = auto()

# ==============================================================================================================================
# FEATURE WRAPPER PARENT CLASSES
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
    # Each FWC's Init/Destroy functions are automatically called during startup/shutdown events by Wrapper_Block_Management.

    @classmethod
    @abstractmethod
    def init_pre_bpy(cls) -> bool: 
        # Is automatically called during register_block_components for all registered features
        # Must have no extra arguments
        # Must return True if init is successful
        pass
    
    @classmethod
    @abstractmethod
    def init_post_bpy(cls, **kwargs):
        # Should be called from post-init hook function in each block
        pass
    
    @classmethod
    @abstractmethod
    def destroy_wrapper(cls):
        # Is automatically called during unregister_block_components for all registered features
        # Must have no extra arguments
        pass

class Abstract_BL_and_RTC_Data_Syncronizer(ABC):
    # Inhertited by all FWCs that sync data between the RTC and Blender (Scene, Preferences, WindowManager, Object... almost any bpy.* object )
    # Children of this class will automatically update RTC data with Blender's source-of-truth upon UNDO/REDO events

    @classmethod
    @abstractmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        # Used by Wrapper_Block_Management on undo/redo/load, and by certain property update callbacks
        # Rebuild RTC from scene/obj/datablock properties. Blender is the source of truth
        # Should use 'update_dataclasses_to_match_collectionprop' for convenience
        # Args must match exactly
        pass

    @classmethod
    @abstractmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events): 
        # Used when RTC data need to be persisted into Blender
        # RTC data overwries scene/obj/datablock properties. Data is reused/modified instead of recreated, when possible
        # Should use 'update_collectionprop_to_match_dataclasses' for convenience
        # Args must match exactly
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


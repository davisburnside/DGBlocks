
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto
from typing import Optional, Type
import bpy # type: ignore

@dataclass
class Global_Addon_State():
    POST_REG_INIT_HAS_RUN: bool = False
    ADDON_STARTED_SUCCESSFULLY: bool = False
    CURRENT_MODE: str = None
    CURRENT_SCENE_ID: tuple[str, str] = None # (name, session_uid)
    CURRENT_WORKSPACE_ID: tuple[str, str] = None # (name, session_uid)
    CURRENT_ACTIVE_OBJ: tuple[str, str] = None # (name, session_uid)

# ==============================================================================================================================
# COMMON ENUMS
# ==============================================================================================================================

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


class Core_Block_Tracked_Datablock_Types(Enum):
    # TRACKED DATABLOCK TYPES - New block primitive, like hooks & loggers
    # Hardcoded list of all possible bpy.data.* datablock types.
    # Downstream blocks call create_instance/destroy_instance to enable/disable tracking.
    # name = type identifier (matches depsgraph.id_type_updated name)
    # value[0] = type_name for depsgraph check
    # value[1] = bpy.data collection attribute name
    # value[2] = bpy.types.* class

    ACTION = ("ACTION", "actions", bpy.types.Action)
    ARMATURE = ("ARMATURE", "armatures", bpy.types.Armature)
    BRUSH = ("BRUSH", "brushes", bpy.types.Brush)
    CACHEFILE = ("CACHEFILE", "cache_files", bpy.types.CacheFile)
    CAMERA = ("CAMERA", "cameras", bpy.types.Camera)
    COLLECTION = ("COLLECTION", "collections", bpy.types.Collection)
    CURVE = ("CURVE", "curves", bpy.types.Curve)
    FONT = ("FONT", "fonts", bpy.types.VectorFont)
    GREASEPENCIL = ("GREASEPENCIL", "grease_pencils", bpy.types.GreasePencil)
    IMAGE = ("IMAGE", "images", bpy.types.Image)
    LATTICE = ("LATTICE", "lattices", bpy.types.Lattice)
    LIGHT = ("LIGHT", "lights", bpy.types.Light)
    LIGHT_PROBE = ("LIGHTPROBE", "lightprobes", bpy.types.LightProbe)
    LINESTYLE = ("LINESTYLE", "linestyles", bpy.types.FreestyleLineStyle)
    MATERIAL = ("MATERIAL", "materials", bpy.types.Material)
    MESH = ("MESH", "meshes", bpy.types.Mesh)
    METABALL = ("METABALL", "metaballs", bpy.types.MetaBall)
    MOVIECLIP = ("MOVIECLIP", "movieclips", bpy.types.MovieClip)
    NODETREE = ("NODETREE", "node_groups", bpy.types.NodeTree)
    OBJECT = ("OBJECT", "objects", bpy.types.Object)
    PAINTCURVE = ("PAINTCURVE", "paint_curves", bpy.types.PaintCurve)
    PALETTE = ("PALETTE", "palettes", bpy.types.Palette)
    PARTICLE = ("PARTICLE", "particles", bpy.types.ParticleSettings)
    POINTCLOUD = ("POINTCLOUD", "pointclouds", bpy.types.PointCloud)
    SCENE = ("SCENE", "scenes", bpy.types.Scene)
    SPEAKER = ("SPEAKER", "speakers", bpy.types.Speaker)
    TEXT = ("TEXT", "texts", bpy.types.Text)
    TEXTURE = ("TEXTURE", "textures", bpy.types.Texture)
    VOLUME = ("VOLUME", "volumes", bpy.types.Volume)
    WORLD = ("WORLD", "worlds", bpy.types.World)
    WORKSPACE = ("WORKSPACE", "workspaces", bpy.types.WorkSpace)

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
    # All functions are optional. If not implemented, Wrapper_Control_Plane handles logic
    # Inhertited by all FWCs that sync data between the RTC and Blender (Scene, Preferences, WindowManager, Object... almost any bpy.* object )
    # Children of this class will automatically update RTC data with Blender's source-of-truth upon UNDO/REDO events

    @classmethod
    @abstractmethod
    def get_owners_list() -> list[Type[bpy.props]]:
        # Optional func: if not implemented in the FWC, context.scene is used (Where BL-mirrored data commonly lives)
        # Executes once per FWC, per resync event
        # Returns are ignored
        pass

    @classmethod
    @abstractmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        # Optional func: if not implemented in the FWC, context.scene is used (Where BL-mirrored data commonly lives)
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
        # Should use 'update_collectionprop_to_match_dataclasses' for convenience
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
class RTC_FWC_Data_Mirror_List_Reference:
    
    RTC_key: str # top-level cache key
    BL_property_path: str # Relative to owner, not full path
    BL_property_owner_type: str # bpy.types.*


    should_use_default_sync_logic: bool
    sync_key_field_names: list[str] # determines unique, canonical records. Field values must be str, int, tuple...
    sync_data_field_names: list[str] # fields synced between BL & RTC records when key_fields match
    timestamp_last_BL_data_refresh: int = field(default = -1)
    timestamp_last_RTC_data_refresh: int = field(default = -1)


@dataclass
class RTC_FWC_Instance:
    src_block_id: str
    feature_name: str
    actual_class: Type[Abstract_Feature_Wrapper]
    has_BL_mirrored_data: bool
    # data_mirror_instance: Optional[Type[RTC_FWC_Data_Mirror_List_Reference]] = field(default = None)

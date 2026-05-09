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
    SCENE_MONITOR_DATA_BLOCKS_CHANGED = ("hook_scene_monitor_datablocks_changed", {"changes": dict})
    SCENE_MONITOR_SCENE_CHANGED = ("hook_scene_monitor_scene_changed", {"old_scene": str, "new_scene": str})
    SCENE_MONITOR_SCENE_OBJECTS_CHANGED = ("hook_scene_monitor_scene_objects_changed", {"changes": dict})

# name = logger ID
# value[0] = logger display name & default level
# value[1] = logger display name & default level
class Core_Block_Loggers(Enum):
    HOOKS = ("hooks", "INFO")
    BLOCK_MGMT = ("core-events", "DEBUG")
    DATA_SYNC = ("data-sync", "DEBUG")
    REGISTRATE = ("register", "DEBUG")
    POST_REGISTRATE = ("post-reg", "DEBUG")
    UI = ("ui", "WARNING")
    TRACKED_DATABLOCK_TYPES = ("tracked-db-types", "DEBUG")
    SCENE_MONITOR = ("scene-monitor", "DEBUG")

# name = RTC Member ID 
# value[0] = actual RTC dict key
# value[1] = default data for RTC key
class Core_Runtime_Cache_Members(Enum):
    ADDON_METADATA = ("ADDON_METADATA", Global_Addon_State)
    REGISTRY_ALL_BLOCKS = ("REGISTRY_ALL_BLOCKS", [])
    REGISTRY_ALL_FWCS = ("REGISTRY_ALL_FWCS", [])
    REGISTRY_ALL_FWC_DATA_MIRRORS = ("REGISTRY_ALL_FWC_DATA_MIRRORS", [])
    REGISTRY_ALL_HOOK_SOURCES = ("REGISTRY_ALL_HOOK_SOURCES", [])
    REGISTRY_ALL_HOOK_SUBSCRIBERS = ("REGISTRY_ALL_HOOK_SUBSCRIBERS", [])
    REGISTRY_ALL_LOGGERS = ("REGISTRY_ALL_LOGGERS", [])
    REGISTRY_ALL_TRACKED_DATABLOCK_TYPES = ("REGISTRY_ALL_TRACKED_DATABLOCK_TYPES", [])
    SCENE_MONITOR_STATE = ("SCENE_MONITOR_STATE", {})
    META_REGISTRIES_BEING_SYNCED = ("META_REGISTRIES_BEING_SYNCED", [])
    UI_ALERTS = ("UI_ALERTS", {})
    UI_WORDWRAP_WIDTHS = ("UI_WORDWRAP_WIDTHS", {})

# ==============================================================================================================================
# TRACKED DATABLOCK TYPES - New block primitive, like hooks & loggers
# Hardcoded list of all possible bpy.data.* datablock types.
# Downstream blocks call create_instance/destroy_instance to enable/disable tracking.
# ==============================================================================================================================

# name = type identifier (matches depsgraph.id_type_updated name)
# value[0] = type_name for depsgraph check
# value[1] = bpy.data collection attribute name
# value[2] = bpy.types.* class
class Core_Block_Tracked_Datablock_Types(Enum):
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
# OTHER
# ==============================================================================================================================

log_timestring_format = "%Y-%m-%d %H:%M:%S"
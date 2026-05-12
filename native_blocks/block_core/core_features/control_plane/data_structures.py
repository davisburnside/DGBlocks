# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from dataclasses import dataclass, field
from types import ModuleType
from typing import Type
from enum import Enum
import bpy  # type: ignore
from bpy.app.handlers import persistent  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Events

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers import get_logger
from .....addon_helpers.generic_helpers import is_bpy_ready

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS

# ==============================================================================================================================
# MSGBUS — Scene-change listener owners & subscriptions
# ==============================================================================================================================

# Blender's msgbus needs some (any) python object to hold a reference to
_msgbus_owner_for_active_scene = object()
_msgbus_owner_for_active_window_scene_viewlayer = object()
_msgbus_owner_for_scene_names = object()
_msgbus_T1 = object()

@persistent
def _msgbus_window_scene_changed(*args):
    """Called by bpy.msgbus when the active scene changes in any window."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Window Scene changed — now in '{bpy.context.scene.name_full}'")

@persistent
def _msgbus_window_scene_viewlayer_changed(*args):
    """Called by bpy.msgbus when the active view layer changes."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Window Scene Viewlayer changed — now in '{bpy.context.view_layer.name}'")

@persistent
def _msgbus_scene_name_changed(*args):
    """Called by bpy.msgbus when the active scene name changes."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Scene Name changed — now in '{bpy.context.scene.name_full}'")

def _msgbus_test1(*args):
    print(f"TEST1   '")

# list of tuples to define msgbus subscriptions
# tuple[0] = msgbus sub "owner" object
# tuple[1] = msgbus key: the data being listened to
# tuple[2] = callback function when the data changes
msgbus_subs = [
    # (_msgbus_owner_for_active_scene, (bpy.types.Window, "scene"), _msgbus_window_scene_changed),
    # (_msgbus_owner_for_active_window_scene_viewlayer, (bpy.types.Window, "view_layer"), _msgbus_window_scene_viewlayer_changed),
    # (_msgbus_owner_for_scene_names, (bpy.types.Scene, "name"), _msgbus_scene_name_changed),
    # (_msgbus_T1, (bpy.types.BlendData, "scenes"), _msgbus_test1)
]

# ==============================================================================================================================
# BLENDER DATA (PropertyGroup + update callback)
# ==============================================================================================================================

def _callback_update_block_enabled(self, context):

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key_blocks) or not is_bpy_ready():
        return

    try:
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        # Lazy import to avoid circular dependency: data_structures <- feature_wrapper <- data_structures
        from .feature_wrapper import Wrapper_Block_Management
        Wrapper_Block_Management.evaluate_and_update_block_statuses(event=Enum_Sync_Events.PROPERTY_UPDATE)

    except Exception:
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.error(f"Exception when updating 'enabled' status of blocks", exc_info=True)

    finally:
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, False)


class DGBLOCKS_PG_Debug_Block_Reference(bpy.types.PropertyGroup):
    # RTC Mirror = 'REGISTRY_ALL_BLOCKS'
    # Used to toggle Blocks On/Off in Debug mode
    # Contains Block status, package location

    block_id: bpy.props.StringProperty(name="Block ID")  # type: ignore
    should_block_be_enabled: bpy.props.BoolProperty(default=True, update=_callback_update_block_enabled)  # type: ignore
    is_block_enabled: bpy.props.BoolProperty(default=True, update=_callback_update_block_enabled)  # type: ignore
    is_block_valid: bpy.props.BoolProperty()  # type: ignore
    is_block_dependencies_valid_and_enabled: bpy.props.BoolProperty()  # type: ignore
    block_disabled_reason: bpy.props.StringProperty()  # type: ignore

# ==============================================================================================================================
# RTC DATA
# ==============================================================================================================================

# Used during RTC <-> BL data sync
rtc_sync_key_fields = ["block_id"]
rtc_sync_data_fields = [
    "should_block_be_enabled",
    "is_block_enabled",
    "is_block_valid",
    "is_block_dependencies_valid_and_enabled",
    "block_disabled_reason",
]


@dataclass
class RTC_Block_Instance:
    # Record — instance state only, no manager logic

    # Mirrored fields of DGBLOCKS_PG_Debug_Block_Reference
    block_id: str
    should_block_be_enabled: bool
    is_block_enabled: bool
    is_block_valid: bool
    is_block_dependencies_valid_and_enabled: bool
    block_disabled_reason: str

    # Not present in mirror
    block_module: ModuleType
    block_dependencies: list[str]
    block_bpy_types_classes: list[bpy.types]
    block_feature_wrapper_classes: list[Abstract_Feature_Wrapper]
    block_hook_source_names: list[str]
    block_logger_names: list[str]
    block_RTC_member_names: list[str]
    tracked_datablock_types: list[str] = field(default_factory=list)  # type_names from Core_Block_Tracked_Datablock_Types

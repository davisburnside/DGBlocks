from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import ModuleType
from typing import Optional
import bpy

from .....addon_helpers.data_structures import Enum_Sync_Events, RTC_FWC_Instance

def _callback_block_debug_mode_changed(self, context):
    """
    Fired when the user toggles the Debug Mode checkbox in the All Blocks UIList.
    Pushes the new value into RTC through the standard BL→RTC data mirror sync.
    """

    # Imported here (not at module scope) to avoid an import cycle:
    # constants -> ui -> ... -> control_plane.data_structures
    from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
    from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
    from ..loggers.feature_wrapper import get_logger

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS):
        return

    logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
    Wrapper_Runtime_Cache.resync_single_data_mirror(
        event = Enum_Sync_Events.PROPERTY_UPDATE,
        BL_is_truth_source = True,
        cache_key = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS,
        logger = logger,
    )



class DGBLOCKS_PG_Block_Record(bpy.types.PropertyGroup):
    block_id: bpy.props.StringProperty(name="Block ID") # type: ignore
    is_valid: bpy.props.BoolProperty(name="Is Valid") # type: ignore
    error_message: bpy.props.StringProperty(name="Error Message") # type: ignore
    is_block_enabled: bpy.props.BoolProperty(name="Is Enabled") # type: ignore
    debug_mode_enabled: bpy.props.BoolProperty(name="Debug Mode", default=False, update=_callback_block_debug_mode_changed) # type: ignore
    block_index: bpy.props.IntProperty(name="Block Index", default=-1) # type: ignore

@dataclass
class RTC_Block_Instance:
    # Record — instance state only, no manager logic

    block_id: str
    block_version: tuple[int,int,int]
    block_module: ModuleType
    block_package_name: str
    block_dependencies: list[str]
    block_bpy_types_classes: list[bpy.types] = field(default_factory=list)
    block_FWC_instances: list[RTC_FWC_Instance] = field(default_factory=list)
    block_RTC_member_names: list[str] = field(default_factory=list)
    is_valid: bool = field(default = True)
    # Mirrored into a StringProperty, so this must never be None
    error_message: str = field(default = "")

    is_block_enabled: bool = field(default = True)
    debug_mode_enabled: bool = field(default = False)
    block_index: int = field(default = -1)

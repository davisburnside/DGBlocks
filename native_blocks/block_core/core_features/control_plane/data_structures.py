
from dataclasses import dataclass, field
from types import ModuleType
import bpy  # type: ignore
from bpy.app.handlers import persistent  # type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Events

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger
from .....addon_helpers.generic_tools import is_bpy_ready

# Aliases
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS

# ==============================================================================================================================
# BLENDER DATA 

def _callback_update_block_enabled(self, context):

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key_blocks) or not is_bpy_ready():
        return

    try:
        instance_FWC_Control_Plane = Wrapper_Runtime_Cache.get_Control_Plane_FWC()
        instance_FWC_Control_Plane.actual_class.update_all_FWC_RTC_caches_to_match_BL_data(event=Enum_Sync_Events.PROPERTY_UPDATE)

    except Exception:
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.error(f"Exception when updating 'enabled' status of blocks", exc_info=True)

    finally:
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, False)


class DGBLOCKS_PG_Debug_Block_Reference(bpy.types.PropertyGroup):
    block_id: bpy.props.StringProperty(name="Block ID")  # type: ignore
    should_block_be_enabled: bpy.props.BoolProperty(default=True, update=_callback_update_block_enabled)  # type: ignore
    is_block_enabled: bpy.props.BoolProperty(default=True, update=_callback_update_block_enabled)  # type: ignore
    is_block_valid: bpy.props.BoolProperty()  # type: ignore
    is_block_dependencies_valid_and_enabled: bpy.props.BoolProperty()  # type: ignore
    block_disabled_reason: bpy.props.StringProperty()  # type: ignore

# ==============================================================================================================================
# RTC DATA

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

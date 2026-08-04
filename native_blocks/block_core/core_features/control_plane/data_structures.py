from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import ModuleType
from typing import Optional
import bpy

from .....addon_helpers.data_structures import RTC_FWC_Instance

def _callback_block_debug_mode_changed(self, context):
    """
    Fired when the user toggles the Debug Mode checkbox in the All Blocks UIList.
    Immediately sync the new value to the matching RTC_Block_Instance.
    """
    try:
        from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache as _WRTC
        cached_blocks = _WRTC.get_cache("REGISTRY_ALL_BLOCKS")
        for block in cached_blocks:
            if block.block_id == self.block_id:
                block.debug_mode_enabled = self.debug_mode_enabled
                _WRTC.set_cache("REGISTRY_ALL_BLOCKS", cached_blocks)
                break
    except Exception:
        pass


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
    error_message: Optional[str] = field(default = None)
    is_block_enabled: bool = field(default = True)
    debug_mode_enabled: bool = field(default = False)
    block_index: int = field(default = -1)

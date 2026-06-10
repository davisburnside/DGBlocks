from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import ModuleType
from typing import Optional
import bpy

from .....addon_helpers.data_structures import RTC_FWC_Instance

class DGBLOCKS_PG_Block_Record(bpy.types.PropertyGroup):
    block_id: bpy.props.StringProperty(name="Block ID") # type: ignore
    is_valid: bpy.props.BoolProperty(name="Is Valid") # type: ignore
    error_message: bpy.props.StringProperty(name="Error Message") # type: ignore
    is_block_enabled: bpy.props.BoolProperty(name="Is Enabled") # type: ignore

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

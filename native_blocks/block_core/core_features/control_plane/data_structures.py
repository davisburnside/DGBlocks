from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import ModuleType
from typing import Optional
import bpy

from .....addon_helpers.data_structures import RTC_FWC_Instance

@dataclass
class RTC_Block_Instance:
    # Record — instance state only, no manager logic

    block_id: str
    block_module: ModuleType
    block_package_name: str
    block_dependencies: list[str]
    block_bpy_types_classes: list[bpy.types] = field(default_factory=list)
    block_FWC_instances: list[RTC_FWC_Instance] = field(default_factory=list)
    block_RTC_member_names: list[str] = field(default_factory=list)
    is_valid: bool = field(default = True)
    error_message: Optional[str] = field(default = None)

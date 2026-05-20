import os

from addon_helpers.generic_tools import get_self_block_module
from native_blocks.block_core.core_helpers.ops import DGBLOCKS_OT_Copy_To_Clipboard, DGBLOCKS_OT_Debug_Clear_And_Restore_Caches, DGBLOCKS_OT_Force_Reload_Refresh_UI, DGBLOCKS_OT_Force_Reload_Scripts, DGBLOCKS_OT_Open_Help_Page
from native_blocks.block_core.core_helpers.props import DGBLOCKS_PG_Core_Props
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events

# --------------------------------------------------------------
# Core block imports
# --------------------------------------------------------------
from .core_helpers.constants import Core_Block_Hook_Sources, Core_Block_Loggers, Core_Data_Mirrors, Core_Runtime_Cache_Members, _BLOCK_ID as core_block_id
from .core_features.loggers.feature_wrapper import Wrapper_Loggers
from .core_features.loggers.data_structures import DGBLOCKS_PG_Logger_Instance
from .core_features.loggers.ui import DGBLOCKS_UL_Loggers
from .core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
from .core_features.control_plane.ui import DGBLOCKS_UL_Blocks
from .core_features.control_plane.data_structures import DGBLOCKS_PG_Debug_Block_Reference
from .core_features.hooks.data_structures import DGBLOCKS_PG_Hook_Reference
from .core_features.hooks.feature_wrapper import Wrapper_Hooks
from .core_features.hooks.ui import  DGBLOCKS_UL_Hooks
from .core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .core_helpers.ui import DGBLOCKS_PT_Core_Block_Panel

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_PG_Debug_Block_Reference,
    DGBLOCKS_PG_Logger_Instance,
    DGBLOCKS_PG_Hook_Reference,
    DGBLOCKS_PG_Core_Props,
    DGBLOCKS_OT_Open_Help_Page,
    DGBLOCKS_OT_Copy_To_Clipboard,
    DGBLOCKS_OT_Force_Reload_Refresh_UI,
    DGBLOCKS_OT_Force_Reload_Scripts,
    DGBLOCKS_OT_Debug_Clear_And_Restore_Caches,
    DGBLOCKS_PT_Core_Block_Panel,
    DGBLOCKS_UL_Blocks,
    DGBLOCKS_UL_Hooks,
    DGBLOCKS_UL_Loggers,
]

# All core-block feature wrapper
_feature_wrapper_classes_to_register = [
    Wrapper_Control_Plane,
    Wrapper_Runtime_Cache,
    Wrapper_Loggers,
    Wrapper_Hooks,
]

# ==============================================================================================================================
# REQUIRED 
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module = __file__,
    block_id = core_block_id,
    block_dependencies = [],
    block_bpy_classes = _block_classes_to_register,
    block_feature_wrapper_classes = _feature_wrapper_classes_to_register,
    block_loggers = Core_Block_Loggers,
    block_hook_sources = Core_Block_Hook_Sources,
    block_RTC_members = Core_Runtime_Cache_Members,
    block_data_mirrors = Core_Data_Mirrors,
)

def register_block_props(event: Enum_Sync_Events):
    bpy.types.Scene.dgblocks_core_props = bpy.props.PointerProperty(type = DGBLOCKS_PG_Core_Props)

def unregister_block_props(event: Enum_Sync_Events):
    if hasattr(bpy.types.Scene, "dgblocks_core_props"):
        del bpy.types.Scene.dgblocks_core_props

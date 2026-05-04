
import time
import bpy # type: ignore
from bpy.props import BoolProperty, PointerProperty # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import should_draw_delevoper_panel, get_self_block_module
from ...my_addon_config import Documentation_URLs, should_show_developer_ui_panels, default_disabled_icon, addon_name, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import _block_core
from .._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_stable_modal import BL_Modal_Instance, MODAL_OT_Delete, MODAL_UL_StackList, VIEW3D_PT_ModalStack, MODAL_OT_Add, Wrapper_Modals_Manager, DGBLOCKS_OT_StableModal
from .block_constants import Block_Logger_Definitions,Block_RTC_Members, Block_Hooks

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-stable-modal"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core"
]

# =============================================================================
# DATABLOCKS - Attached to Scene
# Stores persistent modal configuration
# =============================================================================

class DGBLOCKS_PG_Modal_Props(bpy.types.PropertyGroup):
    """Modal configuration stored in scene"""
    
    managed_modals: bpy.props.CollectionProperty(type=BL_Modal_Instance) # type: ignore
    managed_modals_selected_idx: bpy.props.IntProperty()  # type: ignore

#================================================================
# REGISTRATION EVENTS - Should only be called from the addon's main __init__.py
#================================================================

_block_classes_to_register = [
    BL_Modal_Instance,
    DGBLOCKS_PG_Modal_Props,
    DGBLOCKS_OT_StableModal,
    MODAL_OT_Delete,
    MODAL_OT_Add,
    MODAL_UL_StackList,
    VIEW3D_PT_ModalStack,
]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_feature_wrapper_classes = [Wrapper_Modals_Manager], 
        block_hook_source_enums = Block_Hooks,
        block_RTC_member_enums = Block_RTC_Members, 
        block_logger_enums = Block_Logger_Definitions 
    )

    # Create Scene Property to hold modal configuration
    bpy.types.Scene.dgblocks_modal_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Modal_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")
    
    
    # Remove block components from RTC
    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_modal_props"):
        del bpy.types.Scene.dgblocks_modal_props

    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")

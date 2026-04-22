

import bpy # type: ignore
from typing import Optional

#=================================================================================
# BLOCK DATA - A unique ID & list of Dependencies is required for every Block
#=================================================================================

import blocks_ununsed.block_event_listeners as block_event_listeners
_BLOCK_ID = "block-ui-display-modal"
_BLOCK_DEPENDENCIES = [
    "block-core", 
    block_event_listeners._BLOCK_ID,
]

#=================================================================================
# IMPORTS
#=================================================================================
from ...my_addon_config import (
        addon_name, 
        addon_title,
        Documentation_URLs)
from ...blocks_natively_included._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from ...blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from ...blocks_natively_included._block_core.core_features.feature_logs import get_logger

from .rendered_ui_modal import DGBLOCKS_DISPLAY_MODAL_PROPS, DGBLOCKS_OT_DisplayModal, DGBLOCKS_PT_Modal_Display

#=================================================================================
# CALLBACK HOOK FUNCTIONS 
#=================================================================================

def hook_post_register_init(context):
    
    logger = get_logger(my_logger_definitions.load_listener.name)
    display_modal_props = context.scene.dgblocks_display_modal_props
    
    # Start or kill the modal on addon startup
    if display_modal_props.should_be_activated_after_startup and not display_modal_props.myaddon_display_active:
        logger.info("Activating UI Display Modal")
        display_modal_props.myaddon_display_active = True
    elif not display_modal_props.should_be_activated_after_startup and display_modal_props.myaddon_display_active:
        logger.info("Deactivating UI Display Modal")
        display_modal_props.myaddon_display_active = False
        
    return True

#=================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#=================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [    
    DGBLOCKS_DISPLAY_MODAL_PROPS,
    DGBLOCKS_PT_Modal_Display,
    DGBLOCKS_OT_DisplayModal]

def register_block():
    
    logger = get_logger(my_logger_definitions.class_registrations.name)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(_block_classes_to_register)
    
    bpy.types.Scene.dgblocks_display_modal_props = bpy.props.PointerProperty(type=DGBLOCKS_DISPLAY_MODAL_PROPS)
    
    # Initialize empty render & animations structs
    Wrapper_Runtime_Cache.set_instance("render", {})
    Wrapper_Runtime_Cache.set_instance("animations", {})
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(my_logger_definitions.class_registrations.name)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    # Clear runtime cache data
    Wrapper_Runtime_Cache.set_instance("render", {})
    Wrapper_Runtime_Cache.set_instance("animations", {})
    
    # Force shutdown of operator
    # DGBLOCKS_OT_DisplayModal.kill_display_modal(bpy.context)
    
    # Remove property and classes
    if hasattr(bpy.types.Scene, "dgblocks_display_modal_props"):
        del bpy.types.Scene.dgblocks_display_modal_props
    
    unregister_block_components(_block_classes_to_register)
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")
    
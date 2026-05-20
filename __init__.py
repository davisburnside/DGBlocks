
bl_info = {
    "name" : "dgblock_basic_template",
    "author" : "DGBlocks", 
    "description" : "A standardized collection of addon features",
    "blender" : (5, 0, 0),
    "version" : (1, 0, 0),
    "location" : "",
    "warning" : "",
    "doc_url": "TODO", 
    "tracker_url": "", 
    "category" : "3D View" 
}

import sys
import importlib
import bpy
from native_blocks.block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

from .addon_helpers.generic_tools import clear_console, validate_block_list_before_registration
clear_console()

# ==============================================================================================================================
# RECURSIVE MODULE RELOAD (FOR DEVELOPERS)
# ==============================================================================================================================
# Allows a single bpy.ops.script.reload() to reload all python files in deeply nested folders.
# Without this step, some modules need 2 reload() actions to refresh

# Get all modules in addon
all_sys_modules = sys.modules.items()
modules_to_reload = [
    (name, module) for name, module in all_sys_modules
    if name.startswith(f"{__name__}.") or name == __name__]

# Sort by depth (most dots = deepest), reload leaves first
modules_to_reload.sort(key=lambda x: x[0].count('.'), reverse=True) 

# Refresh modules
for name, module in modules_to_reload: 
    importlib.reload(module)

# ==============================================================================================================================
# ADDON-LEVEL & CORE-BLOCK IMPORTS
# ==============================================================================================================================

from .addon_config.preferences import DGBLOCKS_UP_Core_Preferences
from .addon_config.active_blocks import _BLOCK_PACKAGES
from .addon_config.static_settings import addon_name

from .native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .native_blocks.block_core.core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
from .native_blocks.block_core.core_features.loggers.feature_wrapper import Wrapper_Loggers, get_logger
from .native_blocks.block_core.core_helpers.constants import Core_Block_Loggers

# ==============================================================================================================================
# MAIN REGISTRATION
# ==============================================================================================================================
# This main __init__ file should own/register no bpy.types.* classes
# Instead, all classes/properties should be registered & managed by the block that owns them

def register():

    # Register Addon props. This is the only addon-level class
    bpy.utils.register_class(DGBLOCKS_UP_Core_Preferences)

    _RTC_dummy = Wrapper_Runtime_Cache # for debugging
    
    # Core feature-wrapper classes are bootstrapped first, before their owner block starts registration.
    # The first FWC created is Runtime Cache (RTC), to hold the next created objects.
    # Next is the Loggers FWC, to write console output
    # Finally is the Control-Plane FWC, which adds the core app.handler and msgbus listeners
    core_block_FWCs = [Wrapper_Runtime_Cache, Wrapper_Loggers, Wrapper_Control_Plane, Wrapper_Hooks]
    for actual_feature_wrapper_class in core_block_FWCs:
        actual_feature_wrapper_class.init_wrapper()
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main pre-bpy registration for Addon '{addon_name}'")

    # Identify valid blocks to register. Invalid blocks are skipped, with an error logged in the console
    # Causes of invalid blocks: TODO webpage link
    valid_block_packages, invalid_blocks_errors = validate_block_list_before_registration(_BLOCK_PACKAGES)
    for block_id, errors_list in invalid_blocks_errors.items():
        logger.error(f"Errors registering '{block_id}': {str(errors_list)}")

    # Call registration logic of each block, in order. Core-block should always be first in this list
    # Most init tasks for core-block features are already completed by this point, but 
    # Other features, from other blocks, may have their own init tasks. These are automatically triggered inside 'register_block'
    # To see the full list of actions triggered by the registration loop, set REGISTRATE, POST_REGISTRATE, BLOCK_MGMT Loggers to 'DEBUG'
    for block_package in valid_block_packages:
        Wrapper_Control_Plane.create_instance(block_package._BLOCK_DECLARATION)
    
    logger.log_with_linebreak(f"Finished main pre-bpy registration for Addon '{addon_name}'")

def unregister():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main unregistration for Addon '{addon_name}'")

    # Unregister other DGBlock packages
    # This should be done in the opposite order as register()
    registered_blocks = Wrapper_Runtime_Cache.get_cache()
    for block in reversed(_BLOCK_PACKAGES):
        try:
            block.unregister_block(event)
        except:
            logger.error(f"Exception when unregistering block '{block._BLOCK_ID}': ", exc_info = True)
    
    try:
        bpy.utils.unregister_class(DGBLOCKS_UP_Core_Preferences)
        logger.log_with_linebreak(f"Finished main unregistration for Addon '{addon_name}'")
        print("\n")
    except:
        pass

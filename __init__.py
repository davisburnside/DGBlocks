
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
from .addon_helpers.generic_helpers import clear_console
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
from .addon_helpers.data_structures import Enum_Sync_Events
from .my_activated_blocks import _ordered_blocks_list
from .my_addon_config import addon_name

from .blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .blocks_natively_included._block_core.core_features.feature_logs import Wrapper_Loggers, get_logger
from .blocks_natively_included._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .blocks_natively_included._block_core.core_helpers.constants import Core_Block_Loggers

# ==============================================================================================================================
# MAIN REGISTRATION
# ==============================================================================================================================
# This main __init__ file should own/register no bpy.types.* classes
# Instead, all classes/properties should be registered & managed by the block that owns them

def register():

    event = Enum_Sync_Events.ADDON_INIT
    
    # Two feature-wrapper classes (runtime-cache & loggers) are bootstrapped first, before their owner (block-core) starts registration.
    # Loggers are used immediately after this step, and loggers are stored inside the Runtime Cache
    Wrapper_Runtime_Cache.init_pre_bpy(event)
    Wrapper_Loggers.init_pre_bpy(event)
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main pre-bpy registration for Addon '{addon_name}'")

    # Block Managmenet feature-wrapper is created next, and is used immediately after (Triggers init tasks on other core-block features)
    Wrapper_Block_Management.init_pre_bpy(event)

    # Identify valid blocks to register. Invalid blocks are skipped, with an error logged in the console
    # Causes of invalid blocks: TODO webpage link
    valid_block_packages = Wrapper_Block_Management.validate_block_list_before_registration(_ordered_blocks_list)

    # Call registration logic of each block, in order. Core-block should always be first in this list
    # Most init tasks for core-block features are already completed by this point, but 
    # Other features, from other blocks, may have their own init tasks. These are automatically triggered inside 'register_block'
    # To see the full list of actions triggered by the registration loop, set REGISTRATE, POST_REGISTRATE, BLOCK_MGMT Loggers to 'DEBUG'
    for block in valid_block_packages:
        block.register_block(event)
    
    logger.log_with_linebreak(f"Finished main pre-bpy registration for Addon '{addon_name}'")

def unregister():

    event = Enum_Sync_Events.ADDON_SHUTDOWN
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    try: 
        logger.log_with_linebreak(f"Starting main unregistration for Addon '{addon_name}'")
    except:
        pass

    # Unregister other DGBlock packages
    # This should be done in the opposite order as register()
    for block in reversed(_ordered_blocks_list):
        try:
            block.unregister_block(event)
        except:
            logger.error(f"Exception when unregistering block '{block._BLOCK_ID}': ", exc_info = True)

    # Block-manager does cleanup tasks for itself & all other core-block features
    Wrapper_Block_Management.destroy_wrapper(event)
    
    try:
        logger.log_with_linebreak(f"Finished main unregistration for Addon '{addon_name}'")
        print("\n")
    except:
        pass

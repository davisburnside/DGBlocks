
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
from .addon_config.preferences import DGBLOCKS_UP_Core_Preferences
from .addon_config.active_blocks import _BLOCK_PACKAGES
from .addon_config.static_settings import addon_name

from .native_blocks.block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from .native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .native_blocks.block_core.core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
from .native_blocks.block_core.core_features.loggers.feature_wrapper import Wrapper_Loggers, get_logger
from .native_blocks.block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members

# ==============================================================================================================================
# MAIN REGISTRATION
# ==============================================================================================================================
# This main __init__ file should own/register no bpy.types.* classes
# Instead, all classes/properties should be registered & managed by the block that owns them
# clear_console()
def register():


    # Register Addon props. This is the only addon-level class
    bpy.utils.register_class(DGBLOCKS_UP_Core_Preferences)

    _RTC_dummy = Wrapper_Runtime_Cache # for debugging
    
    # Core feature-wrapper classes are bootstrapped first, before their owner block starts registration.
    
    core_block_FWCs = [Wrapper_Runtime_Cache, Wrapper_Loggers, Wrapper_Control_Plane, Wrapper_Hooks]
    for actual_feature_wrapper_class in core_block_FWCs:
        actual_feature_wrapper_class.init_wrapper()
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main pre-bpy registration for Addon '{addon_name}'")

    # Call registration logic of each block, in order. Core-block should always be first in this list
    # Most init tasks for core-block features are already completed by this point, but 
    # Other features, from other blocks, may have their own init tasks. These are automatically triggered inside 'register_block'
    # To see the full list of actions triggered by the registration loop, set REGISTRATE, POST_REGISTRATE, BLOCK_MGMT Loggers to 'DEBUG'
    event = Enum_Sync_Events.ADDON_INIT
    for block_module in _BLOCK_PACKAGES:
        Wrapper_Control_Plane.create_instance(event, block_module)

    logger.log_with_linebreak(f"Finished main pre-bpy registration for Addon '{addon_name}'")

def unregister():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main unregistration for Addon '{addon_name}'")

    # Unregister other DGBlock packages
    # This should be done in the opposite order as register()
    event = Enum_Sync_Events.ADDON_SHUTDOWN
    cached_blocks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)
    for block_instance in reversed(cached_blocks):
        try:
            Wrapper_Control_Plane.destroy_instance(event, block_instance)
        except:
            logger.error(f"Exception when unregistering block '{block_instance.block_id}': ", exc_info = True)
    
    try:
        bpy.utils.unregister_class(DGBLOCKS_UP_Core_Preferences)
        logger.log_with_linebreak(f"Finished main unregistration for Addon '{addon_name}'")
        print("\n")
    except:
        pass

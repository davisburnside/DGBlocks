# DGBLocks Baseline
# Copyright 2026, Davis Burnside
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You may have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
 
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

from typing import Optional
import sys
import logging
import importlib
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .addon_helper_funcs import clear_console
from .my_addon_native_blocks import _ordered_blocks_list
from .my_addon_config import addon_name
blender_version = '.'.join(map(str, bpy.app.version[:2]))

clear_console()

#================================================================
# RECURSIVE MODULE RELOAD
# Allows a single bpy.ops.script.reload() to reload all python files in deeply nested folders
#================================================================

# Get all modules in addon
all_sys_modules = sys.modules.items()
modules_to_reload = [
    (name, module) for name, module in all_sys_modules
    if name.startswith(f"{__name__}.") or name == __name__]

# Sort by depth (most dots = deepest), reload leaves first
modules_to_reload.sort(key=lambda x: x[0].count('.'), reverse=True) 

# Refresh modules
for name, module in modules_to_reload:
    # if logger_registration is not None:
    #     logger_registration.debug(f"Reloading {addon_name} | {module}")        
    importlib.reload(module)

#================================================================
# CORE-BLOCK IMPORTS
#================================================================

from .blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .blocks_natively_included._block_core.core_features.feature_logs import Wrapper_Loggers, get_logger
from .blocks_natively_included._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from .blocks_natively_included._block_core.core_helpers.helper_functions import register_hotkeys, unregister_hotkeys
from .blocks_natively_included._block_core.core_helpers.constants import Core_Block_Loggers

#================================================================
# MAIN REGISTRATION
# This main __init__ file should own/register no bpy.types.* classes
# Instead, all classes should be owned & registered by a block
#================================================================

def register():
    
    # Two feature-wrapper classes (runtime-cache & loggers) are initialized first
    if not Wrapper_Runtime_Cache.init_pre_bpy():
        raise Exception("Runtime Cache Wrapper failed pre-bpy init")
    if not Wrapper_Loggers.init_pre_bpy(): # The "get_logger(...)"" func will work after this step
        raise Exception("Logger Wrapper failed pre-bpy init")
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting main registration for Addon '{addon_name}'")

    # Block Managmenet feature-wrapper is created next, and is used immediately after (Triggers init tasks on other core-block features)
    Wrapper_Block_Management.init_pre_bpy(blocks_to_register = _ordered_blocks_list)

    # Identify valid blocks to register. Invalid blocks are skipped, with an error logged in the console
    # Causes of invalid blocks: TODO webpage link
    valid_block_packages = Wrapper_Block_Management.validate_block_list_before_registration(_ordered_blocks_list)

    # Call registration logic of each block, in order. Core-block should always be first in this list
    # Most init tasks for core-block features are already completed by this point, but 
    # Other features, from other blocks, may have their own init tasks. These are automatically triggered inside 'register_block'
    for block in valid_block_packages:
        block.register_block()
    
    logger.log_with_linebreak(f"Finished main registration for Addon '{addon_name}'")

def unregister():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    try: 
        logger.log_with_linebreak(f"Starting main unregistration for Addon '{addon_name}'")
    except:
        pass

    # Unregister other DGBlock packages
    # This should be done in the opposite order as register()
    for block in reversed(_ordered_blocks_list):
        try:
            block.unregister_block()
        except:
            logger.error(f"Exception when unregistering block '{block._BLOCK_ID}': ", exc_info = True)

    # Block-manager does cleanup tasks for itself & all other core-block features
    Wrapper_Block_Management.destroy_wrapper()
    
    try:
        logger.log_with_linebreak(f"Finished main unregistration for Addon '{addon_name}'")
        print("\n")
    except:
        pass

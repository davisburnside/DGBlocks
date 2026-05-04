
from enum import Enum, EnumMeta
import inspect
import os
from copy import deepcopy
import logging
from types import ModuleType
from dataclasses import is_dataclass, replace, asdict
from typing import Any, Callable, Collection, List, Optional
import numpy as np
import bpy  # type: ignore
import mathutils # type: ignore

# addon_helper_funcs module can only import from .addon_config.py in this addon, to prevent circular deps
from ..my_addon_config import should_show_developer_ui_panels, addon_name

# --------------------------------------------------------------
# Generic Blender helpers
# --------------------------------------------------------------

def is_bpy_ready():
    try:
        if bpy.context is None or bpy.context.window is None or bpy.context.scene is None:
            return False
        return True
    except:
        return False

def force_reload_all_scripts(context, logger = None):
    
    # disable / reenable modal operator between reload
    if "dgblocks_display_modal_props" in context.scene:
        was_ui_display_modal_active = context.scene.dgblocks_display_modal_props.myaddon_display_active
        if was_ui_display_modal_active:
            logger.debug("Temporarily Deactivating UI Display Modal")
            context.scene.dgblocks_display_modal_props.myaddon_display_active = False
        bpy.ops.script.reload()
        if was_ui_display_modal_active:
            if logger:
                logger.debug("Reactivating UI Display Modal")
            context.scene.dgblocks_display_modal_props.myaddon_display_active = True

    # No modal operator, reload normally
    else:
        if logger:
            logger.debug("Reactivating UI Display Modal")
        bpy.ops.script.reload()

def force_redraw_ui(context:bpy.context):
    
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def get_addon_preferences(context:bpy.context):
    prefs = context.preferences.addons[addon_name].preferences
    return prefs

# --------------------------------------------------------------
# Printing/Logging tools, useful when logger-FWC status is unknown, like during startup/shutdown
# --------------------------------------------------------------

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\033[2J\033[H", end="")

def print_section_separator(text, width=100, char="="):
    
    print(f"\n{char * width}")
    print(text.center(width))
    print(f"{char * width}\n")

# --------------------------------------------------------------
# Block tools
# --------------------------------------------------------------

def get_self_block_module(block_manager_wrapper: ModuleType):
    """  
    Get the actual block module (__init__.py file) being added
    This function only works when called directly from a block's __init__.py
    """
    
    caller_frame = inspect.stack()[1] # Gets the module which called the current function
    block_module = inspect.getmodule(caller_frame.frame)
    # _is_valid = len(block_manager_wrapper.validate_block_list_before_registration([block_module])) == 1
    # if not _is_valid:
    #     raise Exception("Wrapper_Block_Management.create_instance must be called directly from a Block's main '__init__.py' Module")
    return block_module
        
def get_block_module_by_id(block_id: str, registered_blocks: List[ModuleType]) -> ModuleType:
    """Look up a block module by its ID."""
        
    return next(
        (b for b in registered_blocks if b._BLOCK_ID == block_id),
        None
    )

def find_blocks_owning_func_with_name(func_name: str, registered_blocks:list[ModuleType], logger: Optional[logging.Logger] = None) -> List[ModuleType]:
    """Find all registered blocks that have a function with the given name."""
    
    blocks = [
        block for block in registered_blocks
        if hasattr(block.block_module, func_name)
    ]
    if logger:
        block_ids = [b._BLOCK_ID for b in blocks]
        logger.debug(f"Found {len(blocks)} blocks with hook func '{blocks}': {block_ids}")
    return blocks

# --------------------------------------------------------------
# Other
# --------------------------------------------------------------

def get_names_of_parent_classes(python_obj: any):
    
    parent_classes = [cls.__name__ for cls in python_obj.__mro__]
    return parent_classes

def should_draw_delevoper_panel(context):
    return should_show_developer_ui_panels and context.scene.dgblocks_core_props.addon_is_active

def register_hotkeys():
        
    # Add keymap entry
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        
        km = kc.keymaps.new(name='Window', space_type='EMPTY')
        
        # kmi1 = km.keymap_items.new(op_name, type='T', value='PRESS', ctrl=True, shift=True)
        # kmi1.active = True  
        
        for hotkey_data in my_addon_config.addon_hotkeys:
            name = hotkey_data["OP_NAME"]
            kmi2 = km.keymap_items.new(
                    name, 
                    type=hotkey_data["TYPE"], 
                    value='PRESS', # Keypress event
                    ctrl =hotkey_data["CTRL"],
                    alt = hotkey_data["ALT"],
                    shift = hotkey_data["SHIFT"],
                    head=True)
            kmi2.active = True    
            logger.info(f"Added hotkey {name}")
        
def unregister_hotkeys():
        
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps['Window']
        for kmi in km.keymap_items:
            if kmi.idname in [k["OP_NAME"] for k in my_addon_config.addon_hotkeys]:
                logger.info(f"removing hotkey {kmi.idname}")
                km.keymap_items.remove(kmi)

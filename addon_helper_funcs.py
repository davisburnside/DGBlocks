
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

# addon_helper_funcs module can only import from .addon_config.py in this addon, to prevent circular deps
from .my_addon_config import should_show_developer_ui_panels, addon_name

# --------------------------------------------------------------
# Maintenance tools
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

# --------------------------------------------------------------
# Logging tools, multipurpose & useful when logger-FWC status is unknown
# --------------------------------------------------------------

def log_or_print(message:str, level:str, logger:logging.Logger = None):
    level_int = getattr(logging, level.upper(), logging.INFO)
    logger.log(level_int, message) if logger else print(message)

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\033[2J\033[H", end="")

# --------------------------------------------------------------
# Python Data tools
# --------------------------------------------------------------

def is_py_listy(obj):
    return isinstance(obj, set) or isinstance(obj, list) or isinstance(obj, tuple)

def is_py_dicty_or_listy(obj):
    return is_py_listy(obj) or isinstance(obj, dict) or is_dataclass(obj)

def py_dicty_has_field(obj, field_name):
    """ Works on Dicts & @Dataclasses """
    if isinstance(obj, dict):
        return field_name in obj
    return hasattr(obj, field_name)

def py_dicty_get_field_value(obj, field_name):
    """ Works on Dicts & @Dataclasses """
    if isinstance(obj, dict):
        return obj[field_name]
    return getattr(obj, field_name)

def create_dict_from_nested_enum_classes(enum_cls):
    return {
        member.name: (
            create_dict_from_nested_enum_classes(member.value) if isinstance(member.value, EnumMeta)
            else deepcopy(member.value)
        )
        for member in enum_cls
    }

def fast_deepcopy_with_fallback(obj: Collection, logger:logging.Logger = None) -> Any:
    """
    Fast deepcopy for arbitrary structures.
    Copyable types: primitives, collections, tuples, Loggers, @dataclasses
    """
    
    # Tuples can't be natively copied, they require deepcopy
    if isinstance(obj, tuple):
        return tuple(deepcopy(item) for item in obj)
    
    # Collection-types
    elif isinstance(obj, dict):
        return {k: fast_deepcopy_with_fallback(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fast_deepcopy_with_fallback(item) for item in obj]
    
    # Raw values
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj

    # Enums classes (potentially nested) as values, like for 'Global_Addon_State'
    elif isinstance(obj, EnumMeta):
        return create_dict_from_nested_enum_classes(obj)

    # Return references as-is (don't copy modules, or callables)
    # elif isinstance(obj, (ModuleType, Callable)):
    #     return obj

    # Use replace() for dataclass instances.
    elif is_dataclass(obj) and not isinstance(obj, type):
        return replace(obj)
    
    elif isinstance(obj, logging.Logger):
        return obj

    try:
        # attempt python-native copy()
        if hasattr(obj, 'copy') and callable(obj.copy):
            return obj.copy()
        return obj.__class__(obj) if hasattr(obj, '__class__') else obj
    except Exception as e:
        print(f"Failed to copy object of type {type(obj)}. Returning original. Error: {e}", logger)
        return obj

def create_simplified_list_from_csv_string(input_str):
    
    list_return = input_str.split(",") # Make str list from str
    list_return = [k.strip() for k in list_return] # strip whitespace from start & end of each str
    list_return = [k for k in list_return if len(k) > 0] # remove empties
    return list_return

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
# Convenience functions for CollectionProperty / PropertyGroup
# --------------------------------------------------------------

def get_addon_preferences(context:bpy.context):
    prefs = context.preferences.addons[addon_name].preferences
    return prefs

def get_members_and_values_of_propertygroup_with_name_prefix(prop_group, prefix=None):
    skip = {'rna_type', 'name'}
    
    def walk(current_group):
        data = {}
        for prop in current_group.bl_rna.properties:
            prop_id = prop.identifier
            if prop_id in skip:
                continue
            
            val = getattr(current_group, prop_id)
            
            # Case 1: Pointer (Nested PropertyGroup)
            if prop.type == 'POINTER' and hasattr(val, "bl_rna"):
                data[prop_id] = walk(val)
            
            # Case 2: Collection
            elif prop.type == 'COLLECTION':
                data[prop_id] = [walk(item) for item in val if hasattr(item, "bl_rna")]
            
            # Case 3: Standard Value
            else:
                data[prop_id] = val
        return data

    # Initial filtering logic
    top_data = {}
    for prop in prop_group.bl_rna.properties:
        prop_id = prop.identifier
        
        # Apply prefix filter only at the start
        if prefix and not prop_id.lower().startswith(prefix.lower()):
            continue
        if prop_id in skip:
            continue
            
        val = getattr(prop_group, prop_id)
        
        if prop.type == 'POINTER' and hasattr(val, "bl_rna"):
            top_data[prop_id] = walk(val)
        elif prop.type == 'COLLECTION':
            top_data[prop_id] = [walk(item) for item in val if hasattr(item, "bl_rna")]
        else:
            top_data[prop_id] = val
            
    return top_data

def diff_collections(old_keys, new_keys):
    """
    Find differences between two key collections for sync operations.
    
    Args:
        old_keys: Iterable of keys from current/old state (e.g., RTC dict keys)
        new_keys: Iterable of keys from new/desired state (e.g., scene property names)
    
    Returns:
        tuple: (to_add, to_remove, to_update) - three sets of keys
            - to_add: Keys in new but not in old (create these)
            - to_remove: Keys in old but not in new (delete these)
            - to_update: Keys in both (update these)
    
    Example:
        >>> to_add, to_remove, to_update = diff_collections(
        ...     rtc_timers.keys(),
        ...     [t['timer_name'] for t in scene_data['timers']]
        ... )
        >>> for name in to_remove:
        ...     destroy_instance(name)
    """
    old = set(old_keys)
    new = set(new_keys)
    
    return (
        new - old,      # to_add
        old - new,      # to_remove
        old & new       # to_update (intersection)
    )

# --------------------------------------------------------------
# General Convenience functions
# --------------------------------------------------------------

def get_names_of_parent_classes(python_obj: any):
    
    parent_classes = [cls.__name__ for cls in python_obj.__mro__]
    return parent_classes


def should_draw_delevoper_panel(context):
    return should_show_developer_ui_panels and context.scene.dgblocks_core_props.addon_is_active


from abc import ABC
from collections import defaultdict
from enum import Enum, EnumMeta
import inspect
import os
from copy import deepcopy
import logging
from pathlib import Path
import traceback
import time
from types import ModuleType
from dataclasses import is_dataclass, replace, asdict
from typing import Any, Callable, Collection, List, Optional
import numpy as np
import bpy  # type: ignore
import mathutils # type: ignore
from ..addon_config.static_settings import should_show_developer_ui_panels, addon_name

# --------------------------------------------------------------
# Generic Blender helpers
# --------------------------------------------------------------
global _dirty_wrapper_runtime_cache
def get_Wrapper_Runtime_Cache():

    global _dirty_wrapper_runtime_cache
    return _dirty_wrapper_runtime_cache

def set_Wrapper_Runtime_Cache(val):
    global _dirty_wrapper_runtime_cache
    _dirty_wrapper_runtime_cache = val

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

def force_redraw_ui(context:bpy.context = None):
    
    context = context if context else bpy.context
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

def get_exception_last_n_lines(n: int, exc: BaseException | None = None) -> str:
    """
    Returns the last N lines of a stacktrace as a single string.
    If exc is None, uses the current exception (if any).
    """
    if exc is not None:
        lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    else:
        lines = traceback.format_exception(*sys.exc_info())

    full_text = "".join(lines)
    split_lines = full_text.splitlines()
    return "\n".join(split_lines[-n:])

# --------------------------------------------------------------
# Block tools
# --------------------------------------------------------------

def get_self_block_module():
    """  
    Get the actual block module (__init__.py file) being added
    This function only works when called directly from a block's __init__.py
    """
    
    caller_frame = inspect.stack()[1] # Gets the module which called the current function
    block_module = inspect.getmodule(caller_frame.frame)
    return block_module

def is_block_debug_mode_enabled(block_id: str) -> bool:
    """
    True when the named block's `debug_mode_enabled` flag is set.

    Debug mode lives on the block's RTC record (`REGISTRY_ALL_BLOCKS`), which is toggled
    from core's All Blocks UIList. Looking the record up by `block_id` avoids depending on
    the unstable index of `scene.dgblocks_core_props.managed_blocks[N]`.

    Never raises — returns False when the cache is unavailable (startup / teardown).
    """
    try:
        cache = get_Wrapper_Runtime_Cache()
        for block_record in cache.get_cache("REGISTRY_ALL_BLOCKS") or []:
            if block_record.block_id == block_id:
                return bool(block_record.debug_mode_enabled)
    except Exception:
        return False
    return False

def find_blocks_owning_func_with_name(func_name: str, registered_blocks:list[ModuleType], logger: Optional[logging.Logger] = None) -> List[ModuleType]:
    """Find all registered blocks that have a function with the given name."""
    
    blocks = [
        block for block in registered_blocks
        if hasattr(block.block_module, func_name)
    ]
    if logger:
        block_ids = [b.block_id for b in blocks]
        logger.debug(f"Found {len(blocks)} blocks with func '{func_name}': {block_ids}")
    return blocks

def validate_block_list_before_registration(blocks_to_register: list[any]):

    # A list of variables and functions names, required in a block's __init__.py
    required_in_block = ["_BLOCK_DEPENDENCIES", "_BLOCK_VERSION", "_BLOCK_ID", "register_block", "unregister_block"]
    valid_block_names = []
    valid_blocks = []
    invalid_blocks = defaultdict(list) 
    for block_main_file in blocks_to_register:

        # Validate block contents
        should_skip_package = False
        for required_ in required_in_block:
            if not hasattr(block_main_file, required_):
                file_dunder_name = block_main_file.__name__
                error_str = f"Could not register {file_dunder_name} as a Block. Its __init__.py is missing a required variable/function: '{required_}'"
                invalid_blocks[block_id].append(error_str)
                should_skip_package = True
        if should_skip_package:
            continue

        # Validate block ID uniqueness
        block_id = getattr(block_main_file, "_BLOCK_ID")
        if block_id in valid_block_names:
            error_str = f"Block with ID {block_id} is already registered"
            invalid_blocks[block_id].append(error_str)
            continue

        # Validate installation of other blocks that the current depends on
        block_deps = getattr(block_main_file, "_BLOCK_DEPENDENCIES")
        for dependent_block_id in block_deps:
            if dependent_block_id not in valid_block_names:
                error_str = "Block {block_id} depends on {dependent_block_id}, but it is not registered. All registered blocks: [ {', '.join(valid_block_names)} ]"
                invalid_blocks[block_id].append(error_str)
                should_skip_package = True
        if should_skip_package:
            continue

        valid_blocks.append(block_main_file)
        valid_block_names.append(block_id)

    return valid_blocks, invalid_blocks




# --------------------------------------------------------------
# Feature-Wrapper-Class tools
# --------------------------------------------------------------

def determine_FWC_abstract_funcs(actual_class: type) -> list[str]:

    # Collect all ABC bases (excluding the class itself and object)
    abc_bases = [
        base for base in inspect.getmro(actual_class)
        if base not in (actual_class, object) and issubclass(base, ABC)
    ]

    # Collect all abstract method names defined in those bases
    abstract_methods = {
        name
        for base in abc_bases
        for name, member in vars(base).items()
        if getattr(member, "__isabstractmethod__", False)
    }

    missing_func_implementations = [
        name for name in abstract_methods
        if not (
            isinstance(vars(actual_class).get(name), classmethod)
            and not getattr(vars(actual_class).get(name), "__isabstractmethod__", False)
        )
    ]

    present_func_implementations = [
        name for name in abstract_methods
        if (
            isinstance(vars(actual_class).get(name), classmethod)
            and not getattr(vars(actual_class).get(name), "__isabstractmethod__", False)
        )
    ]

    return present_func_implementations, missing_func_implementations

def validate_FWC_data_mirrors_after_init():
    pass
# --------------------------------------------------------------
# Other
# --------------------------------------------------------------

# def get_ts_millis() -> int:
#     return time.time() // 1_000_000

# def get_ts() -> int:
#     return time.time()

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

def is_same_class_by_name(obj, cls) -> bool:
    """Check if `obj` is an instance of `cls` by class name, sidestepping
    identity issues from double-imported modules.
    
    Use only as a fallback for the `isinstance` double-import problem;
    prefer fixing the import paths when possible.
    """
    return type(obj).__name__ == cls.__name__

def validate_func_args(func, expected_args: list[str]) -> None:
    """Raise TypeError if `func`'s parameter names don't exactly match `expected_args`.
    
    Order matters; *args/**kwargs are included by their declared names.
    """
    actual_args = list(inspect.signature(func).parameters.keys())
    
    if actual_args != expected_args:
        raise TypeError(
            f"Function '{func.__name__}' has args {actual_args}, expected {expected_args}"
        )

def get_folder_parts(module) -> list[str]:
    """Return the folder names containing the module, from filesystem root down."""
    return list(Path(module.__file__).parent.parts)

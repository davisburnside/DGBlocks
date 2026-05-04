"""
Handler Listener Adapter System for Blender Addons

Provides a unified interface for managing various Blender app handlers:
- depsgraph_update_pre / depsgraph_update_post
- frame_change_pre / frame_change_post
- undo_pre / undo_post
- redo_pre / redo_post
- save_pre / save_post
- object_bake_pre / object_bake_post (texture bake)
- composite_pre / composite_post

All handlers share consistent create/delete/callback patterns with
debouncing, ignore flags, and runtime cache integration.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import bpy
from bpy.types import Depsgraph, Object, Scene

from ..native_blocks._block_core.core_feature_logs import get_logger
from ..native_blocks._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache

from .block_constants import Enum_Runtime_Cache_Keys, Enum_Event_Listener_Definitions

from .block_constants import Block_Logger_Definitions

# =============================================================================
# WRAPPER CLASS - Encapsulates listener logic
# =============================================================================

@dataclass
class Event_Listener_Wrapper:
    # All listeners live inside runtime data cache. They are created/destroyed as listeners are enabled/disabled through dgblocks_event_listener_props props
    # For a single addon, there is always either 0 or 1 listener for each type. Other addons may create their own listeners
    # Each listener has a corresping bpy.app.handlers collection, to hold the Event_Listener_Wrapper instance itself as a callback function (enabled with __call__ func)
    
    handler_type: Enum_Event_Listener_Definitions
    should_ignore_updates: bool = False
    timestamp_last_trigger: float = 0.0
    ms_delay_between_triggers: float = 0.0
    is_registered: bool = False
    logger: logging.Logger = None
    
    @property
    def cache_key(self) -> str:
        return self.handler_type.handler_attr
    
    @property
    def listener_id(self) -> str:
        return self.handler_type.hook_suffix
    
    @property
    def hook_func_name(self) -> str:
        return f"callback_hook_listener_{self.handler_type.hook_suffix}"
    
    def should_skip(self) -> bool:
        if self.should_ignore_updates:
            return True
        if self.ms_delay_between_triggers > 0:
            elapsed_ms = (time.time() - self.timestamp_last_trigger) * 1000
            if elapsed_ms < self.ms_delay_between_triggers:
                return True
        return False
    
    def propogate_event_to_hooked_blocks(self, *args) -> None:
        
        print("args", args)
        self.timestamp_last_trigger = time.time()
        hook_func_name = self.hook_func_name
        blocks_to_propogate_event_to = get_hooked_blocks_metadata_for_func(hook_func_name)
        for block_module in blocks_to_propogate_event_to:
            try:
                self.logger.debug(f"Triggering hook function {hook_func_name} in {block_module._BLOCK_ID}")
                if hook_func := getattr(block_module, hook_func_name, None):
                    result = hook_func(*args)
            except Exception as e:
                self.logger.error(f"Failed Triggering hook function {hook_func_name} in {block_module._BLOCK_ID}", exc_info = True)
    
    def __call__(self, *args) -> None:
        """Makes the instance directly usable as a Blender handler callback."""
        try:
            if self.should_skip():
                if self.logger:
                    self.logger.debug(f"skip {self.cache_key}")
            else:
                if self.logger:
                    self.logger.info(f"trigger {self.cache_key}")
                self.propogate_event_to_hooked_blocks(*args)
        except Exception as e:
            print(f"[Listener] {self.cache_key}: {e}")

# =============================================================================
# INTERNAL API - Used only inside this block
# =============================================================================

def _get_listener(handler_type: Enum_Event_Listener_Definitions) -> Event_Listener_Wrapper | None:
    """Retrieve a listener listener_wrapper from cache."""

    all_listener_wrappers = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.EVENT_LISTENER_WRAPPER_CACHE, default = {})
    listener_wrapper = all_listener_wrappers.get(handler_type.handler_attr)
    return listener_wrapper

def _add_listener(listener_definition: Enum_Event_Listener_Definitions) -> Event_Listener_Wrapper:

    logger = get_logger(Block_Logger_Definitions.LISTENERS)

    if existing_listener_wrapper := _get_listener(listener_definition):
        logger.info(f"Event listener wrapper for {listener_definition.handler_attr} already exists, skipping creation")
        return existing_listener_wrapper

    logger.info(f"Creating event listener wrapper for {listener_definition.handler_attr}")
    new_listener_wrapper = Event_Listener_Wrapper(handler_type=listener_definition, logger=logger)

    # Store in cache
    all_listener_wrappers = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.EVENT_LISTENER_WRAPPER_CACHE)
    if all_listener_wrappers is None:
        all_listener_wrappers = {}
    all_listener_wrappers[new_listener_wrapper.cache_key] = new_listener_wrapper
    Wrapper_Runtime_Cache.set_cache(Enum_Runtime_Cache_Keys.EVENT_LISTENER_WRAPPER_CACHE, all_listener_wrappers)

    # Register the instance itself as the handler callback
    bpy_app_handlers = listener_definition.bpy_app_handlers_collection_of_listener
    if new_listener_wrapper not in bpy_app_handlers:
        logger.info(f"Adding event listener wrapper '{listener_definition.handler_attr}' to bpy.app.handlers")
        bpy_app_handlers.append(new_listener_wrapper)
        log_all_current_bpy_app_handlers_for_type(logger, listener_definition.handler_attr)

    new_listener_wrapper.is_registered = True
    return new_listener_wrapper

def _remove_listener(listener_definition: Enum_Event_Listener_Definitions, keep_bpy_app_handler_callback = False) -> bool:
    """Unregister and remove a listener. Returns True if removed."""
    
    logger = get_logger(Block_Logger_Definitions.LISTENERS)
    
    bpy_app_handlers = listener_definition.bpy_app_handlers_collection_of_listener
    listener_wrapper = _get_listener(listener_definition)
    if not listener_wrapper or not listener_wrapper:
        logger.info(f"Event listener '{listener_definition.handler_attr}' is not present in bpy.app.handlers, nothing to remove")
        return False
    
    all_listener_wrappers = Wrapper_Runtime_Cache.get_cache(Enum_Runtime_Cache_Keys.EVENT_LISTENER_WRAPPER_CACHE)
    if not keep_bpy_app_handler_callback:
        if (c := all_listener_wrappers.get(listener_wrapper.cache_key)) and c in bpy_app_handlers:
            logger.info(f"Removing event listener wrapper '{listener_definition.handler_attr}' to bpy.app.handlers: ")
            bpy_app_handlers.remove(c)
            log_all_current_bpy_app_handlers_for_type(logger, listener_definition.handler_attr)
    
    all_listener_wrappers.pop(listener_wrapper.cache_key, None)

def log_all_current_bpy_app_handlers_for_type(logger:logging.Logger, handlers_collection_name: str):
    
    # if 
    
    # This will include handlers from other addons
    all_handlers_of_type = getattr(bpy.app.handlers, handlers_collection_name)
    # if all_handlers_of_type is None:
        
    logger.debug(f"All members of bpy.app.handlers.{handlers_collection_name}: {[m.__class__ for m in all_handlers_of_type]}")


# =============================================================================
# PROPERTY UPDATE FUNC FACTORY
# Creates unique functions for each dgblocks_event_listener_props.enable_listener* property-update callback
# =============================================================================

def _factory_property_update_func(listener_definition: Enum_Event_Listener_Definitions) -> Callable:
    """Create update function for a BoolProperty toggling this listener."""
    
    prop_name = listener_definition.property_name
    
    def update(self, context):
        if getattr(self, prop_name, False):
            _add_listener(listener_definition)
        else:
            _remove_listener(listener_definition)
    
    return update

# =============================================================================
# 
# =============================================================================

def create_hook_references_for_all_event_listeners(context, logger):
    
    # Create references for each block hook of each listener type
    for handler in Enum_Event_Listener_Definitions:
        
        # Define name of function to search for
        func_name_suffix = handler.value[0]
        hook_func_name = f"block_api_{func_name_suffix}"
        
        hooked_blocks = find_blocks_owning_func_with_name(hook_func_name, logger)
        
        # Find all blocks that contain the hook function
        for block_module in hooked_blocks:
            block_id = block_module._BLOCK_ID
            add_block_hook_metadata_to_runtime_cache(hook_func_name, block_id, logger)

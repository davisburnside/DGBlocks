from dataclasses import asdict, is_dataclass, fields
from enum import Enum
import threading
from contextlib import nullcontext
from typing import Any, Optional
import numpy as np
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helper_funcs import fast_deepcopy_with_fallback, is_py_listy, py_dicty_get_field_value, py_dicty_has_field
from ....addon_data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ..core_helpers.constants import Core_Runtime_Cache_Members

#=================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
#=================================================================================

class Wrapper_Runtime_Cache(Abstract_Feature_Wrapper):
    """
    Thread-safe runtime data cache. Data is not persisted to .blend file.
    Use thread lock when:
    - Making structural changes (adding/removing items)
    - Need guaranteed consistency
    - Modifying shared data structures
    """
    
    _cache: Optional[dict[str, Any]] = None
    _lock: threading.RLock = threading.RLock()

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        
        # Initialize the cache
        cls.destroy_wrapper()
        cls._cache = {}  # Force new dict instance
        cls._lock = threading.RLock()  # Force new lock instance
        
        # Create Runtime cache members with default values.
        for rtc_member in Core_Runtime_Cache_Members:
            member_key = rtc_member.name
            member_default_value = rtc_member.value[1] # Supported RTC value types = primitives, types, python collections, Enum classes, and @dataclasses
            default_value_copy = fast_deepcopy_with_fallback(member_default_value) 
            cls.set_cache(member_key, default_value_copy)
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        # Initialize the cache. Called after of addon registration
        return True # No actions to take

    @classmethod
    def destroy_wrapper(cls):
        # Clear all cache data. Called during unregister
        with cls._lock:
            cls._cache = {}

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_cache(
        cls, 
        new_key: str, 
        new_value: Any,
        should_copy: bool = False, # Does not guarantee a full deep copy. Members may be undefined for .copy(), and the original data is returned
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ):
        
        existing_cache = cls.get_cache(
            key = new_key, 
            should_copy = False, 
            should_use_thread_lock = should_use_thread_lock,
        )
        if existing_cache is None:
            cls.set_cache(
                key = new_key, 
                value = new_value, 
                should_copy = should_copy, 
                should_use_thread_lock = should_use_thread_lock,
            )
    
    @classmethod
    def get_cache(
        cls,
        key: str,
        should_copy: bool = False, # Does not guarantee a full deep copy. Members may be undefined for .copy(), and the original data is returned
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ) -> Any:

        with cls._lock if should_use_thread_lock else nullcontext():
            true_key = get_actual_rtc_key(key, fail_gracefully = False)
            value = cls._cache.get(true_key)
            if should_copy and value is not None:
                return fast_deepcopy_with_fallback(value)
            return value
    
    @classmethod
    def set_cache(
        cls, 
        key: str, 
        value: Any,
        should_copy: bool = False, # Does not guarantee a full deep copy. Members may be undefined for .copy(), and the original data is returned
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ):
        
        with cls._lock if should_use_thread_lock else nullcontext():
            true_key = get_actual_rtc_key(key, fail_gracefully = False)
            if should_copy and value is not None:
                value = fast_deepcopy_with_fallback(value)
            cls._cache[true_key] = value

    @classmethod
    def remove_cache(cls, key: str, should_use_thread_lock:bool = True):

        with cls._lock if should_use_thread_lock else nullcontext():
            true_key = get_actual_rtc_key(key, fail_gracefully = False)
            if true_key in cls._cache:
                del cls._cache[true_key]

    # --------------------------------------------------------------
    # Funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def add_unique_instance_to_registry_list(cls, member_key:str, uniqueness_field:str, new_instance: any, should_use_thread_lock:bool = True):
        """
        This function adds unique instances to an RTC main member in a way that facilitates simple RTC <--> BL Data syncs
        It raises an exception on data validation failure
        """

        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        current_data = cls.get_cache(true_member_key, should_use_thread_lock = should_use_thread_lock)

        # Validate data structure
        if current_data is None:
            raise Exception(f"RTC member '{true_member_key}' is invalid: {current_data}")
        if not is_py_listy(current_data):
            raise Exception(f"RTC member '{true_member_key}' must be a list/set/tuple. It is instead a '{current_data.__class__}'")
        if not py_dicty_has_field(new_instance, uniqueness_field):
            _exception_missing_required_field(true_member_key, uniqueness_field)

        # Validate uniqueness
        new_unique_value = py_dicty_get_field_value(new_instance, uniqueness_field)
        unique_values = set(new_unique_value)
        for idx, existing_instance in enumerate(current_data):
            if not py_dicty_has_field(existing_instance, uniqueness_field):
                _exception_missing_required_field(member_key, uniqueness_field, idx)
            instance_field_value = getattr(existing_instance, uniqueness_field)
            if instance_field_value in unique_values:
                message = f"RTC member '{member_key}' already contains an instance at index {idx} with unique field '{uniqueness_field}' value '{instance_field_value}'"
                print(message)
                return
                # raise Exception(f"RTC member '{member_key}' already contains an instance at index {idx} with unique field '{uniqueness_field}' value '{instance_field_value}'")
            unique_values.add(instance_field_value)

        # Update RTC member with new instance
        current_data.append(new_instance)
        cls.set_cache(member_key, current_data)

    @classmethod
    def get_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_use_thread_lock:bool = True):
        """
        This function adds unique instances to an RTC main member in a way that facilitates simple RTC <--> BL Data syncs
        It raises an exception on data validation failure
        """

        current_data = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        for idx, existing_instance in enumerate(current_data):
            # if not py_dicty_has_field(existing_instance, uniqueness_field):
            #     _exception_missing_required_field(member_key, uniqueness_field, idx)

            instance_field_value = getattr(existing_instance, uniqueness_field)
            if instance_field_value == uniqueness_field_value:
                return idx, existing_instance
            
        return -1, None

    @classmethod
    def destroy_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_use_thread_lock:bool = True):
        
        current_data = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        idx_to_remove = -1
        for idx, existing_instance in enumerate(current_data):
            # if not py_dicty_has_field(existing_instance, uniqueness_field):
            #     _exception_missing_required_field(member_key, uniqueness_field, idx)
            instance_field_value = getattr(existing_instance, uniqueness_field)
            if instance_field_value == uniqueness_field_value:
                idx_to_remove = idx
                break

        if idx_to_remove >= 0:
            del current_data[idx_to_remove]
    
    @classmethod
    def get_all_with_key_value_from_registry_list(cls, member_key:str, key_field_name:str, key_field_value: any, should_use_thread_lock:bool = True):


        current_data = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        return_idxs = []
        return_instances = []
        for idx, existing_instance in enumerate(current_data):
            # if not py_dicty_has_field(existing_instance, key_field_name):
            #     _exception_missing_required_field(member_key, key_field_name, idx)

            instance_field_value = getattr(existing_instance, key_field_name)
            if instance_field_value == key_field_value:
                return_idxs.append(idx)
                return_instances.append(existing_instance)

        return return_instances
    
    @classmethod
    def destroy_all_with_key_value_from_registry_list(cls, member_key:str, key_field_name:str, key_field_value: any, should_use_thread_lock:bool = True):
     
        current_data = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        idxs_to_delete = []
        for idx, existing_instance in enumerate(current_data):
            instance_field_value = getattr(existing_instance, key_field_name)
            if instance_field_value == key_field_value:
                idxs_to_delete.append(idx)

        for idx in reversed(idxs_to_delete):
            del current_data[idx]

    @classmethod
    def is_cache_flagged_as_syncing(cls, member_key: str):
        
        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        cache_names_being_synced = cls.get_cache(Core_Runtime_Cache_Members.META_REGISTRIES_BEING_SYNCED)
        if true_member_key in cache_names_being_synced:
            return True
        else:
            return False
        
    @classmethod
    def flag_cache_as_syncing(cls, member_key: str, is_actively_syncing: bool):

        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        cache_names_being_synced = cls.get_cache(Core_Runtime_Cache_Members.META_REGISTRIES_BEING_SYNCED)
        if true_member_key in cache_names_being_synced and not is_actively_syncing:
            cache_names_being_synced.remove(true_member_key)
        elif true_member_key not in cache_names_being_synced and is_actively_syncing:
            cache_names_being_synced.append(true_member_key)

#=================================================================================
# CONVENIENCE FUNCTIONS
#=================================================================================

def get_actual_rtc_key(key:Any, fail_gracefully:bool = True):
    # Enum classes are the standard for defining a block's loggers, RTC members, & other structured data.
    # For code simplicity, Enum member names can be used directly as RTC key.
    if isinstance(key, Enum):
        return key.name
    elif isinstance(key, str):
        return key
    if fail_gracefully:
        return str(key)
    else:
        raise Exception(f"Invalid key: {key} | {key.__class__}")

def _exception_missing_required_field(member_key:any, uniqueness_field:str, list_idx:int = None):

    if list_idx is None:
        raise Exception(f"RTC member '{member_key}' instance is missing required field '{uniqueness_field}'")
    else:
        raise Exception(f"RTC member '{member_key}' instance at list index {list_idx} is missing required field '{uniqueness_field}'")

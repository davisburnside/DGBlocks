# Sample License, ignore for now

# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from enum import Enum
import threading
from contextlib import nullcontext
from typing import Any, Optional

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_tools import fast_deepcopy_with_fallback
from ....addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Events

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ..core_helpers.constants import Core_Runtime_Cache_Members

# ==============================================================================================================================
#  MAIN MODULE FEATURE
# ==============================================================================================================================

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
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
        
        # Initialize the cache
        cls.destroy_wrapper(event = event)
        cls._cache = {}  # Force new dict instance
        cls._lock = threading.RLock()  # Force new lock instance
        
        # Create Runtime cache members with default values.
        for rtc_member in Core_Runtime_Cache_Members:
            member_key = rtc_member.name
            member_default_value = rtc_member.value[1] # Supported RTC value types = primitives, types, python collections, Enum classes, and @dataclasses
            default_value_copy = fast_deepcopy_with_fallback(member_default_value) 
            cls.set_cache(member_key, default_value_copy)

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:
        # Initialize the cache. Called after of addon registration
        return # No actions to take

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events):
        # Clear all cache data. Called during unregister
        with cls._lock:
            cls._cache = {}

    # --------------------------------------------------------------
    # Funcs specific to this class, for cache lifecycle mgmt
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
    # Funcs specific to this class, for getting/setting unique list members
    # --------------------------------------------------------------

    @classmethod
    def cache_list_contains_member(cls, cache_list: list, key_field_name: str, key_field_value: str):
        return any(getattr(item, key_field_name) == key_field_value for item in cache_list)

    @classmethod
    def add_unique_instance_to_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, new_instance: any, should_use_thread_lock:bool = True):

        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        idx, current_instance, all_RTC_list_members = cls.get_unique_instance_from_registry_list(member_key, uniqueness_field, uniqueness_field_value)

        # Validate uniqueness
        if current_instance:
            raise Exception(f"RTC list '{true_member_key}' already contains an instance with '{uniqueness_field}' = '{uniqueness_field_value}'")

        # Update RTC member with new instance
        all_RTC_list_members.append(new_instance)
        cls.set_cache(member_key, all_RTC_list_members)

    @classmethod
    def get_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_copy: bool = False, should_use_thread_lock:bool = True):

        all_RTC_list_members = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        for idx, existing_instance in enumerate(all_RTC_list_members):
            instance_field_value = getattr(existing_instance, uniqueness_field)
            if instance_field_value and instance_field_value == uniqueness_field_value:
                return idx, existing_instance, all_RTC_list_members
            
        return -1, None, all_RTC_list_members

    @classmethod
    def destroy_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_use_thread_lock:bool = True):
        
        idx, current_instance, all_RTC_list_members = cls.get_unique_instance_from_registry_list(member_key, uniqueness_field, uniqueness_field_value, should_use_thread_lock = should_use_thread_lock)
        if idx >= 0:
            del all_RTC_list_members[idx]
        cls.set_cache(member_key, all_RTC_list_members)
        
    @classmethod
    def get_all_with_key_value_from_registry_list(cls, member_key:str, key_field_name:str, key_field_value: any, should_use_thread_lock:bool = True):


        current_data = cls.get_cache(member_key, should_use_thread_lock = should_use_thread_lock)
        return_idxs = []
        return_instances = []
        for idx, existing_instance in enumerate(current_data):

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

    # --------------------------------------------------------------
    # Funcs specific to this class, for getting/setting "is-syncing" metadata for each RTC member cache
    # --------------------------------------------------------------

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

    @classmethod
    def asset_cache_is_not_syncing(cls, cache_key, wrapper_class):
        if cls.is_cache_flagged_as_syncing(cache_key):
            raise Exception(f"'{wrapper_class.__name__}' is flagged as syncing")

# ==============================================================================================================================
# PUBLIC CONVENIENCE FUNCTIONS
# ==============================================================================================================================

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

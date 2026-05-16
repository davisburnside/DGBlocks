
# ==============================================================================================================================
# IMPORTS

from enum import Enum
import threading
from contextlib import nullcontext
from typing import Any, Optional

# --------------------------------------------------------------
# Addon-level imports
from .....addon_helpers.data_tools import fast_deepcopy_with_fallback
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Actions, Enum_Sync_Events, RTC_FWC_Data_Mirror_Instance, RTC_FWC_Instance

# --------------------------------------------------------------
# Intra-block imports
from ...core_helpers.constants import Core_Runtime_Cache_Members
from .data_sync_tools import default_data_mirror_BL_colprop_update_logic, default_data_mirror_RTC_list_update_logic

# --------------------------------------------------------------
# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS

# ==============================================================================================================================
#  MAIN MODULE FEATURE

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
    def init_pre_bpy(cls, event, self_FWC_instance) -> bool:
        
        # Initialize the cache
        cls.destroy_wrapper(event, None)
        cls._cache = {}  # Force new dict instance
        cls._lock = threading.RLock()  # Force new lock instance
        
        # Create Runtime cache members with default values.
        for RTC_member_enum in Core_Runtime_Cache_Members:
            member_default_value = fast_deepcopy_with_fallback(RTC_member_enum.value.default_value) 
            cls.set_cache(RTC_member_enum.name, member_default_value)

    @classmethod
    def init_post_bpy(cls, event, self_FWC_instance) -> bool:
        # Initialize the cache. Called after of addon registration
        return # No actions to take

    @classmethod
    def destroy_wrapper(cls, event, self_FWC_instance):
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
    # Funcs specific to this class, for non-unique list members
    # --------------------------------------------------------------

    @classmethod
    def append_to_cached_list(
        cls, 
        cache_key: str, 
        new_instance: Any,
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ):
        
        with cls._lock if should_use_thread_lock else nullcontext():
            true_key = get_actual_rtc_key(cache_key, fail_gracefully = False)
            cls._cache[true_key].append(new_instance)

    @classmethod
    def remove_from_cached_list(
        cls, 
        cache_key: str, 
        instance_key_field_names: tuple[str],
        instance_key_field_values: tuple[any],
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ):
        
        with cls._lock if should_use_thread_lock else nullcontext():

            # Get indices to remove
            true_key = get_actual_rtc_key(cache_key, fail_gracefully = False)
            cached_list = cls._cache[true_key]
            idxs_to_remove = []
            for idx, instance in enumerate(cached_list):
                eval_instance_key_values = tuple([instance[k] for k in instance_key_field_names])
                if eval_instance_key_values == instance_key_field_values:
                    idxs_to_remove.append(idx)

            # Perform removal
            for idx in idxs_to_remove.reversed():
                del idxs_to_remove[idx]

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
    def assert_cache_is_not_syncing(cls, cache_key):
        if cls.is_cache_flagged_as_syncing(cache_key):
            raise Exception(f"Error: Mirrored cache '{cache_key}' is already flagged as syncing")

    @classmethod
    def resync_single_data_mirror(
        cls, 
        event: Enum_Sync_Events, 
        FWC_instance: RTC_FWC_Instance,
        data_mirror_instance: RTC_FWC_Data_Mirror_Instance,
        BL_is_truth_source:bool,
        logger,
    ) -> None:

        cache_key = data_mirror_instance.RTC_key
        source_type = "Blender" if BL_is_truth_source else "RTC"
        target_type = "RTC" if BL_is_truth_source else "Blender"
        use_default_sync_logic = data_mirror_instance.default_data_path_in_scene is not None
        cached_RTC_list = cls.get_cache(cache_key)

        # Data-mirror has custom sync functions inside the FWC
        if use_default_sync_logic:
            logger.debug(f"(Default list sync) Updating {target_type} with {source_type} truth-source for cache '{cache_key}'")

            # Update RTC with BL data
            actions_denied = set()
            if BL_is_truth_source:
                if data_mirror_instance.RTC_member_type == "list":
                    default_data_mirror_RTC_list_update_logic(
                        FWC_instance,
                        data_mirror_instance,
                        cached_RTC_list,
                        actions_denied,
                        logger,
                    )
                else:
                    print("PLACEHOLDER--------------------------")

            # Update BL with RTC data
            else:

                # Sanity check before syncing BL data. This is needed to prevent update-callback loops in certain cases
                # Custom updates need to peform their own cache-flagging checks & setters
                try:
                    cls.assert_cache_is_not_syncing(cache_key)
                    cls.flag_cache_as_syncing(cache_key, True)

                    # During init, allow add/move/remove but not edit. This allows user choices to be reloaded after save
                    actions_denied = set()
                    if event == Enum_Sync_Events.ADDON_INIT:
                        actions_denied = {Enum_Sync_Actions.EDIT}

                    if data_mirror_instance.RTC_member_type == "list":
                        default_data_mirror_BL_colprop_update_logic(
                            FWC_instance,
                            data_mirror_instance,
                            cached_RTC_list,
                            actions_denied,
                            logger,
                        )
                    else:
                        print("PLACEHOLDER--------------------------")
                except:
                    logger.error("Error", exc_info = True)
                finally:
                    cls.flag_cache_as_syncing(cache_key, False)

        else:
            logger.debug(f"(Custom list sync) Updating {target_type} with {source_type} truth-source for cache '{cache_key}'")
            if BL_is_truth_source:
                FWC_instance.actual_class.update_RTC_with_mirrored_BL_data(event, FWC_instance, data_mirror_instance)
            else:
                FWC_instance.actual_class.update_BL_with_mirrored_RTC_data(event, FWC_instance, data_mirror_instance)

    @classmethod
    def resync_all_data_mirrors(cls, event: Enum_Sync_Events, BL_is_truth_source:bool, logger) -> None:
        """
        Iterate through all registered Feature_Wrapper_References and call their
        update_RTC_with_mirrored_BL_data method.
        """

        source_type = "Blender" if BL_is_truth_source else "RTC"
        target_type = "RTC" if BL_is_truth_source else "Blender"
        logger.debug(f"Updating {target_type} with mirrored {source_type} data for event='{event}'")

        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            for data_mirror_list_instance in FWC_instance.data_mirrors:
                cls.resync_single_data_mirror_list(
                    event, 
                    FWC_instance,
                    data_mirror_list_instance,
                    BL_is_truth_source,
                    logger,
                )

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

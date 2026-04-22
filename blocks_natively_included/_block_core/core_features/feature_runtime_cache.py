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

class Wrapper_Runtime_Cache(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
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
            cls.set_instance(member_key, default_value_copy)
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
    def create_instance(
        cls, 
        new_key: str, 
        new_value: Any,
        should_copy: bool = False, # Does not guarantee a full deep copy. Members may be undefined for .copy(), and the original data is returned
        should_use_thread_lock:bool = True # Parallel threads are bottlenecked for read/write access when this is True
    ):
        
        existing_instance = cls.get_instance(
            key = new_key, 
            should_copy = False, 
            should_use_thread_lock = should_use_thread_lock,
        )
        if existing_instance is None:
            cls.set_instance(
                key = new_key, 
                value = new_value, 
                should_copy = should_copy, 
                should_use_thread_lock = should_use_thread_lock,
            )
    
    @classmethod
    def get_instance(
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
    def set_instance(
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
    def destroy_instance(cls, key: str, should_use_thread_lock:bool = True):

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
        current_data = cls.get_instance(true_member_key, should_use_thread_lock = should_use_thread_lock)

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
        cls.set_instance(member_key, current_data)

    @classmethod
    def get_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_use_thread_lock:bool = True):
        """
        This function adds unique instances to an RTC main member in a way that facilitates simple RTC <--> BL Data syncs
        It raises an exception on data validation failure
        """

        current_data = cls.get_instance(member_key, should_use_thread_lock = should_use_thread_lock)
        for idx, existing_instance in enumerate(current_data):
            # if not py_dicty_has_field(existing_instance, uniqueness_field):
            #     _exception_missing_required_field(member_key, uniqueness_field, idx)

            instance_field_value = getattr(existing_instance, uniqueness_field)
            if instance_field_value == uniqueness_field_value:
                return idx, existing_instance
            
        return -1, None

    @classmethod
    def destroy_unique_instance_from_registry_list(cls, member_key:str, uniqueness_field:str, uniqueness_field_value: any, should_use_thread_lock:bool = True):
        
        current_data = cls.get_instance(member_key, should_use_thread_lock = should_use_thread_lock)
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


        current_data = cls.get_instance(member_key, should_use_thread_lock = should_use_thread_lock)
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
     
        current_data = cls.get_instance(member_key, should_use_thread_lock = should_use_thread_lock)
        idxs_to_delete = []
        for idx, existing_instance in enumerate(current_data):
            instance_field_value = getattr(existing_instance, key_field_name)
            if instance_field_value == key_field_value:
                idxs_to_delete.append(idx)

        for idx in reversed(idxs_to_delete):
            del current_data[idx]

    @classmethod
    def sync_blender_propertygroup_and_raw_python(
        cls, 
        bl_propgroup_data, 
        py_raw_data, 
        blender_as_truth_source=True, 
        use_numpy=False,
        collection_match_fields: dict[str, list[str]] = None
    ):
        """
        Strict reconciliation between Blender PropertyGroups and Python RTC.
        Supports Dicts and Dataclasses.
        
        Args:
            collection_match_fields: Dict mapping collection property names to lists of field names
                                    used to match items by identity rather than index.
                                    e.g. {"my_collection": ["uuid"]} or {"items": ["category", "name"]}
        """
        
        if collection_match_fields is None:
            collection_match_fields = {}

        def get_rtc_value(data, key, default=None):
            """Extract value from Dict, Dataclass, or any object with the attribute."""
            if data is None:
                return default
            if isinstance(data, dict):
                return data.get(key, default)
            if hasattr(data, key):
                return getattr(data, key, default)
            return default

        def to_dict(data):
            """Normalize any dicty/dataclass to a dict for iteration."""
            if data is None:
                return {}
            if isinstance(data, dict):
                return data
            if is_dataclass(data):
                return asdict(data)
            # Generic object with __dict__
            if hasattr(data, '__dict__'):
                return vars(data)
            raise TypeError(f"Cannot convert {type(data).__name__} to dict")

        def to_list(data):
            """Normalize any listy structure to a list."""
            if data is None:
                return []
            if isinstance(data, (list, tuple)):
                return list(data)
            if hasattr(data, '__iter__') and not isinstance(data, (str, dict)):
                return list(data)
            raise TypeError(f"Cannot convert {type(data).__name__} to list")

        def build_match_key(item, match_fields):
            """Build a hashable key from the specified fields of an item."""
            values = []
            for field in match_fields:
                val = get_rtc_value(item, field)
                if val is None:
                    raise ValueError(f"Match field '{field}' is None or missing on item: {item}")
                values.append(val)
            return tuple(values)

        def _sync_to_rtc(bl_data, rtc_template, path="root"):
            """Reads from Blender into RTC."""
            if not ( 
                hasattr(bl_data, "bl_rna") or # Standard RNA types
                bl_data.__class__.__name__ == "bpy_prop_collection_idprop" # Nested CollectionProperty (bpy_prop_collection_idprop)
            ):
                # print(bl_data)
                # print(bl_data.__class__)
                # print(dir(bl_data))
                return bl_data
            
            is_dc_type = isinstance(rtc_template, type) and is_dataclass(rtc_template)
            
            if is_dc_type:
                target_keys = list(rtc_template.__dataclass_fields__.keys())
            elif isinstance(rtc_template, dict):
                target_keys = list(rtc_template.keys())
            elif is_dataclass(rtc_template):
                target_keys = list(rtc_template.__dataclass_fields__.keys())
            else:
                raise TypeError(f"[{path}] rtc_template must be a dict or dataclass, got {type(rtc_template).__name__}")

            result = {}
            
            for key in target_keys:
                current_path = f"{path}.{key}"
                
                if not hasattr(bl_data, key):
                    raise KeyError(f"[{current_path}] Key expected by RTC but missing in Blender PropertyGroup")
                
                rna_prop = bl_data.bl_rna.properties.get(key)
                if rna_prop is None:
                    raise KeyError(f"[{current_path}] Property exists on object but not in bl_rna.properties")
                
                bl_val = getattr(bl_data, key)
                nested_template = get_rtc_value(rtc_template, key)

                if rna_prop.type == 'POINTER':
                    if nested_template is None:
                        raise ValueError(f"[{current_path}] POINTER property requires a nested template, got None")
                    result[key] = _sync_to_rtc(bl_val, nested_template, current_path)
                    
                elif rna_prop.type == 'COLLECTION':
                    if not isinstance(nested_template, list) or len(nested_template) == 0:
                        raise ValueError(f"[{current_path}] COLLECTION property requires a non-empty list template")
                    item_template = nested_template[0]
                    result[key] = [_sync_to_rtc(item, item_template, f"{current_path}[{i}]") for i, item in enumerate(bl_val)]
                    
                else:
                    if rna_prop.is_array:
                        result[key] = np.array(bl_val) if use_numpy else list(bl_val)
                    else:
                        result[key] = bl_val
            
            return rtc_template(**result) if is_dc_type else result

        def _sync_to_blender(bl_data, rtc_data, path="root"):
            """Writes from RTC (Dict, Dataclass, or object) into Blender."""
            try:
                data_map = to_dict(rtc_data)
            except TypeError as e:
                raise TypeError(f"[{path}] {e}")
            
            for key, rtc_val in data_map.items():
                current_path = f"{path}.{key}"
                
                if not hasattr(bl_data, key):
                    bl_name = bl_data.name if hasattr(bl_data, 'name') else type(bl_data).__name__
                    raise AttributeError(f"[{current_path}] RTC key not found in Blender PropertyGroup '{bl_name}'")

                rna_prop = bl_data.bl_rna.properties.get(key)
                if rna_prop is None:
                    raise AttributeError(f"[{current_path}] Property exists on object but not in bl_rna.properties")
                
                bl_val = getattr(bl_data, key)

                # Nested Pointers
                if rna_prop.type == 'POINTER':
                    _sync_to_blender(bl_val, rtc_val, current_path)

                # Collections
                elif rna_prop.type == 'COLLECTION':
                    try:
                        rtc_list = to_list(rtc_val)
                    except TypeError as e:
                        raise TypeError(f"[{current_path}] {e}")
                    
                    match_fields = collection_match_fields.get(key)
                    
                    if match_fields:
                        _sync_collection_by_match(bl_val, rtc_list, match_fields, current_path)
                    else:
                        _sync_collection_by_index(bl_val, rtc_list, current_path)

                # Standard Attributes
                else:
                    current_bl_val = list(bl_val) if rna_prop.is_array else bl_val
                    compare_rtc = rtc_val.tolist() if hasattr(rtc_val, 'tolist') else rtc_val
                    
                    if current_bl_val != compare_rtc:
                        print(f"[DEBUG] BL_EDIT: Updating '{current_path}' | {current_bl_val} -> {compare_rtc}")
                        try:
                            setattr(bl_data, key, rtc_val)
                        except Exception as e:
                            raise RuntimeError(f"[{current_path}] Failed to set value: {e}")

        def _sync_collection_by_index(bl_collection, rtc_list, path):
            """Original index-based collection sync."""
            while len(bl_collection) > len(rtc_list):
                print(f"[DEBUG] BL_EDIT: Removing item from {path} (Index {len(bl_collection)-1})")
                bl_collection.remove(len(bl_collection) - 1)
            
            while len(bl_collection) < len(rtc_list):
                print(f"[DEBUG] BL_EDIT: Adding new item to {path}")
                bl_collection.add()
            
            for i, item_rtc in enumerate(rtc_list):
                _sync_to_blender(bl_collection[i], item_rtc, f"{path}[{i}]")

        def _sync_collection_by_match(bl_collection, rtc_list, match_fields, path):
            """Match-based collection sync using uniqueness fields."""
            
            # Build lookup of existing Blender items by match key
            bl_index_by_key = {}
            for i, bl_item in enumerate(bl_collection):
                try:
                    key = build_match_key(bl_item, match_fields)
                    bl_index_by_key[key] = i
                except ValueError as e:
                    raise ValueError(f"[{path}[{i}]] {e}")
            
            # Build lookup of RTC items
            rtc_by_key = {}
            for i, rtc_item in enumerate(rtc_list):
                try:
                    key = build_match_key(rtc_item, match_fields)
                    if key in rtc_by_key:
                        raise ValueError(f"[{path}] Duplicate match key {key} in RTC data at indices {rtc_by_key[key][0]} and {i}")
                    rtc_by_key[key] = (i, rtc_item)
                except ValueError as e:
                    raise ValueError(f"[{path}[{i}]] {e}")
            
            # Determine what to remove, update, and add
            bl_keys = set(bl_index_by_key.keys())
            rtc_keys = set(rtc_by_key.keys())
            
            keys_to_remove = bl_keys - rtc_keys
            keys_to_update = bl_keys & rtc_keys
            keys_to_add = rtc_keys - bl_keys
            
            # Remove items (reverse order to preserve indices)
            indices_to_remove = sorted([bl_index_by_key[k] for k in keys_to_remove], reverse=True)
            for idx in indices_to_remove:
                print(f"[DEBUG] BL_EDIT: Removing unmatched item from {path} (Index {idx})")
                bl_collection.remove(idx)
            
            # Rebuild index map after removals
            bl_index_by_key_updated = {}
            for i, bl_item in enumerate(bl_collection):
                key = build_match_key(bl_item, match_fields)
                bl_index_by_key_updated[key] = i
            
            # Update existing items
            for key in keys_to_update:
                bl_idx = bl_index_by_key_updated[key]
                _, rtc_item = rtc_by_key[key]
                print(f"[DEBUG] BL_EDIT: Updating matched item at {path}[{bl_idx}] with key {key}")
                _sync_to_blender(bl_collection[bl_idx], rtc_item, f"{path}[{bl_idx}]")
            
            # Add new items
            for key in keys_to_add:
                _, rtc_item = rtc_by_key[key]
                print(f"[DEBUG] BL_EDIT: Adding new item to {path} with key {key}")
                bl_collection.add()
                new_idx = len(bl_collection) - 1
                _sync_to_blender(bl_collection[new_idx], rtc_item, f"{path}[{new_idx}]")

        # --------------------------------------------------------------
        # Entry point
        # --------------------------------------------------------------
        if blender_as_truth_source:
            _sync_to_blender(bl_propgroup_data, py_raw_data)
            return bl_propgroup_data
        else:
            return _sync_to_rtc(bl_propgroup_data, py_raw_data)

    @classmethod
    def is_registry_being_synced(cls, member_key: str):
        
        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        all_registries_being_synced = cls.get_instance(Core_Runtime_Cache_Members.META_REGISTRIES_BEING_SYNCED)
        if true_member_key in all_registries_being_synced:
            return True
        else:
            return False
        
    @classmethod
    def set_registry_sync_status(cls, member_key: str, is_actively_syncing: bool):

        true_member_key = get_actual_rtc_key(member_key, fail_gracefully = False)
        all_registries_being_synced = cls.get_instance(Core_Runtime_Cache_Members.META_REGISTRIES_BEING_SYNCED)
        if true_member_key in all_registries_being_synced and not is_actively_syncing:
            all_registries_being_synced.remove(true_member_key)
        elif true_member_key not in all_registries_being_synced and is_actively_syncing:
            all_registries_being_synced.append(true_member_key)

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

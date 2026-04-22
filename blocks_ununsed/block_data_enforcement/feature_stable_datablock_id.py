import bpy
import random
import string
import uuid


from ..blocks_natively_included._block_core.core_feature_logs import get_logger
from ..blocks_natively_included._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache
from .block_constants import Block_Runtime_Cache_Member_Definitions
from .block_config import my_filter_for_stable_id_assignment, my_stable_id_target_list
from .block_constants import Block_Logger_Definitions

#================================================================
# All Blender DataBlocks are bpy.types.* classes. 
# All are eligible to own a "stable-id" (bpy.props.StringProperty) value, which remains unchanged throughout the object's life 
# This class manages these logic for enforcing unique ID values
#   * Listeners for name-change events

#   * ID Strings can take 3 styles: Integers, Alphanumeric, & "correct horse battery stable"
# assigning, updating (upon ID conflict), and removal of

#================================================================


# --- Internal Cache Sync (Optimized) ---

def _sync_caches(stable_id, block_name):
    """
    Updates all string-based caches only if a change is detected.
    This prevents redundant writes to the global cache on every 'get' call.
    """
    # 1. Pull current state
    normal = Wrapper_Runtime_Cache.get_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS)
    inverted = Wrapper_Runtime_Cache.get_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS_INVERTED)
    
    needs_update = False

    # Check if the cache is already synchronized with this state
    if (normal.get(stable_id) != block_name or 
        inverted.get(block_name) != stable_id):
        
        normal[stable_id] = block_name
        inverted[block_name] = stable_id
        needs_update = True

    # 2. Only write back to global storage if a change actually occurred
    if needs_update:
        Wrapper_Runtime_Cache.set_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS, normal)
        Wrapper_Runtime_Cache.set_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS_INVERTED, inverted)
        
    return needs_update

# --- Core Logic ---

def generate_new_id():
    """Generates a random 32-bit integer string."""
    return str(random.randint(0, 2147483647))

def ensure_stable_id_is_unique(block, stable_id):
    """
    Checks if the given stable_id is already claimed by another bl_datablock of the same bpy.types.* class
    Returns the stable_id if safe, or a brand new one if a conflict is found.
    """
    normal = Wrapper_Runtime_Cache.get_instance(CACHE_KNOWN_OBJECT_IDS)
    
    # If the ID exists in cache but is registered to a DIFFERENT name
    if stable_id in normal and normal[stable_id] != block.name:
        # Before declaring a conflict, verify there's actually a DIFFERENT block with this ID
        # (The cache might just have a stale name due to a rename)
        cached_name = normal[stable_id]
        
        # Get the collection this block belongs to
        for cls in my_stable_id_target_list:
            if isinstance(block, cls):
                coll_attr = cls.__name__.lower() + "s"
                collection = getattr(bpy.data, coll_attr, None)
                # Check if another block in this collection has the cached name
                other_block = collection.get(cached_name)
                if other_block and other_block != block:
                    # True conflict: another block exists with the cached name
                    other_id = getattr(getattr(other_block, "dgblocks_object_stable_id_props", None), "stable_id", None)
                    if other_id == stable_id:
                        # Conflict detected! This block is likely a duplicate or appended data.
                        new_id = generate_new_id()
                        while new_id in normal:
                            new_id = generate_new_id()
                        
                        print(f"STABLE ID: Conflict detected for '{block.name}'. Generating new ID: {new_id}")
                        return new_id
                # No conflict - this is the same block, possibly renamed
                break
    
    return stable_id

def ensure_stable_id(bl_datablock):
    """Ensure the bl_datablock has a blender-file unique stable id.
    This assumes the filter function has already verified that this bl_datablock needs a stable id
    """
    
    if not bl_datablock: 
        return None
        
    props = getattr(bl_datablock, "dgblocks_object_stable_id_props", None)
    if not props: return None

    current_stable_id = props.stable_id
    
    # Check for empty string or conflicts
    if not current_stable_id:
        current_stable_id = generate_new_id()
        while current_stable_id in Wrapper_Runtime_Cache.get_instance(CACHE_KNOWN_OBJECT_IDS):
            current_stable_id = generate_new_id()
    else:
        # Validate that this ID isn't already owned by someone else
        current_stable_id = ensure_stable_id_is_unique(bl_datablock, current_stable_id)

    # Apply (or re-apply) the ID and sync
    props.stable_id = current_stable_id
    _sync_caches(current_stable_id, bl_datablock.name)
    
    return current_stable_id

# --- Event Handlers ---

def event_callback(context, depsgraph):
    
    context = bpy.context # Can't pass bpy.context directly in callback args because it's not a static object, it changes based on the current state.
    logger = get_logger(Block_Logger_Definitions.STABLE_ID)
    
    # Determine bl_datablock type (Object, Scene, Material...)
    coll_attr = type_name_str.lower() + "s"
    collection = getattr(bpy.data, coll_attr, None)
    if not collection: return
    
    # Get caches of known names & ids
    cached_bl_datablocks_dict = Wrapper_Runtime_Cache.get_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS, should_copy = True) # stable-id : name
    cached_bl_datablocks_dict_inverted = Wrapper_Runtime_Cache.get_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS_INVERTED, should_copy = True) # name : stable-id
    
    # Create Generator with a filter
    needs_processing = (
        bl_datablock for bl_datablock in collection
        if bl_datablock.name not in cached_bl_datablocks_dict_inverted
        and my_filter_for_stable_id_assignment(context, bl_datablock, logger))
    
    for bl_datablock in needs_processing:
                
        # ensure_stable_id handles: 
        # 1. ID Generation if missing
        # 2. Conflict resolution if ID is duplicated
        # 3. Cache sync if bl_datablock renamed (Stable ID remains unchanged)
        stable_id = ensure_stable_id(bl_datablock)
        if stable_id is None:
            continue
        
        # After ensure_stable_id, both cached_* dicts defined above may hold stale values
        
        # Check if a rename just happened 
        old_name = cached_bl_datablocks_dict.get(stable_id)
        print("checking", old_name, bl_datablock.name, stable_id)
        if old_name and bl_datablock.name != old_name:
            print(f"STABLE ID: {type_name_str} rename validated: {old_name} -> {bl_datablock.name}")

    # Note: _sync_caches within get_stable_id handles the writes to global cache.

def rebuild_full_cache():
    """Wipes and resyncs all tracked types, fixing duplicates and missing IDs."""
    # Start fresh to ensure we don't have dead names from previous files
    Wrapper_Runtime_Cache.set_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS, {})
    Wrapper_Runtime_Cache.set_instance(Block_Runtime_Cache_Member_Definitions.CACHE_KNOWN_OBJECT_IDS_INVERTED, {})

    for cls in my_stable_id_target_list:
        coll_attr = cls.__name__.lower() + "s"
        collection = getattr(bpy.data, coll_attr, [])
        for bl_datablock in collection:
            # This triggers generation and uniqueness validation
            ensure_stable_id(bl_datablock) 

    print("STABLE ID: Full cache rebuild and uniqueness check complete.")

# --- Lifecycle Management ---

def initialize_permanent_id_manager():
    
    destroy_permanent_id_manager()
    logger = get_logger(Block_Logger_Definitions.STABLE_ID)
   
    logger.info("Finished Stable ID Manager Initialized")

def destroy_permanent_id_manager():
    
    logger = get_logger(Block_Logger_Definitions.STABLE_ID)
   
    # logger.info("Finished Stable ID Manager Initialized")
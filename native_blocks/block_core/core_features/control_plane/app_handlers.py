
from bpy.app.handlers import persistent  # type: ignore
import bpy 

# Addon-level imports
from .....addon_helpers.data_structures import Enum_Sync_Events
from .....addon_helpers.generic_tools import is_bpy_ready

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID as core_block_id, Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks

# Aliases
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
enum_hook_undo = Core_Block_Hook_Sources.hook_core_event_undo
enum_hook_redo = Core_Block_Hook_Sources.hook_core_event_redo
# enum_hook_active_scene_changed = Core_Block_Hook_Sources.SCENE_MONITOR_ACTIVE_SCENE_CHANGED
# enum_hook_active_workspace_changed = Core_Block_Hook_Sources.SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED
# enum_hook_active_mode_changed = Core_Block_Hook_Sources.SCENE_MONITOR_ACTIVE_MODE_CHANGED
# enum_hook_active_obj_changed = Core_Block_Hook_Sources.SCENE_MONITOR_ACTIVE_OBJ_CHANGED



# --------------------------------------------------------------
# Post-load callbacks

def _delayed_callback_load_post():
    """
    Timer callback for deferred initialization.
    If not ready, returns 0.1 to retry in 0.1 seconds. Returns None when done.
    """
    if not is_bpy_ready():
        return 0.1  # Try again in 0.1 seconds
    
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    logger.debug(f"Calling core init logic from _delayed_callback_load_post")

    event = Enum_Sync_Events.ADDON_INIT
    _, self_FWC_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_FWCs, "feature_name", "Wrapper_Control_Plane")
    self_FWC_instance.actual_class.init_post_bpy()
    return None


@persistent
def _callback_load_post(dummy):
    """
    Persistent handler called on file load events.
    """
    if is_bpy_ready():
        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Calling core init logic from @persistent '_callback_load_post'")
        
        event = Enum_Sync_Events.ADDON_INIT
        _, self_FWC_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_FWCs, "feature_name", "Wrapper_Control_Plane")
        self_FWC_instance.actual_class.init_post_bpy()



# --------------------------------------------------------------
# Undo / redo callbacks

@persistent
def _callback_undo_post(dummy):
    """
    Called by Blender after an undo operation.
    Scene properties have reverted — rebuild RTC from them.
    """
    if not is_bpy_ready():
        return

    logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
    logger.debug("'Undo' event")

    # 1: FWCs with BL<->RTC data sync to process UNDO event first
    event = Enum_Sync_Events.PROPERTY_UPDATE_UNDO
    Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = True, logger = logger) 

    # 2: Blocks with UNDO hook subscription to process last
    _ = Wrapper_Hooks.run_hooked_funcs(hook_func_name=enum_hook_undo)


@persistent
def _callback_redo_post(dummy):
    """
    Called by Blender after a redo operation.
    Scene properties have changed — rebuild RTC from them.
    """
    if not is_bpy_ready():
        return
    logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
    logger.debug("'Redo' event")

    # 1: FWCs with BL<->RTC data sync to process REDO event first
    event = Enum_Sync_Events.PROPERTY_UPDATE_REDO
    Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = True, logger = logger) 

    # 2: Blocks with REDO hook subscription to process last
    _ = Wrapper_Hooks.run_hooked_funcs(hook_func_name=enum_hook_redo)

# --------------------------------------------------------------
# Depsgraph update callbacks — Scene Monitor

def _update_addon_state_trackers(scene):
    """
    Update all Global_Addon_State context trackers stored in ADDON_METADATA.
    Called once per depsgraph_update_post tick, after the early-return guard.
    """
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    metadata = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)

    try:
        ctx = bpy.context

        # CURRENT_SCENE_ID
        new_scene_id = (scene.name, scene.session_uid)
        if metadata.CURRENT_SCENE_ID != new_scene_id:
            old_id = metadata.CURRENT_SCENE_ID
            metadata.CURRENT_SCENE_ID = new_scene_id
            logger.debug(f"Active scene changed: {old_id} -> {new_scene_id}")
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=enum_hook_active_scene_changed,
                old_id=old_id,
                new_id=new_scene_id,
            )

        # CURRENT_WORKSPACE_ID
        ws = ctx.workspace
        new_ws_id = (ws.name, ws.session_uid) if ws else None
        if metadata.CURRENT_WORKSPACE_ID != new_ws_id:
            old_id = metadata.CURRENT_WORKSPACE_ID
            metadata.CURRENT_WORKSPACE_ID = new_ws_id
            logger.debug(f"Active workspace changed: {old_id} -> {new_ws_id}")
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=enum_hook_active_workspace_changed,
                old_id=old_id,
                new_id=new_ws_id,
            )

        # CURRENT_MODE
        if metadata.CURRENT_MODE != ctx.mode:
            old_id = metadata.CURRENT_MODE
            metadata.CURRENT_MODE = ctx.mode
            logger.debug(f"Active mode changed: {old_id} -> {ctx.mode}")
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=enum_hook_active_mode_changed,
                old_id=old_id,
                new_id=ctx.mode,
            )

        # CURRENT_ACTIVE_OBJ
        active_obj = ctx.active_object
        new_active_id = (active_obj.name, active_obj.session_uid) if active_obj else None
        if metadata.CURRENT_ACTIVE_OBJ != new_active_id:
            old_id = metadata.CURRENT_ACTIVE_OBJ
            metadata.CURRENT_ACTIVE_OBJ = new_active_id
            logger.debug(f"Active object changed: {old_id} -> {new_active_id}")
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=enum_hook_active_obj_changed,
                old_id=old_id,
                new_id=new_active_id,
            )

        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, metadata)

    except Exception:
        logger.error("Exception in _update_addon_state_trackers", exc_info=True)


def _reset_scene_monitor_state(scene_name: str):
    """
    Reset the scene monitor RTC state to defaults.
    """
    initial_state = {
        'current_scene': scene_name,
        'snapshots': {},
        'pointer_maps': {},
        'scene_objects': set(),
    }
    Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.SCENE_MONITOR_STATE, initial_state)


def _ensure_scene_monitor_state(scene_name: str):
    """
    Get or initialize the scene monitor state from RTC.
    Returns the state dict.
    """
    state = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.SCENE_MONITOR_STATE)
    if state is None or len(state) == 0:
        _reset_scene_monitor_state(scene_name)
        state = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.SCENE_MONITOR_STATE)
    return state


@persistent
def _callback_depsgraph_post(scene, depsgraph):

    ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
    if not (ADDON_METADATA.POST_REG_INIT_HAS_RUN and ADDON_METADATA.ADDON_STARTED_SUCCESSFULLY):
        return

    # _update_addon_state_trackers(scene)


# --------------------------------------------------------------
# Depsgraph update callbacks — Scene Monitor


def install_core_app_handler_callbacks(logger):
    
     # Add a handler for post-register init, if needed
    if _callback_load_post not in bpy.app.handlers.load_post:
        logger.debug(f"Func '_callback_load_post' added to 'bpy.app.handlers.load_post'")
        bpy.app.handlers.load_post.append(_callback_load_post)
    else:
        logger.debug(f"Func '_callback_load_post' already present in 'bpy.app.handlers.load_post'")

    # Add another post-load handler, but with a different trigger
    # It performs the same step as _callback_load_post, but for unsaved / new files
    bpy.app.timers.register(_delayed_callback_load_post, first_interval=0.0001)

    # Add post-undo & post-redo handlers, if needed
    if _callback_undo_post not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(_callback_undo_post)
        logger.debug("Func '_callback_undo_post' added to bpy.app.handlers.undo_post")
    else:
        logger.debug(f"Func '_callback_undo_post' already present in 'bpy.app.handlers.undo_post'")
    if _callback_redo_post not in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.append(_callback_redo_post)
        logger.debug("Func '_callback_redo_post' added to bpy.app.handlers.redo_post")
    else:
        logger.debug(f"Func '_callback_redo_post' already present in 'bpy.app.handlers.redo_post'")

    # Add a depsgraph listener
    if _callback_depsgraph_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_callback_depsgraph_post)
        logger.debug("Func '_callback_depsgraph_post' added to bpy.app.handlers.depsgraph_update_post")
    else:
        logger.debug(f"Func '_callback_depsgraph_post' already present in 'bpy.app.handlers.depsgraph_update_post'")

def remove_core_app_handler_callbacks(logger):
    
    # Remove scene monitor depsgraph handler
    if _callback_depsgraph_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_callback_depsgraph_post)
        logger.debug("Func '_callback_depsgraph_post' removed from 'bpy.app.handlers.depsgraph_update_post'")
    else:
        logger.debug("Func '_callback_depsgraph_post' not present in 'bpy.app.handlers.depsgraph_update_post'")

    if _callback_undo_post in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(_callback_undo_post)
        logger.debug("Func '_callback_undo_post' removed from 'bpy.app.handlers.undo_post'")
    else:
        logger.debug("Func '_callback_undo_post' not present in 'bpy.app.handlers.undo_post'")

    if _callback_redo_post in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(_callback_redo_post)
        logger.debug("Func '_callback_redo_post' removed from 'bpy.app.handlers.redo_post'")
    else:
        logger.debug("Func '_callback_redo_post' not present in 'bpy.app.handlers.redo_post'")

    if _callback_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_callback_load_post)
        logger.debug("Func '_callback_load_post' removed from 'bpy.app.handlers.load_post'")
    else:
        logger.debug("Func '_callback_load_post' not present in 'bpy.app.handlers.load_post'")

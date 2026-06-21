
from bpy.app.handlers import persistent  # type: ignore
import bpy

# Addon-level imports
from .....addon_helpers.data_structures import Enum_Sync_Events
from .....addon_helpers.generic_tools import is_bpy_ready

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks

# Aliases
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
cache_key_FWCs     = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
enum_hook_undo     = Core_Block_Hook_Sources.hook_core_event_undo
enum_hook_redo     = Core_Block_Hook_Sources.hook_core_event_redo


# --------------------------------------------------------------
# Post-load callbacks

def _delayed_callback_load_post():
    """
    Timer callback for deferred initialization.
    If not ready, returns 0.1 to retry in 0.1 seconds. Returns None when done.
    """
    if not is_bpy_ready():
        return 0.1

    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    logger.debug("Calling core init logic from _delayed_callback_load_post")

    _, self_FWC_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        cache_key_FWCs, "feature_name", "Wrapper_Control_Plane"
    )
    self_FWC_instance.actual_class.init_post_bpy()
    return None


@persistent
def _callback_load_post(dummy):
    """Persistent handler called on file load events."""
    if is_bpy_ready():
        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug("Calling core init logic from @persistent '_callback_load_post'")

        _, self_FWC_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            cache_key_FWCs, "feature_name", "Wrapper_Control_Plane"
        )
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

    event = Enum_Sync_Events.PROPERTY_UPDATE_UNDO
    Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source=True, logger=logger)
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

    event = Enum_Sync_Events.PROPERTY_UPDATE_REDO
    Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source=True, logger=logger)
    _ = Wrapper_Hooks.run_hooked_funcs(hook_func_name=enum_hook_redo)


# --------------------------------------------------------------
# Install / remove

def install_core_app_handler_callbacks(logger):

    if _callback_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_callback_load_post)
        logger.debug("Func '_callback_load_post' added to 'bpy.app.handlers.load_post'")
    else:
        logger.debug("Func '_callback_load_post' already present in 'bpy.app.handlers.load_post'")

    # Timer-based fallback for unsaved / new files (no load_post fires)
    bpy.app.timers.register(_delayed_callback_load_post, first_interval=0.0001)

    if _callback_undo_post not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(_callback_undo_post)
        logger.debug("Func '_callback_undo_post' added to 'bpy.app.handlers.undo_post'")
    else:
        logger.debug("Func '_callback_undo_post' already present in 'bpy.app.handlers.undo_post'")

    if _callback_redo_post not in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.append(_callback_redo_post)
        logger.debug("Func '_callback_redo_post' added to 'bpy.app.handlers.redo_post'")
    else:
        logger.debug("Func '_callback_redo_post' already present in 'bpy.app.handlers.redo_post'")


def remove_core_app_handler_callbacks(logger):

    if _callback_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_callback_load_post)
        logger.debug("Func '_callback_load_post' removed from 'bpy.app.handlers.load_post'")
    else:
        logger.debug("Func '_callback_load_post' not present in 'bpy.app.handlers.load_post'")

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

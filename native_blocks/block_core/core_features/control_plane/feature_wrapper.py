
from typing import Callable, Type
from types import ModuleType
from enum import Enum
import bpy # type: ignore
from bpy.app.handlers import persistent# type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, Enum_Sync_Actions, Global_Addon_State, RTC_FWC_Instance
from .....addon_helpers.data_tools import reset_propertygroup
from .....addon_helpers.generic_tools import is_bpy_ready, force_redraw_ui

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID as core_block_id, Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .helpers import register_and_init_block_components
from .app_handlers import  _callback_redo_post, _callback_undo_post, _callback_depsgraph_post
from .msgbus import clear_msgbuses, add_msgbuses, msgbus_subs

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
enum_hook_blocks_registered = Core_Block_Hook_Sources.hook_block_registered
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.hook_block_unregistered

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS

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
    self_FWC_instance.actual_class.init_post_bpy(event, self_FWC_instance)
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
        self_FWC_instance.actual_class.init_post_bpy(event, self_FWC_instance)

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS

class Wrapper_Control_Plane(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event, self_FWC_instance) -> bool:
        """
        Called during register() before bpy is fully available.
        """

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug("Running pre-bpy init for Wrapper_Control_Plane")

        # Write initial addon state to RTC. It will be updated again after init is finished
        initial_state = Global_Addon_State()
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, initial_state)

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
            logger.debug("Func  '_callback_redo_post' added to bpy.app.handlers.redo_post")
        else:
            logger.debug(f"Func '_callback_redo_post' already present in 'bpy.app.handlers.redo_post'")

        # Add a depsgraph listener
        if _callback_depsgraph_post not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_callback_depsgraph_post)
            logger.debug("Func  '_callback_depsgraph_post' added to bpy.app.handlers.depsgraph_update_post")
        else:
            logger.debug(f"Func '_callback_depsgraph_post' already present in 'bpy.app.handlers.depsgraph_update_post'")


    @classmethod
    def init_post_bpy(cls, event, self_FWC_instance) -> bool:
        """
        This function will only be called once for Blender's lifecycle, unless:
        * Opening New file
        * Uninstalling, then reinstalling the addon
        """

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug("Running post-bpy init for Wrapper_Control_Plane")

        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        if ADDON_METADATA.POST_REG_INIT_HAS_RUN:
            logger.info("Already completed post-bpy init for Wrapper_Control_Plane, returning early")
            return

        # (Debugging) clear all saved properties if needed
        core_props = bpy.context.scene.dgblocks_core_props
        if core_props.debug_mode_enabled and core_props.debug_clear_BL_data_on_startup:

            logger.warning("(Debugging) Clearing all saved properties")
            reset_propertygroup(core_props, clear_collections=True, reset_defaults=True, logger=logger)
            core_props.debug_log_all_RTC_BL_sync_actions = True
            core_props.debug_mode_enabled = True

        # ----------------------------------------------------------------------------------------------------------------------------
        # 1: initial BL<->RTC 2-way sync for this FWC
        # Because event = init, keeping user's saved block enabled/disabled settings if they exist 
        self_data_mirror_instance = self_FWC_instance.data_mirrors[0]
        Wrapper_Runtime_Cache.resync_single_data_mirror(event, self_FWC_instance,  self_data_mirror_instance, False, logger) # Causes partial RTC->BL sync
        Wrapper_Runtime_Cache.resync_single_data_mirror(event, self_FWC_instance,  self_data_mirror_instance, True, logger) # Causes full BL-RTC resync

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: run post_bpy_init() of all Feature Wrapper Classes, of all blocks
        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            if FWC_instance.actual_class == cls:  # Already inside init_post_bpy for this FWC, avoid recursion
                continue
            FWC_instance.actual_class.init_post_bpy(event, self_FWC_instance)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 3: Update addon metadata
        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        ADDON_METADATA.POST_REG_INIT_HAS_RUN = True
        ADDON_METADATA.ADDON_STARTED_SUCCESSFULLY = True
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, ADDON_METADATA)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 4: Run post-register initialization actions for all blocks with "hook_block_registered" function in their __init__.py
        logger.info(f"Running final-init hook for all subscriber Blocks")
        blocks_cache = Wrapper_Runtime_Cache.get_cache(cache_key_blocks, should_copy=True)
        kwargs = {"block_instances": blocks_cache}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=enum_hook_blocks_registered,
            should_halt_on_exception=False,
            **kwargs)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 5: Subscribe msgbus scene-change listener on all open windows
        clear_msgbuses(msgbus_subs)
        add_msgbuses(msgbus_subs)
        logger.info("msgbus scene-change listener registered")

        # ----------------------------------------------------------------------------------------------------------------------------
        # 6: refresh UI, finish init
        force_redraw_ui(bpy.context)
        logger.info(f"Finished all init actions. The Addon is ready to use")


    @classmethod
    def destroy_wrapper(cls, event, self_FWC_instance) -> bool:
        """
        Remove bpy.app.handlers and clear the sync registry.
        Called during core-block unregistration.
        """
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)

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

        # Remove msgbus scene-change listener
        clear_msgbuses(msgbus_subs)
        logger.debug("msgbus scene-change listener cleared")

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        block_module: ModuleType,
        block_bpy_types_classes: list[bpy.types] = [],
        block_feature_wrapper_classes: list[Abstract_Feature_Wrapper] = [],
        block_RTC_member_enums: list[Enum] = [],
        block_RTC_data_mirror_enums: list[Enum] = [],
        block_hook_source_enums: list[Enum] = [],
        block_logger_enums: list[Enum] = [],
    ):
        """
        Blocks are created during addon startup/refresh. They can also be removed/recreated during runtime
        """

        if None in [block_bpy_types_classes, block_feature_wrapper_classes, block_hook_source_enums, block_RTC_member_enums, block_logger_enums]:
            raise Exception("Arg lists may be empty, but not None")

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_module._BLOCK_ID
        logger.debug(f"Starting creation of block '{block_id}' instance")

        try:

            # Create Loggers, Hooks, FWCs, and RTC caches for the new block
            FWCs_to_skip_init = [f.__name__ for f in early_init_FWCs]
            register_and_init_block_components(
                event,
                block_module,
                block_bpy_types_classes,
                block_feature_wrapper_classes,
                block_RTC_member_enums,
                block_RTC_data_mirror_enums,
                block_hook_source_enums,
                block_logger_enums,
                FWCs_to_skip_init,
            )

            # If a block is being added during runtime (AKA after the registration cycle), trigger its post-bpy logic & final hook init here
            should_peform_final_init_steps_early = event in (Enum_Sync_Events.PROPERTY_UPDATE, Enum_Sync_Events.PROPERTY_UPDATE_REDO, Enum_Sync_Events.PROPERTY_UPDATE_UNDO)
            if should_peform_final_init_steps_early:

                # perform final init step for all FWCs of the block
                for FWC_instance in block_feature_wrapper_classes:
                    FWC_instance.actual_class.init_post_bpy(event, FWC_instance)

                # trigger final init hook, if needed
                try:
                    blocks_cache = Wrapper_Runtime_Cache.get_cache(cache_key_blocks, should_copy=True)
                    kwargs = {"block_instances": blocks_cache}
                    Wrapper_Hooks.run_hooked_funcs(
                        hook_func_name=enum_hook_blocks_registered,
                        subscriber_block_id=block_id,
                        **kwargs)
                except Exception as e:
                    logger.error(f"Exception occurred when propagating post-register init hook function", exc_info=True)

            logger.debug(f"Finished creation of block '{block_id}' instance")

        except:
            logger.error(f"Exception when creating {block_id} instance", exc_info=True)


    @classmethod
    def destroy_instance(cls, event, block_id: str):

        # Note that the Block record is not removed from RTC's REGISTRY_ALL_BLOCKS cache.
        # It is the only "trace" that should remain of a removed block.

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting removal of block '{block_id}'")

        idx, block_to_remove, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = cache_key_blocks,
            uniqueness_field = "block_id",
            uniqueness_field_value = block_id,
        )

        if block_to_remove is None:
            pass

        # 1: Unregister bpy classes
        for bpy_class in reversed(block_to_remove.block_bpy_types_classes):
            if bpy_class.is_registered:
                logger.debug(f"Unregistering BPY class '{bpy_class.__name__}'")
                bpy.utils.unregister_class(bpy_class)

        # 2: Remove FWCs. First call FWC-specific removal logic, then remove FWC from RTC. Only core-block skips this step.
        if block_id != core_block_id:
            for actual_class in reversed(block_to_remove.block_feature_wrapper_classes):
                feature_name = actual_class.__name__
                actual_class.destroy_wrapper(event, None)
                Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
                    member_key=cache_key_FWCs,
                    uniqueness_field="feature_name",
                    uniqueness_field_value=feature_name,
                )

        # 3: Delete the Block's Hooks, Loggers, and RTC Registries. Only sync to Blender on the last iteration
        for idx, hook_func_name in enumerate(reversed(block_to_remove.block_hook_source_names)):
            is_last = idx + 1 == len(block_to_remove.block_hook_source_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Hooks.destroy_instance(
                event,
                hook_func_name=hook_func_name,
                skip_BL_sync=is_shutdown or not is_last,
                skip_subscriber_cache_rebuild=is_shutdown or not is_last,
            )
        for idx, logger_name in enumerate(reversed(block_to_remove.block_logger_names)):
            is_last = idx + 1 == len(block_to_remove.block_logger_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Loggers.destroy_instance(
                event,
                logger_name=logger_name,
                skip_BL_sync=is_shutdown or not is_last,
            )
        for rtc_registry_name in reversed(block_to_remove.block_RTC_member_names):
            Wrapper_Runtime_Cache.remove_cache(rtc_registry_name)

        logger.info(f"Finished removal of block '{block_id}'")

    # ------------------------------------------------------------------
    # Funcs specific to this class
    # ------------------------------------------------------------------

    @classmethod
    def is_block_enabled(cls, block_id: str):

        block_instance = cls.get_block_instance(block_id)
        if block_instance is None:
            return False
        return block_instance.is_block_enabled


    @classmethod
    def get_block_instance(cls, block_id: str):

        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        block_instance = next((b for b in cached_blocks if b.block_id == block_id), None)
        return block_instance

# order matters
early_init_FWCs = [
    Wrapper_Runtime_Cache,
    Wrapper_Loggers,
    Wrapper_Control_Plane,
]

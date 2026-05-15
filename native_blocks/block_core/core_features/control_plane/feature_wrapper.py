
from typing import Callable, Type
from types import ModuleType
from enum import Enum
import bpy  # type: ignore
from bpy.app.handlers import persistent

# Addon-level imports
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, Enum_Sync_Actions, Global_Addon_State, RTC_FWC_Data_Mirror_List_Reference, RTC_FWC_Instance
from .....addon_helpers.data_tools import reset_propertygroup
from .....addon_helpers.generic_tools import is_bpy_ready, force_redraw_ui

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID as core_block_id, Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ...core_helpers.BL_RTC_data_sync_tools import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .data_structures import rtc_sync_key_fields, rtc_sync_data_fields
from .helpers import evaluate_and_update_block_statuses, init_and_register_block_components
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
    Wrapper_Control_Plane.init_post_bpy(event=Enum_Sync_Events.ADDON_INIT)
    return None


@persistent
def _callback_load_post(dummy):
    """
    Persistent handler called on file load events.
    """
    if is_bpy_ready():
        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Calling core init logic from @persistent '_callback_load_post'")
        Wrapper_Control_Plane.init_post_bpy(event=Enum_Sync_Events.ADDON_INIT)

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS

class Wrapper_Control_Plane(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
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
    def init_post_bpy(cls, event: Enum_Sync_Events, self_FWC_instance: type[RTC_FWC_Instance]) -> bool:
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
        # 0: Setup the data mirror for Block-management, then store it directly inside this class's parent FWC instance
        # self_data_mirror_instance = RTC_FWC_Data_Mirror_List_Reference(
        #     RTC_key = cache_key_blocks,
        #     sync_key_field_names = rtc_sync_key_fields, 
        #     sync_data_field_names = rtc_sync_data_fields,
        #     default_BL_scene_child_propertygroup_path = "dgblocks_core_props.managed_blocks"
        # )
        # self_FWC_instance.data_mirror_lists.append(self_data_mirror_instance)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 1: BL<->RTC 2-way sync, keeping user's saved block enabled/disabled settings if they exist
        cls.update_BL_with_mirrored_RTC_data(event=event)  # Causes partial RTC->BL sync
        cls.update_RTC_with_mirrored_BL_data(event=event)  # Causes full BL-RTC resync

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: run post_bpy_init() of all Feature Wrapper Classes, of all blocks
        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            if FWC_instance.actual_class == cls:  # Already inside init_post_bpy for this FWC, avoid recursion
                continue
            FWC_instance.actual_class.init_post_bpy(event=event)

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
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
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
            init_and_register_block_components(
                event,
                block_module,
                block_bpy_types_classes,
                block_feature_wrapper_classes,
                block_RTC_member_enums,
                block_RTC_data_mirror_enums,
                block_hook_source_enums,
                block_logger_enums,
            )

            # If a block is being added during runtime (AKA after the registration cycle), trigger its post-bpy logic & final hook init here
            should_peform_final_init_steps_early = event in (Enum_Sync_Events.PROPERTY_UPDATE, Enum_Sync_Events.PROPERTY_UPDATE_REDO, Enum_Sync_Events.PROPERTY_UPDATE_UNDO)
            if should_peform_final_init_steps_early:

                # perform final init step for all FWCs of the block
                for FWC_instance in block_feature_wrapper_classes:
                    FWC_instance.actual_class.init_post_bpy(event=event)

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
    def destroy_instance(cls, event: Enum_Sync_Events, block_id: str):

        # Note that the Block record is not removed from RTC's REGISTRY_ALL_BLOCKS cache.
        # It is the only "trace" that should remain of a removed block.

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting removal of block '{block_id}'")

        idx, block_to_remove, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key=cache_key_blocks,
            uniqueness_field="block_id",
            uniqueness_field_value=block_id,
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
                actual_class.destroy_wrapper(event=event)
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
                event=event,
                hook_func_name=hook_func_name,
                skip_BL_sync=is_shutdown or not is_last,
                skip_subscriber_cache_rebuild=is_shutdown or not is_last,
            )
        for idx, logger_name in enumerate(reversed(block_to_remove.block_logger_names)):
            is_last = idx + 1 == len(block_to_remove.block_logger_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Loggers.destroy_instance(
                event=event,
                logger_name=logger_name,
                skip_BL_sync=is_shutdown or not is_last,
            )
        for rtc_registry_name in reversed(block_to_remove.block_RTC_member_names):
            Wrapper_Runtime_Cache.remove_cache(rtc_registry_name)

        logger.info(f"Finished removal of block '{block_id}'")

    # ------------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # ------------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):

        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating block-mgmt RTC with mirrored Blender data")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        scene_blocks = core_props.managed_blocks

        # BL->RTC Sync
        update_dataclasses_to_match_collectionprop(
            actual_FWC=Wrapper_Control_Plane,
            source=scene_blocks,
            target=cached_blocks,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=set(),
            debug_logger=debug_logger,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):

        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating block-mgmt BL Data with mirrored RTC")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Sanity check before sync
        Wrapper_Runtime_Cache.asset_cache_is_not_syncing(cache_key_blocks, cls)

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        scene_blocks = core_props.managed_blocks

        # During init, allow add/move/remove but not edit. This allows user choices to be reloaded after save
        actions_denied = set()
        if event == Enum_Sync_Events.ADDON_INIT:
            actions_denied = {Enum_Sync_Actions.EDIT}

        # RTC->BL Sync
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, True)
        update_collectionprop_to_match_dataclasses(
            source=cached_blocks,
            target=scene_blocks,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=actions_denied,
            debug_logger=debug_logger,
        )
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, False)

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

    @classmethod
    def update_all_FWC_RTC_caches_to_match_BL_data(cls, event: Enum_Sync_Events) -> None:
        """
        Iterate through all registered Feature_Wrapper_References and call their
        update_RTC_with_mirrored_BL_data method.
        """

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting update_all_FWC_RTC_caches_to_match_BL_data for event='{event}'")

        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:

            # Ignore feature wrapper classes without BL<-->RTC sync capability
            if not FWC_instance.has_BL_mirrored_data:
                continue

            # Call sync function in class
            try:
                actual_class = FWC_instance.actual_class
                src_block_id = FWC_instance.src_block_id

                # Perform sync on self. That this should always be the first operation, because Wrapper_Control_Plane is always the first FWC in its cache
                if actual_class == cls:
                    evaluate_and_update_block_statuses(event, cls)
                    
                # Perform sync on all other syncable FWCs of all blocks
                else:
                    logger.debug(f"Updating RTC with BL data for '{actual_class.__name__}'")
                    actual_class.update_RTC_with_mirrored_BL_data(event)
                    
            except Exception:
                logger.error(f"Exception during RTC sync for '{src_block_id}'", exc_info=True)

        
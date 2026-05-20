
from dataclasses import dataclass, field
from typing import Callable, Type
from types import ModuleType
from enum import Enum
from .....addon_helpers.FWC_abstracts import Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager, Abstract_Feature_Wrapper
import bpy # type: ignore
from bpy.app.handlers import persistent# type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import Enum_Sync_Events, Enum_Sync_Actions, Global_Addon_State, RTC_FWC_Instance
from .....addon_helpers.data_tools import reset_propertygroup
from .....addon_helpers.generic_tools import is_bpy_ready, force_redraw_ui

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID as core_block_id, Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .helpers import _create_and_init_new_block_FWCs, _create_new_block_RTC_data_mirrors, _create_new_block_bpy_classes, _create_new_block_record, _create_new_block_standard_features, determine_blocks_to_update_status, install_block_components_into_RTC
from .app_handlers import  _callback_redo_post, _callback_undo_post, _callback_depsgraph_post, install_core_app_handler_callbacks, remove_core_app_handler_callbacks
from .msgbus import clear_msgbuses, add_msgbuses, msgbus_subs

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
enum_hook_blocks_registered = Core_Block_Hook_Sources.hook_block_registered
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.hook_block_unregistered

# ==============================================================================================================================
# INSTANCES MANAGED BY WRAPPER

@dataclass
class RTC_Block_Instance:
    # Record — instance state only, no manager logic

    block_id: str
    block_module: ModuleType
    block_dependencies: list[str]
    block_bpy_types_classes: list[bpy.types] = field(default_factory=list)
    block_FWC_instances: list[RTC_FWC_Instance] = field(default_factory=list)
    block_RTC_member_names: list[str] = field(default_factory=list)


# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS

class Wrapper_Control_Plane(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_wrapper(cls, event, self_FWC_instance) -> bool:
        """
        Called during register() before bpy is fully available.
        """

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug("Running pre-bpy init for Wrapper_Control_Plane")

        # Write initial addon state to RTC. It will be updated again after init is finished
        initial_state = Global_Addon_State()
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, initial_state)

        install_core_app_handler_callbacks(logger)


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

            logger.warning("(Debugging) Clearing all DGBLOCK saved properties")
            reset_propertygroup(core_props, clear_collections=True, reset_defaults=True, logger=logger)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: Load saved settings for all data mirrors into RTC , then perform 2 syncs. This ensures file-saved data is properly loaded alongside new RTC data
        logger.debug("Starting 2-way sync for all BL/RTC data mirrors")
        Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = False, logger = logger) 
        Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = True, logger = logger) 

        # ----------------------------------------------------------------------------------------------------------------------------
        # 3: run post_bpy_init() of all Feature Wrapper Classes, of all blocks
        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            if FWC_instance.actual_class == cls:  # Already inside init_post_bpy for this FWC, avoid recursion
                continue
            FWC_instance.actual_class.init_post_bpy(event, self_FWC_instance)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 4: Update addon metadata
        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        ADDON_METADATA.POST_REG_INIT_HAS_RUN = True
        ADDON_METADATA.ADDON_STARTED_SUCCESSFULLY = True
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, ADDON_METADATA)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 5: Subscribe msgbus scene-change listener on all open windows
        # clear_msgbuses(msgbus_subs)
        # add_msgbuses(msgbus_subs)
        # logger.info("msgbus scene-change listener registered")

        # ----------------------------------------------------------------------------------------------------------------------------
        # 6: Run post-register initialization actions for all blocks with "hook_block_registered" function in their __init__.py
        logger.info(f"Running final-init hook for all subscriber Blocks")
        blocks_cache = Wrapper_Runtime_Cache.get_cache(cache_key_blocks, should_copy=True)
        kwargs = {"block_instances": blocks_cache}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=enum_hook_blocks_registered,
            should_halt_on_exception=False,
            **kwargs)

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

        remove_core_app_handler_callbacks(logger)

        # Remove msgbus scene-change listener
        clear_msgbuses(msgbus_subs)
        logger.debug("msgbus scene-change listener cleared")

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(cls, block_declaration):
        """
        Blocks are created during addon startup/refresh. They can also be removed/recreated during runtime
        """

        # if None in [block_bpy_types_classes, block_feature_wrapper_classes, block_hook_source_enums, block_RTC_member_enums, block_logger_enums]:
        #     raise Exception("Arg lists may be empty, but not None")
        
        # if event != Enum_Sync_Events.ADDON_INIT:
        #     raise Exception("Arg lists may be empty, but not None")

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_declaration._BLOCK_ID
        logger.debug(f"Starting creation of block '{block_id}' instance")

        try:
            
            # 1: Register the new block's bpy.types.* classes into Blender's native registry
            _create_new_block_bpy_classes(block_declaration, logger)

            # 2: Register the new block's feature-wrapper classes
            new_FWC_instances = _create_and_init_new_block_FWCs(block_declaration, logger)

            # 3: Add block module to global block registry in RTC
            _create_new_block_record(block_declaration, new_FWC_instances, logger)

            # 4: Register the new block's RTC members, loggers, and hook sources. Only sync to Blender on the last iteration
            _create_new_block_standard_features(block_declaration, logger)

            # 5: Create data mirrors to link certain FWCs / RTC members / BL data
            _create_new_block_RTC_data_mirrors(block_declaration, logger)

            logger.debug(f"Finished creation of block '{block_id}' instance")

        except:
            logger.error(f"Exception when creating {block_id} instance", exc_info=True)


    @classmethod
    def destroy_instance(cls, event, block_id: str):

        # Note that the Block record itself is not removed from RTC's REGISTRY_ALL_BLOCKS cache. Instead, its 'is_block_enabled' property is set to false
        # It is the only "trace" that should remain of a removed block.

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting removal of block '{block_id}'")

        idx, block_to_disable, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = cache_key_blocks,
            uniqueness_field = "block_id",
            uniqueness_field_value = block_id,
        )

        if block_to_disable is None:
            pass

        # 1: Unregister bpy classes
        for bpy_class in reversed(block_to_disable.block_bpy_types_classes):
            if bpy_class.is_registered:
                logger.debug(f"Unregistering BPY class '{bpy_class.__name__}'")
                bpy.utils.unregister_class(bpy_class)

        # 2: Remove FWCs. First call FWC-specific removal logic, then remove FWC from RTC. Only core-block skips this step.
        if block_id != core_block_id:
            for actual_class in reversed(block_to_disable.block_FWC_instances):
                feature_name = actual_class.__name__
                actual_class.destroy_wrapper(event, None)
                Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
                    member_key=cache_key_FWCs,
                    uniqueness_field="feature_name",
                    uniqueness_field_value=feature_name,
                )

        # 3: Delete the Block's Hooks, Loggers, and RTC Registries. Only sync to Blender on the last iteration
        for idx, hook_func_name in enumerate(reversed(block_to_disable.block_hook_source_names)):
            is_last = idx + 1 == len(block_to_disable.block_hook_source_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Hooks.destroy_instance(
                event,
                hook_func_name=hook_func_name,
                skip_BL_sync=is_shutdown or not is_last,
                skip_subscriber_cache_rebuild=is_shutdown or not is_last,
            )
        for idx, logger_name in enumerate(reversed(block_to_disable.block_logger_names)):
            is_last = idx + 1 == len(block_to_disable.block_logger_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Loggers.destroy_instance(
                event,
                logger_name=logger_name,
                skip_BL_sync=is_shutdown or not is_last,
            )
        for rtc_registry_name in reversed(block_to_disable.block_RTC_member_names):
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

# Sample License, ignore for now

# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from abc import ABC
from dataclasses import dataclass
import inspect
from typing import Type
from types import ModuleType
from enum import Enum
from ....addon_helpers.ui_drawing_helpers import ui_draw_list_headers
import bpy  # type: ignore
from bpy.app.handlers import persistent  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_and_RTC_Data_Syncronizer, Enum_Sync_Events, Enum_Sync_Actions, Global_Addon_State
from ....addon_helpers.data_tools import fast_deepcopy_with_fallback, reset_propertygroup
from ....addon_helpers.generic_helpers import is_bpy_ready, force_redraw_ui, get_names_of_parent_classes

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ..core_helpers.constants import _BLOCK_ID as core_block_id, Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..core_helpers.helper_datasync import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from .feature_logs import Wrapper_Loggers, get_logger
from .feature_runtime_cache import Wrapper_Runtime_Cache
from .feature_hooks import Wrapper_Hooks

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
enum_hook_blocks_registered = Core_Block_Hook_Sources.CORE_EVENT_BLOCKS_REGISTERED
enum_hook_blocks_unregistered = Core_Block_Hook_Sources.CORE_EVENT_BLOCKS_UNREGISTERED
enum_hook_undo = Core_Block_Hook_Sources.CORE_EVENT_POST_UNDO
enum_hook_redo = Core_Block_Hook_Sources.CORE_EVENT_POST_REDO

# ==============================================================================================================================
# MIRRORED DATA FOR RTC & BLENDER
# ==============================================================================================================================

# --------------------------------------------------------------
# Blender data, stored in scene
# --------------------------------------------------------------

def _callback_update_block_enabled(self, context):

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key_blocks) or not is_bpy_ready():
        # print("skip block update")
        return
    
    try:

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        Wrapper_Block_Management.evaluate_and_update_block_statuses(event = Enum_Sync_Events.PROPERTY_UPDATE)

    except Exception:
        logger.error(f"Exception when updating 'enabled' status of blocks", exc_info = True)

    finally:

        # Reset sync status
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, False)

class DGBLOCKS_PG_Debug_Block_Reference(bpy.types.PropertyGroup):
    # RTC Mirror = 'REGISTRY_ALL_BLOCKS'
    # Used to toggle Blocks On/Off in Debug mode
    # Contains Block status, package location
    
    block_id: bpy.props.StringProperty(name="Block ID") # type: ignore
    should_block_be_enabled: bpy.props.BoolProperty(default = True, update = _callback_update_block_enabled) # type: ignore
    is_block_enabled: bpy.props.BoolProperty(default = True, update = _callback_update_block_enabled) # type: ignore
    is_block_valid: bpy.props.BoolProperty() # type: ignore
    is_block_dependencies_valid_and_enabled: bpy.props.BoolProperty() # type: ignore
    block_disabled_reason: bpy.props.StringProperty() # type: ignore

# --------------------------------------------------------------
# RTC data
# --------------------------------------------------------------

@dataclass
class RTC_Block_Instance:
    # Record — instance state only, no manager logic

    # Mirrored fields of DGBLOCKS_PG_Logger_Instance
    block_id: str
    should_block_be_enabled: bool
    is_block_enabled: bool
    is_block_valid: bool
    is_block_dependencies_valid_and_enabled: bool
    block_disabled_reason: str

    # Not present in mirror
    block_module: ModuleType
    block_dependencies: list[str]
    block_bpy_types_classes: list[bpy.types]
    block_feature_wrapper_classes: list[Abstract_Feature_Wrapper]
    block_hook_source_names: list[str]
    block_logger_names: list[str]
    block_RTC_member_names: list[str]

# Used during RTC <-> BL data sync
rtc_sync_key_fields = ["block_id"]
rtc_sync_data_fields = [
    "should_block_be_enabled",
    "is_block_enabled", 
    "is_block_valid", 
    "is_block_dependencies_valid_and_enabled",
    "block_disabled_reason",
]

# ==============================================================================================================================
# UNMIRRORED DATA
# ==============================================================================================================================

@dataclass
class RTC_FWC_Instance:
    """
    Record — instance state only, no manager logic
    This dataclass also stores the callable subscriber hook func.
    """

    src_block_id: str
    feature_name: str
    feature_wrapper_class: Abstract_Feature_Wrapper
    has_BL_mirrored_data: bool

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Block_Management(Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Datawrapper_Instance_Manager):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------
 
    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
        """
        Called during register() before bpy is fully available.
        """
        
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug("Running pre-bpy init for Wrapper_Block_Management")
        
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
        # It perform the same step as _callback_load_post, but for unsaved / new files
        # This callback will be continuously called until bpy.context is available. Unlike the other callbacks, it does not need to be removed upon unregister()
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

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:
        """
        This function will only be called once for Blender's lifecycle, unless:
        * Opening New file
        * Uninstalling, then reinstalling the addon
        """
        
        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug("Running post-bpy init for Wrapper_Block_Management")

        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        if ADDON_METADATA.POST_REG_INIT_HAS_RUN:
            logger.info("Already completed post-bpy init for Wrapper_Block_Management, returning early")
            return
        
        # (Debugging) clear all saved properties
        core_props = bpy.context.scene.dgblocks_core_props
        if True: #core_props.debug_mode_enabled and core_props.debug_clear_BL_data_on_startup:
            logger.warning("(Debugging) Clearing all saved properties")
            reset_propertygroup(core_props, clear_collections=True, reset_defaults=True, logger = logger)
        
        # 1: BL<->RTC 2-way sync, keeping user's saved block enabled/disabled settings if they exist
        cls.update_BL_with_mirrored_RTC_data(event = event) # Causes partial RTC->BL sync 
        cls.update_RTC_with_mirrored_BL_data(event = event) # Causes full BL-RTC resync

        # 2: run post_bpy_init() of all Feature Wrapper Classes, of all blocks. The order is deterministic, based on block/FWC list order
        # Some FWCs need to sync a feature's RTC data with its supporting Blender data using 'update_RTC_with_mirrored_BL_data' function
        # This sync action can happen either in 'post_bpy_init', or the post-bpy-init-hook function of the next step. Developer's preference
        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            if FWC_instance.feature_wrapper_class == cls: # Already inside init_post_bpy for this FWC, avoid recursion
                continue
            FWC_instance.feature_wrapper_class.init_post_bpy(event = event)

        # 3: Update addon metadata
        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        ADDON_METADATA.POST_REG_INIT_HAS_RUN = True
        ADDON_METADATA.ADDON_STARTED_SUCCESSFULLY = True
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, ADDON_METADATA)

        # Step 3: Run post-register initialization actions for all blocks with "hook_post_register_init" function in their __init__.py
        logger.info(f"Running final-init hook for all subscriber Blocks")
        blocks_cache = Wrapper_Runtime_Cache.get_cache(cache_key_blocks, should_copy = True)
        kwargs = {"block_instances": blocks_cache}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name = enum_hook_blocks_registered,
            should_halt_on_exception = False,
            **kwargs)
        
        force_redraw_ui(bpy.context)
        logger.info(f"Finished all init actions. The Addon is ready to use")
            
    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
        """
        Remove bpy.app.handlers and clear the sync registry.
        Called during core-block unregistration.
        """
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        # if logger is None:
        #     return

        if _callback_undo_post in bpy.app.handlers.undo_post:
            bpy.app.handlers.undo_post.remove(_callback_undo_post)
            logger.debug("Func '_callback_undo_post' removed from 'bpy.app.handlers.undo_post'")
        else:
            logger.debug("Func '_callback_undo_post' not present in 'bpy.app.handlers.undo_post'")

        if _callback_redo_post in bpy.app.handlers.redo_post:
            bpy.app.handlers.redo_post.remove(_callback_redo_post)
            logger.debug("Func '_callback_redo_post' removed from 'bpy.app.handlers.redo_post'")
        else:
            logger.debug("Func '_callback_undo_post' not present in 'bpy.app.handlers.undo_post'")
            
        if _callback_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_callback_load_post)
            logger.debug("Func '_callback_load_post' removed from 'bpy.app.handlers.load_post'")
        else:
            logger.debug("Func '_callback_load_post' not present in 'bpy.app.handlers.load_post'")

        # Clear the RTC of feature wrappers
        Wrapper_Runtime_Cache.set_cache(cache_key_FWCs, {})

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        block_module: ModuleType,
        block_bpy_types_classes: list[Type[Abstract_Feature_Wrapper]] = [],
        block_feature_wrapper_classes: list[Type[Abstract_Feature_Wrapper]] = [],
        block_hook_source_enums: list[Type[Enum]] = [],
        block_RTC_member_enums:list[Enum] = [],
        block_logger_enums:list[Enum] = [],
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
            cls.init_and_register_block_components(
                event,
                block_module,
                block_bpy_types_classes,
                block_feature_wrapper_classes,
                block_hook_source_enums,
                block_RTC_member_enums,
                block_logger_enums,
            )

            # If a block is being added during runtime, instead of created during startup, then the post-bpy (FWC scope) & final hook init (block scope) for are triggered here
            # Otherwise, they are handled in Wrapper_Block_Management.post_bpy_init
            should_peform_final_init_steps_early = event in (Enum_Sync_Events.PROPERTY_UPDATE, Enum_Sync_Events.PROPERTY_UPDATE_REDO, Enum_Sync_Events.PROPERTY_UPDATE_UNDO)
            if should_peform_final_init_steps_early:

                # perform final init step for all FWCs
                for FWC_instance in block_feature_wrapper_classes:
                    FWC_instance.feature_wrapper_class.init_post_bpy(event = event)

                # trigger final init hook for block, if needed
                try:
                    Wrapper_Hooks.run_hooked_funcs(hook_func_name = enum_hook_final_init, subscriber_block_id = block_id)
                except Exception as e:
                    logger.error(f"Exception occurred when propagating post-register init hook function", exc_info=True)

            logger.debug(f"Finished creation of block '{block_id}' instance")

        except:
            logger.error(f"Exception when creating {block_id} instance", exc_info = True)
            # cls.destroy_instance(block_id)

    @classmethod
    def destroy_instance(cls, event: Enum_Sync_Events, block_id: str):

        # Note that that Block record is not removed from RTC's REGISTRY_ALL_BLOCKS cache. It is the only "trace" that should remain of a removed block
        # When event != ADDON_SHUTDOWN, the block record needs to remain so that the enable/disable option remains for it.
        # And when event = ADDON_SHUTDOWN, the RTC is dumped anyway

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting removal of block '{block_id}'")

        idx, block_to_remove, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = cache_key_blocks, 
            uniqueness_field = "block_id", 
            uniqueness_field_value = block_id,
        )

        # 1: Unregister bpy classes
        for bpy_class in reversed(block_to_remove.block_bpy_types_classes):
            if bpy_class.is_registered:
                logger.debug(f"Unregistering BPY class '{bpy_class.__name__}'")
                bpy.utils.unregister_class(bpy_class)

        # 2: Remove FWCs. First call FWC-specific removal logic, then remove FWC from RTC. Only core-block skips this step.
        if block_id != core_block_id:
            for class_actual in reversed(block_to_remove.block_feature_wrapper_classes):
                feature_name= class_actual.__name__ # The feature's name = the feature's wrapper class name
                class_actual.destroy_wrapper(event = event)
                Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
                    member_key = cache_key_FWCs, 
                    uniqueness_field = "feature_name", 
                    uniqueness_field_value = feature_name,
                )

        # 3: Delete the Block's Hooks, Loggers, and RTC Registries first. Only Sync to Blender on the last iteration
        for idx, hook_func_name in enumerate(reversed(block_to_remove.block_hook_source_names)):
            is_last = idx + 1 == len(block_to_remove.block_hook_source_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Hooks.destroy_instance(
                event = event,
                hook_func_name = hook_func_name,
                skip_BL_sync = is_shutdown or not is_last, 
                skip_subscriber_cache_rebuild = is_shutdown or not is_last,
            )
        for idx, logger_name in enumerate(reversed(block_to_remove.block_logger_names)):
            is_last = idx + 1 == len(block_to_remove.block_logger_names)
            is_shutdown = event == Enum_Sync_Events.ADDON_SHUTDOWN
            Wrapper_Loggers.destroy_instance(
                event = event,
                logger_name = logger_name, 
                skip_BL_sync = is_shutdown or not is_last, 
            )
        for rtc_registry_name in reversed(block_to_remove.block_RTC_member_names):
            Wrapper_Runtime_Cache.remove_cache(rtc_registry_name)

        logger.info(f"Finished removal of block '{block_id}'")

    # ------------------------------------------------------------------
    #  Implemented from Abstract_BL_and_RTC_Data_Syncronizer
    # ------------------------------------------------------------------
    
    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):

        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.DATA_SYNC)
        logger.debug(f"Updating block-mgmt RTC with mirrored Blender data")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None
        
        # Get mirrored BL/RTC data (potentially de-synced)
        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        scene_blocks = core_props.managed_blocks
        
        # BL->RTC Sync
        update_dataclasses_to_match_collectionprop(
            actual_FWC = Wrapper_Block_Management,
            source = scene_blocks,
            target = cached_blocks,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields,
            actions_denied = set(), # Block-manager's BL->RTC sync will never need to skip actions
            debug_logger = debug_logger,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):

        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.DATA_SYNC)
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
            source = cached_blocks,
            target = scene_blocks,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields,
            actions_denied = actions_denied,
            debug_logger = debug_logger,
        )
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_blocks, False)

    # ------------------------------------------------------------------
    # Funcs specific to this class
    # ------------------------------------------------------------------

    @classmethod
    def validate_block_list_before_registration(cls, blocks_to_register:list[any], ) -> tuple[list[any], list[str]]:
    
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        
        # A list of variables and functions names, required in a block's __init__.py
        required_in_block = ["_BLOCK_DEPENDENCIES", "_BLOCK_VERSION", "_BLOCK_ID", "register_block", "unregister_block"]
        valid_blocks = []
        valid_block_names = []
        for block_main_file in blocks_to_register:
            
            # Validate block contents
            should_skip_package = False
            for required_ in required_in_block:
                if not hasattr(block_main_file, required_):
                    file_dunder_name = block_main_file.__name__ # I learned a new word today
                    logger.error(f"Could not register {file_dunder_name} as a Block. Its __init__.py is missing a required variable/function: '{required_}'")
                    should_skip_package = True
            if should_skip_package:
                continue
            
            # Validate block ID uniqueness
            block_id = getattr(block_main_file, "_BLOCK_ID")
            if block_id in valid_block_names:
                logger.error(f"Block with ID {block_id} is already registered")
                continue
                
            # Validate installation of other blocks that the current depends on
            block_deps = getattr(block_main_file, "_BLOCK_DEPENDENCIES")
            for dependent_block_id in block_deps:
                if dependent_block_id not in valid_block_names:
                    logger.error(f"Block {block_id} depends on {dependent_block_id}, but it is not registered")
                    logger.error(f"All registered blocks: [ {', '.join(valid_block_names)} ]")
                    should_skip_package = True
            if should_skip_package:
                continue
            
            valid_blocks.append(block_main_file)
            valid_block_names.append(block_id)
            logger.debug(f"{block_id} passes pre-register validation")
        
        return valid_blocks

    @classmethod
    def determine_FWC_missing_abstract_funcs(cls, feature_wrapper_class: type) -> list[str]:

        # Collect all ABC bases (excluding the class itself and object)
        abc_bases = [
            base for base in inspect.getmro(feature_wrapper_class)
            if base not in (feature_wrapper_class, object) and issubclass(base, ABC)
        ]

        # Collect all abstract method names defined in those bases
        abstract_methods = {
            name
            for base in abc_bases
            for name, member in vars(base).items()
            if getattr(member, "__isabstractmethod__", False)
        }

        # Filter to methods not concretely implemented as a classmethod on cls
        return [
            name for name in abstract_methods
            if not (
                isinstance(vars(feature_wrapper_class).get(name), classmethod)
                and not getattr(vars(feature_wrapper_class).get(name), "__isabstractmethod__", False)
            )
        ]

    @classmethod
    def init_and_register_block_components(
        cls,
        event,
        block_module,
        block_bpy_types_classes,
        block_feature_wrapper_classes,
        block_hook_source_enums,
        block_RTC_member_enums,
        block_logger_enums,
    ):
        
        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        block_id = block_module._BLOCK_ID
        block_dependencies = block_module._BLOCK_DEPENDENCIES

        # ----------------------------------------------------------------------------------------------------------------------------
        # 1: Register the new block's bpy.types.* classes into Blender's native registry
        for bpy_class in block_bpy_types_classes:
            if bpy_class.is_registered:
                logger.debug(f"class {str(bpy_class)} is already registered")
            else:
                logger.debug(f"Registering BPY class '{bpy_class.__name__}'")
                bpy.utils.register_class(bpy_class)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: Register the new block's feature-wrapper classes

        # For core-block, these FWCs were already init'd in main addon register(). 'Wrapper_Hooks' is the only one needing init
        core_FWC_already_init = [cls, Wrapper_Loggers, Wrapper_Runtime_Cache] 
        for class_actual in block_feature_wrapper_classes:
            feature_name = class_actual.__name__ # The feature's name = the feature's wrapper class name

            # Validate presence of required abstract func implementations of wrapper classes
            if class_actual not in core_FWC_already_init:
                missing_abstract_funcs = cls.determine_FWC_missing_abstract_funcs(class_actual)
                if len(missing_abstract_funcs) > 0:
                    missing_func_str = "'" + "', '".join(missing_abstract_funcs) + "'"
                    raise Exception(f"Feature Wrapper Class {class_actual} is missing required class functions: {missing_func_str}")
                class_actual.init_pre_bpy(event = event)

            # Determine if the FWC will need BL<->RTC data sync actions
            has_BL_mirrored_data = False
            all_parent_classes = get_names_of_parent_classes(class_actual)
            if Abstract_BL_and_RTC_Data_Syncronizer.__name__ in all_parent_classes:
                has_BL_mirrored_data = True
            
            # Validate FWC uniqueness
            idx, FWC_instance, cached_FWCs_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
                member_key = cache_key_FWCs, 
                uniqueness_field = "feature_name", 
                uniqueness_field_value = feature_name,
            )
            if FWC_instance:
                logger.debug(f"FWC '{feature_name}' already exists in RTC. Skipping duplication")
                continue

            # Create & cache a new FWC instance
            FWC_instance = RTC_FWC_Instance(
                src_block_id = block_id,
                feature_name = class_actual.__name__,
                feature_wrapper_class = class_actual,
                has_BL_mirrored_data = has_BL_mirrored_data
            )
            cached_FWCs_list.append(FWC_instance)
            Wrapper_Runtime_Cache.set_cache(cache_key_FWCs, cached_FWCs_list)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 3: Add block module to global block registry in RTC
        # This structure partially mirrors DGBLOCKS_PG_Debug_Block_Reference. Only the first 3 fields exist in the BL Data
        idx, block_instance, cached_blocks_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = cache_key_blocks, 
            uniqueness_field = "block_id", 
            uniqueness_field_value = block_id,
        )
        if block_instance:
            logger.info(f"Block '{block_id}' record already exists in RTC REGISTRY_ALL_BLOCKS. Continuing with other RTC members")
        else:
            block_instance = RTC_Block_Instance(
                block_id,
                block_disabled_reason = "",
                should_block_be_enabled = True,
                is_block_enabled = True,
                is_block_valid = True,
                is_block_dependencies_valid_and_enabled = True,
                block_module = block_module,
                block_dependencies = block_dependencies,
                block_bpy_types_classes = block_bpy_types_classes,
                block_feature_wrapper_classes = block_feature_wrapper_classes,
                block_hook_source_names = [h.value[0] for h in block_hook_source_enums],
                block_logger_names = [l.name for l in block_logger_enums],
                block_RTC_member_names = [m.name for m in block_RTC_member_enums],
            )
            cached_blocks_list.append(block_instance)
            Wrapper_Runtime_Cache.set_cache(cache_key_blocks, cached_blocks_list)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 4: Register the new block's RTC members, loggers, and hook sources. Only Sync to Blender on the last iteration

        # RTC Registries - initialized with empty data containers, commonly an dict or list
        for enum_cache_key in block_RTC_member_enums:
            Wrapper_Runtime_Cache.create_cache(
                new_key = enum_cache_key.name, 
                new_value = fast_deepcopy_with_fallback(enum_cache_key.value[1]),
            )

        # Loggers - initialized with default log levels
        for idx, enum_logger in enumerate(block_logger_enums):
            is_last = idx + 1 == len(block_logger_enums)
            Wrapper_Loggers.create_instance(
                event,
                src_block_id = block_id,
                logger_name = enum_logger.name,
                level_name = enum_logger.value[1],
                skip_BL_sync = not is_last,
            )

        # Hooks Sources - remain unchanged after init. Only Downstreams (derived later, from sources) can be changed
        for idx, enum_hook in enumerate(block_hook_source_enums):
            is_last = idx + 1 == len(block_hook_source_enums)
            Wrapper_Hooks.create_instance(
                event,
                src_block_id = block_id,
                new_hook_func_id = enum_hook.value[0],
                new_hook_func_named_args = enum_hook.value[1],
                skip_BL_sync = not is_last, 
                skip_subscriber_cache_rebuild = not is_last,
            )

    @classmethod
    def determine_blocks_to_update_status(
        cls,
        cached_blocks: list[RTC_Block_Instance],
    ) -> tuple[list[RTC_Block_Instance], list[str], list[str]]:

        prior_statuses = {b.block_id: b.is_block_enabled for b in cached_blocks}
        block_map = {n.block_id: n for n in cached_blocks}

        # Build reverse dependency graph
        dependents: dict[str, list[str]] = {n.block_id: [] for n in cached_blocks}
        for node in cached_blocks:
            for dep_id in node.block_dependencies:
                if dep_id in dependents:
                    dependents[dep_id].append(node.block_id)

        # Evaluate each block's own state
        for node in cached_blocks:
            node.is_block_dependencies_valid_and_enabled = True
            if not node.should_block_be_enabled:
                node.block_disabled_reason = "self is disabled"
                node.is_block_enabled = False
            elif not node.is_block_valid:
                node.block_disabled_reason = "self is invalid"
                node.is_block_enabled = False
            else:
                node.block_disabled_reason = ""
                node.is_block_enabled = True

        # BFS: propagate disabled/invalid states to dependents
        queue = [n.block_id for n in cached_blocks if not n.is_block_enabled]
        visited = set(queue)
        while queue:
            current_id = queue.pop(0)
            current = block_map[current_id]

            for dep_id in dependents[current_id]:
                dependent = block_map[dep_id]
                if dependent.is_block_dependencies_valid_and_enabled:
                    dependent.is_block_dependencies_valid_and_enabled = False
                    if dependent.should_block_be_enabled and dependent.is_block_valid:
                        dependent.block_disabled_reason = f"dependency '{current_id}' is disabled or invalid"
                        dependent.is_block_enabled = False
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)

        was_enabled  = [b for b in cached_blocks if b.is_block_enabled  and not prior_statuses[b.block_id]]
        was_disabled = [b for b in cached_blocks if not b.is_block_enabled and prior_statuses[b.block_id]]

        return was_enabled, was_disabled

    @classmethod
    def evaluate_and_update_block_statuses(cls, event):

        # Update RTC to match Blender/UI
        Wrapper_Block_Management.update_RTC_with_mirrored_BL_data(event)

        # Update enabled/disabled status for all block instances, depending on the status of their dependencies
        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        blocks_to_enable, blocks_to_disable = Wrapper_Block_Management.determine_blocks_to_update_status(cached_blocks)

        for block in blocks_to_enable:
            block.block_module.register_block(event)

        for block in blocks_to_disable:
            block.block_module.unregister_block(event)

        # Apply changes back to mirrored Blender data
        Wrapper_Block_Management.update_BL_with_mirrored_RTC_data(Enum_Sync_Events.PROPERTY_UPDATE)
        
        # Final step, Run hook to notify subscribers of block registration/unregistration
        if len(blocks_to_enable) > 0:
            kwargs = {"block_instances": blocks_to_enable}
            _ = Wrapper_Hooks.run_hooked_funcs(
                hook_func_name = enum_hook_blocks_registered,
                should_halt_on_exception = False,
                **kwargs)
        if len(blocks_to_disable) > 0:
            kwargs = {"block_instances": blocks_to_disable}
            _ = Wrapper_Hooks.run_hooked_funcs(
                hook_func_name = enum_hook_blocks_unregistered,
                should_halt_on_exception = False,
                **kwargs)

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
        update_RTC_with_mirrored_BL_data(scene) method.
        
        Args:
            scene:      The current bpy.types.Scene
            event_type: One of "undo", "redo", "load" — used for toggle checking and logging
        """
        
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Starting update_all_FWC_RTC_caches_to_match_BL_data for event='{event}'")
        
        cache_all_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cache_all_FWCs:

            # Ignore feature wrapper classes without BL<-->RTC sync capability
            if not FWC_instance.has_BL_mirrored_data:
                continue

            # Call sync function in class
            try:
                actual_class_ref = FWC_instance.feature_wrapper_class
                src_block_id = FWC_instance.src_block_id

                if actual_class_ref == cls:
                    cls.evaluate_and_update_block_statuses(event)

                else:
                    logger.debug(f"Updating RTC with BL data for '{actual_class_ref.__name__}'")
                    actual_class_ref.update_RTC_with_mirrored_BL_data(event)
            except Exception:
                logger.error(f"Exception during RTC sync for '{src_block_id}'", exc_info=True)

# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Name", "Should Enable?", "Is Enabled?")
col_widths = (2, 1, 1)

def _uilayout_draw_block_uilist_selection_detail(context, container):
    
    # Show disabled reason for selected alert row
    core_props = context.scene.dgblocks_core_props
    is_anything_selected = 0 <= core_props.managed_blocks_selected_idx < len(core_props.managed_blocks)
    if core_props.managed_blocks and is_anything_selected:
        active_block = core_props.managed_blocks[core_props.managed_blocks_selected_idx]
        is_alert = active_block.should_block_be_enabled and not active_block.is_block_enabled
        if is_alert and active_block.block_disabled_reason:
            box = container.box()
            box.alert = True
            box.label(text=f"Reason: {active_block.block_disabled_reason}", icon='INFO')

def _uilayout_draw_block_manager_settings(context, container):

    box = container.box()
    core_props = context.scene.dgblocks_core_props
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_block_mgmt", default_closed=True)
    panel_header.label(text = f"All Blocks ({len(context.scene.dgblocks_core_props.managed_blocks)})")
    if panel_body is not None:        

        # Draw column headers - should match draw_item layout exactly
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw the UIList
        row = panel_body.row()
        row_count = len(core_props.managed_blocks)
        row.template_list(
            "DGBLOCKS_UL_Blocks",
            "",
            core_props, "managed_blocks", # Collection property
            core_props, "managed_blocks_selected_idx", # Active index property
            rows = row_count,
            maxrows = row_count,
            columns = row_count, 
        )
        
        # Show disabled reason for selected alert row
        _uilayout_draw_block_uilist_selection_detail(context, container)

class DGBLOCKS_UL_Blocks(bpy.types.UIList):
    """UIList to display RTC blocks with enable toggle and alert states."""
    
    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
       
        is_alert = item.should_block_be_enabled and not item.is_block_enabled
        if is_alert:
            container.alert = True
        row = container.row()
        row.enabled = item.block_id != core_block_id # Prevent core block from being disabled

        # Block name
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.block_id)
        
        # Should enable toggle
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.prop(item, "should_block_be_enabled", text="", icon='CHECKBOX_HLT' if item.should_block_be_enabled else 'CHECKBOX_DEHLT')
        
        # Is enabled status
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.label(text="", icon='CHECKMARK' if item.is_block_enabled else 'X')

# ==============================================================================================================================
# PRIVATE API — init/load/undo/redo callbacks 
# ==============================================================================================================================

def _delayed_callback_load_post():
    """
    Timer callback for deferred initialization.
    
    This function & _callback_load_post will execute in different order 
    for different load situations.
    
    If this function returns a number, it will be called again in that many seconds.
    If None is returned, this function is not called again.
    
    Initialization tasks can't be performed until bpy is fully available.
    If not ready, wait until the next call.
    """
    if not is_bpy_ready():
        return 0.1  # Try again in 0.1 seconds
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    logger.debug(f"Calling core init logic from _delayed_callback_load_post")
    Wrapper_Block_Management.init_post_bpy(event = Enum_Sync_Events.ADDON_INIT)

    # Always return None after first attempt. If initialization fails, do not try again
    return None 

@persistent
def _callback_load_post(dummy):
    """
    Persistent handler called on file load events.
    
    This function & _delayed_callback_load_post will execute in different order 
    for different load situations.
    """

    if is_bpy_ready():
        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Calling core init logic from @persistent '_callback_load_post'")
        Wrapper_Block_Management.init_post_bpy(event = Enum_Sync_Events.ADDON_INIT)

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
    Wrapper_Block_Management.update_all_FWC_RTC_caches_to_match_BL_data(Enum_Sync_Events.PROPERTY_UPDATE_UNDO)

    # 2: Blocks with UNDO hook subscription to process last
    _ = Wrapper_Hooks.run_hooked_funcs(hook_func_name = enum_hook_undo)

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
    Wrapper_Block_Management.update_all_FWC_RTC_caches_to_match_BL_data(Enum_Sync_Events.PROPERTY_UPDATE_REDO)

    # 2: Blocks with UNDO hook subscription to process last
    _ = Wrapper_Hooks.run_hooked_funcs(hook_func_name = enum_hook_redo)

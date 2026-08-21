
import traceback
from types import ModuleType
import bpy # type: ignore

# Addon-level imports
from .....addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events, Global_Addon_State, Abstract_Datawrapper_Instance_Manager, Abstract_Feature_Wrapper

from .....addon_helpers.data_tools import reset_propertygroup
from .....addon_helpers.generic_tools import force_redraw_ui, get_folder_parts

# Intra-block imports
from ...core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import Wrapper_Loggers, get_logger
from ..hooks.feature_wrapper import Wrapper_Hooks
from .data_structures import RTC_Block_Instance
from .helpers import _create_and_init_new_block_FWCs, _create_new_block_RTC_data_mirrors, _create_new_block_bpy_classes, _create_new_block_properties, _create_new_block_record, _create_new_block_shared_UILists, _create_new_block_standard_features, _remove_block_FWC_instances, _remove_block_bpy_classes, _remove_block_properties, reset_reload_flag_if_needed, shallow_validate_block_declaration, shallow_validate_block_module
from .app_handlers import install_core_app_handler_callbacks, remove_core_app_handler_callbacks
from .msgbus import add_msgbuses, clear_msgbuses, msgbus_subs

# Aliases
cache_key_FWCs = Core_Runtime_Cache_Members.REGISTRY_ALL_FWCS
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_metadata = Core_Runtime_Cache_Members.ADDON_METADATA
enum_hook_post_startup = Core_Block_Hook_Sources.hook_post_startup

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS

# The blocks list uses the framework's DEFAULT two-way mirror sync (see Core_Data_Mirrors.BLOCKS_LIST),
# so Abstract_BL_RTC_List_Syncronizer is deliberately NOT inherited here
class Wrapper_Control_Plane(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):


    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def _init_wrapper(cls) -> bool:
        """
        Called during register() before bpy is fully available.
        """

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug("Running pre-bpy init for Wrapper_Control_Plane")

        # Write initial addon state to RTC. It will be updated again after init is finished
        initial_state = Global_Addon_State()
        Wrapper_Runtime_Cache.set_cache(cache_key_metadata, initial_state)

        install_core_app_handler_callbacks(logger)

        # Setup UIList for Debug Panel
        # set_shared_uilist_config(
        #     list_id="BLOCKS_LIST",
        #     col_names=("Valid", "Block ID"),
        #     col_widths=(1, 4),
        #     columns_def=[
        #         {"type": "ICON", "field": "is_valid", "icon_true": "CHECKMARK", "icon_false": "ERROR"},
        #         {"type": "LABEL", "field": "block_id"},
        #     ],
        #     details_func=_uilayout_draw_blocks_uilist_selection_detail
        # )


    @classmethod
    def init_post_bpy(cls) -> bool:
        """
        This function will only be called once for Blender's lifecycle, unless:
        * Opening New file
        * Uninstalling, then reinstalling the addon
        """

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug("Running post-bpy init for Wrapper_Control_Plane")

        ADDON_METADATA = Wrapper_Runtime_Cache.get_cache(cache_key_metadata)
        if ADDON_METADATA.POST_REG_INIT_HAS_RUN:
            # The first init may have fired before the .blend file was loaded
            # (timer-based fallback). User-saved settings such as logger levels
            # must be loaded into RTC now that the real file data is available.
            logger.info("Already completed post-bpy init — re-running mirror sync to load saved data")

            # Same 2-pass order as a cold start. The RTC→BL pass only aligns structure
            # (ADDON_INIT denies Edit actions), so rows saved in the newly opened .blend keep their
            # values and the BL→RTC pass can then load them. Without it, a file saved against a
            # different set of blocks would feed stale rows into the BL→RTC diff
            event = Enum_Sync_Events.ADDON_INIT
            Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source=False, logger=logger)
            Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source=True, logger=logger)


            # Apply the saved "Include Datetime" choice to formatters
            try:
                desired_dt = bpy.context.scene.dgblocks_core_props.logger_include_datetime
            except Exception:
                desired_dt = "NONE"
            Wrapper_Loggers.update_logger_formatters(desired_dt)

            # File-load initialization is a real post-startup lifecycle pass too. Re-fire the
            # final-init hook after the newly loaded Scene data has been mirrored so resources
            # that Blender does not preserve across files (notably modal operators) can restart.
            logger.info("Re-running final-init hooks after file load")
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=enum_hook_post_startup,
                should_halt_on_exception=False,
            )
            force_redraw_ui(bpy.context)
            return

        # 0: (Debugging) clear all saved properties if needed
        core_props = bpy.context.scene.dgblocks_core_props
        core_block_instance = cls.get_block_instance("block-core")
        core_block_debug_mode = core_block_instance.debug_mode_enabled if core_block_instance else False
        if core_block_debug_mode and core_props.debug_clear_BL_data_on_startup:
            logger.warning("(Debugging) Clearing all DGBLOCK saved properties")
            reset_propertygroup(core_props, clear_collections=True, reset_defaults=True, logger=logger)

        # 1: Create & cache hook-subscription instances for all hook sources
        Wrapper_Hooks.rebuild_hook_subs_cache()

        # ----------------------------------------------------------------------------------------------------------------------------
        # 2: initialize all Feature Wrapper Classes, of all blocks (except block-core, which was initialized during addon register)
        core_FWCs = (cls, Wrapper_Runtime_Cache, Wrapper_Hooks, Wrapper_Loggers)
        cached_FWCs = Wrapper_Runtime_Cache.get_cache(cache_key_FWCs)
        for FWC_instance in cached_FWCs:
            if FWC_instance.actual_class in core_FWCs:
                continue
            FWC_instance.actual_class._init_wrapper()

        # ----------------------------------------------------------------------------------------------------------------------------
        # 3: Load saved settings for all data mirrors into RTC , then perform 2 syncs. This ensures file-saved data is properly loaded alongside new RTC data
        logger.debug("Starting 2-way sync for all BL/RTC data mirrors")
        event = Enum_Sync_Events.ADDON_INIT
        Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = False, logger = logger) 
        Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = True, logger = logger) 

        # Apply the saved "Include Datetime" choice (from the All Loggers panel) to all logger formatters
        try:
            desired_dt = bpy.context.scene.dgblocks_core_props.logger_include_datetime
        except Exception:
            desired_dt = "NONE"
        Wrapper_Loggers.update_logger_formatters(desired_dt)

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
        logger.info("msgbus scene-change listener registered")

        # ----------------------------------------------------------------------------------------------------------------------------
        # 6: Run post-register initialization actions for all blocks with "hook_post_startup" function in their __init__.py
        logger.info(f"Running final-init hook for all subscriber Blocks")
        blocks_cache = Wrapper_Runtime_Cache.get_cache(cache_key_blocks, should_copy=True)
        kwargs = {}
        _ = Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=enum_hook_post_startup,
            should_halt_on_exception=False,
            **kwargs)

        # ----------------------------------------------------------------------------------------------------------------------------
        # 6: Reset reload-flag, call did-reset hook if needed refresh UI
        all_surviving_block_data = reset_reload_flag_if_needed(blocks_cache)
        if all_surviving_block_data:
            for block_id, block_data in all_surviving_block_data.items():
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name=Core_Block_Hook_Sources.hook_after_blocks_reload, 
                    subscriber_block_id = block_id,
                    surviving_data = block_data)
        else:
            logger.info(f"Finished all init actions. The Addon is ready to use")
        force_redraw_ui(bpy.context)
        

    @classmethod
    def _remove_wrapper(cls) -> bool:
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
    def _create_instance(cls, event: Enum_Sync_Events, block_module: ModuleType = None, **mirrored_fields):
        """
        Blocks are created during addon startup/refresh. They can also be removed/recreated during runtime
        """

        logger = get_logger(Core_Block_Loggers.REGISTRATE)

        # The default BL→RTC mirror sync calls this with the mirrored key/data fields when a BL row
        # has no RTC counterpart (e.g. a .blend saved with a different active-blocks manifest).
        # Blocks are owned by the manifest, never by scene data, so those rows are ignored
        if block_module is None:
            stale_block_id = mirrored_fields.get("block_id", "<unknown>")
            logger.warning(f"Ignoring stale saved block row '{stale_block_id}': blocks can only be created from the active-blocks manifest")
            return

        block_id = None

        try:

            shallow_validate_block_module(block_module)
            
            block_declaration = block_module._BLOCK_DECLARATION
            block_id = block_declaration.block_id
            logger.debug(f"Starting creation of block '{block_id}' instance")

            shallow_validate_block_declaration(block_declaration, logger)
            
            # 1: Register the new block's bpy.types.* classes and propertygroups into Blender's native registry
            _create_new_block_bpy_classes(block_declaration, logger)
            _create_new_block_properties(block_declaration, logger)

            # 2: Register the new block's feature-wrapper classes
            new_FWC_instances = _create_and_init_new_block_FWCs(block_declaration, logger)

            # 3: Register the new block's RTC members, loggers, and hook sources. Only sync to Blender on the last iteration
            _create_new_block_standard_features(block_declaration, logger)

            # 4: Create data mirrors to link certain FWCs / RTC members / BL data
            new_data_mirrors = _create_new_block_RTC_data_mirrors(block_declaration, logger)

            # 5: Store Declarations (Not instances) of shard UILists. Commonly used for debugging
            _create_new_block_shared_UILists(block_declaration, logger)
            
            # 6: Add block module to global block registry in RTC
            error_str = None
            _create_new_block_record(block_declaration, new_FWC_instances, error_str, logger)

            logger.info(f"Finished creation of block '{block_id}' instance")

        except Exception as e:
            # logger.error("       fgfg   ", exc_info=True)
            if block_id is None:
                block_id = "<invalid>"
            package_name = ".".join(get_folder_parts(block_module)[-2:])

            traceback.print_exc(limit=-2)
            # print_section_separator(f"Exception when creating {block_id} instance from package '{package_name}'. {str(e)}")
            error_str = str(e)
            failed_block_declaration = Block_Declaration(block_module = block_module, block_id = block_id, block_dependencies = [])
            _create_new_block_record(failed_block_declaration, [], error_str, logger)
            event = Enum_Sync_Events.ADDON_INIT
            # cls._remove_instance(event, block_id = block_id)


    @classmethod
    def _remove_instance(cls, event: Enum_Sync_Events, block_instance: RTC_Block_Instance = None, **mirrored_fields):

        # Note that the Block record itself is not removed from RTC's REGISTRY_ALL_BLOCKS cache. Instead, its 'is_block_enabled' property is set to false
        # It is the only "trace" that should remain of a removed block.

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)

        # Mirror-driven removals are ignored for the same reason as mirror-driven creations
        if block_instance is None:
            stale_block_id = mirrored_fields.get("block_id", "<unknown>")
            logger.warning(f"Ignoring mirror-driven removal of block '{stale_block_id}': blocks can only be removed via the active-blocks manifest")
            return


        logger.debug(f"Starting removal of block '{block_instance.block_id}'")

        _remove_block_FWC_instances(block_instance, logger)

        _remove_block_bpy_classes(block_instance, logger)

        _remove_block_properties(block_instance, logger)

        logger.info(f"Finished removal of block '{block_instance.block_id}'")

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

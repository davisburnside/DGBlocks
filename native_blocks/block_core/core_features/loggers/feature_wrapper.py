
from enum import Enum
from typing import Callable
import types
import logging

# Addon-level imports
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager, Enum_Sync_Actions, Enum_Sync_Events
from .....addon_helpers.generic_tools import is_bpy_ready
from .....my_addon_config import base_linebreak_length

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID, Core_Block_Loggers, Core_Runtime_Cache_Members
from ...core_helpers.BL_RTC_data_sync_tools import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..runtime_cache import Wrapper_Runtime_Cache, get_actual_rtc_key
from .data_structures import RTC_Logger_Instance, rtc_sync_key_fields, rtc_sync_data_fields, _setup_logger_console_handler


# Aliases
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

# ==============================================================================================================================
# PUBLIC CONVENIENCE FUNCTIONS

def get_logger(logger_id: Enum):

    true_logger_id = get_actual_rtc_key(logger_id)
    try:

        cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)
        logger_instance = next((x for x in cached_loggers if x.logger_name == true_logger_id), None)
        if logger_instance is None:
            return Wrapper_Loggers._fallback_logger
        else:
            return logger_instance.logger

    except Exception as e:

        fallback_logger = logging.getLogger("_fallback_logger")
        if fallback_logger is None:
            fallback_logger = Wrapper_Loggers._setup_fallback_logger()
        return fallback_logger

# ==============================================================================================================================
# MAIN MODULE FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Loggers(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager):

    _fallback_logger: logging.Logger = None
    _log_linebreak_monkeypatch_func: Callable = None

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:

        # Define Monkeypatch func to allow custom logger functionality
        def log_with_linebreak(self, log_message: str, length_factor: int = 4):
            log_level = self.getEffectiveLevel()
            linebreak_str = "-" * length_factor * base_linebreak_length
            self.log(log_level, f"{log_message} {linebreak_str}")
        cls._log_linebreak_monkeypatch_func = log_with_linebreak

        # setup the fallback logger. Only real usage is during debugging sessions
        cls._setup_fallback_logger()
        cls._fallback_logger.debug("Running pre-bpy init for Wrapper_Loggers")

        # Create all core loggers
        for new_logger_enum in Core_Block_Loggers:
            cls.create_instance(
                event,
                logger_name=new_logger_enum.name,
                src_block_id=_BLOCK_ID,
                level_name=new_logger_enum.value[1],
            )

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Running post-bpy init for Wrapper_Loggers")

        # BL<->RTC 2-way sync, keeping user's saved logger settings if they exist
        cls.update_BL_with_mirrored_RTC_data(event)   # Causes partial RTC->BL sync
        cls.update_RTC_with_mirrored_BL_data(event)   # Causes full BL-RTC resync

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
        "No action to take. Loggers exist until the addon's final unregister() steps"

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        """
        Synchronizes RTC with the Blender Logger info
        """
        import bpy  # type: ignore
        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating loggers RTC with mirrored BL Data")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)
        scene_loggers = core_props.managed_loggers

        # BL->RTC Sync
        update_dataclasses_to_match_collectionprop(
            actual_FWC=Wrapper_Loggers,
            source=scene_loggers,
            target=cached_loggers,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=set(),
            debug_logger=debug_logger,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):
        """
        Synchronizes Blender log levels with the RTC logger info
        """
        import bpy  # type: ignore
        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating loggers BL Data with mirrored RTC")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Sanity check before sync
        Wrapper_Runtime_Cache.asset_cache_is_not_syncing(cache_key_loggers, cls)

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers)
        scene_loggers = core_props.managed_loggers

        # During init, allow add/move/remove but not edit. This allows user choices to be reloaded after save
        actions_denied = set()
        if event == Enum_Sync_Events.ADDON_INIT:
            actions_denied = {Enum_Sync_Actions.EDIT}

        # BL->RTC Sync
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_loggers, True)
        update_collectionprop_to_match_dataclasses(
            source=cached_loggers,
            target=scene_loggers,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            debug_logger=debug_logger,
            actions_denied=actions_denied,
        )
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_loggers, False)

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        logger_name: Enum,
        src_block_id: str,
        level_name: str,
        skip_BL_sync: bool = False,
    ):

        action_logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)

        true_logger_id = get_actual_rtc_key(logger_name)
        idx, current_logger, cached_loggers = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_loggers, "logger_name", logger_name)

        # Validate uniqueness. Return with no result upon duplication attempt
        if current_logger:
            action_logger.debug(f"Logger '{true_logger_id}' already exists in RTC. Returning with no action")
            return

        # Makes new python logger if not present
        new_logger = logging.getLogger(true_logger_id)
        _setup_logger_console_handler(new_logger, level_name)

        # Attach monkeypatch funcs
        new_logger.log_with_linebreak = types.MethodType(cls._log_linebreak_monkeypatch_func, new_logger)

        # Create data structure for RTC storage
        RTC_logger_instance = RTC_Logger_Instance(
            logger_name=logger_name,
            level_name=level_name,
            src_block_id=src_block_id,
            logger=new_logger
        )

        # Update runtime cache with new logger
        cached_loggers.append(RTC_logger_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_loggers, cached_loggers)
        action_logger.debug(f"Created Logger '{true_logger_id}'")

        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event)

        return new_logger

    @classmethod
    def destroy_instance(
        cls,
        event: Enum_Sync_Events,
        logger_name: any,
        skip_BL_sync: bool = False):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)

        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key=cache_key_loggers,
            uniqueness_field="logger_name",
            uniqueness_field_value=logger_name,
        )
        logger.debug(f"Removed Logger '{logger_name}'")

        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event)

    # --------------------------------------------------------------
    # Private funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def _setup_fallback_logger(cls):

        # setup the fallback logger. Only real usage is during debugging sessions
        cls._fallback_logger = logging.getLogger("_fallback_logger")
        _setup_logger_console_handler(cls._fallback_logger, 10)
        cls._fallback_logger.log_with_linebreak = types.MethodType(cls._log_linebreak_monkeypatch_func, cls._fallback_logger)
        return cls._fallback_logger

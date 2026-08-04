
from enum import Enum
from typing import Callable
import types
import logging
import bpy  # type: ignore


# Addon-level imports
from .....addon_helpers.data_structures import Enum_Sync_Events, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager, Abstract_Feature_Wrapper
from .....addon_config.static_settings import base_linebreak_length

# Intra-block imports
from ...core_helpers.constants import _BLOCK_ID, Core_Block_Loggers, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache, get_actual_rtc_key
from .data_structures import RTC_Logger_Instance, _setup_logger_console_handler


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
    def _init_wrapper(cls) -> bool:

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
        event = Enum_Sync_Events.ADDON_INIT
        for new_logger_enum in Core_Block_Loggers:
            cls._create_instance(
                event,
                logger_name=new_logger_enum.name,
                src_block_id=_BLOCK_ID,
                level_name=new_logger_enum.value.default_level,
            )

        # set_shared_uilist_config(
        #     list_id="LOGGERS_LIST",
        #     col_names=("Source Block", "Logger Name", "Log Level"),
        #     col_widths=(3, 5, 3),
        #     columns_def=[
        #         {"type": "LABEL", "field": "src_block_id"},
        #         {"type": "LABEL", "field": "logger_name"},
        #         {"type": "PROP", "field": "level_name", "icon_only": False}
        #     ],
        #     details_func=None
        # )

    @classmethod
    def _remove_wrapper(cls, event, self_FWC_instance) -> bool:
        "No-op. Loggers exist until the addon's final unregister() steps"

    # --------------------------------------------------------------
    # Formatter management
    # --------------------------------------------------------------

    @classmethod
    def update_logger_formatters(cls, include_datetime: str = "NONE"):
        """
        Rebuild the console-handler formatter on every registered logger so that
        the ":" separator aligns across all log lines, and the optional datetime
        prefix is applied.

        The name/levelname column widths are computed from the longest logger name
        and level label currently registered, + a small margin so future loggers
        don't shift the column mid-session. Called:
          - At startup (after BL data is loaded)
          - When the Include Datetime dropdown changes
          - When a new logger is created (to rebalance widths)
        """
        try:
            from ...core_helpers.constants import Core_Block_Loggers
            cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers) or []
            if not cached_loggers:
                return

            # Compute max widths for all loggers currently registered
            max_name_len = max(len(l.logger_name) for l in cached_loggers)
            max_level_len = max(len(l.level_name) for l in cached_loggers)

            # Add padding so new loggers don't cause the column to shift mid-session
            name_width = max(20, max_name_len + 2)
            level_width = max(10, max_level_len + 2)

            from .....addon_config.static_settings import get_logger_format
            fmt, datefmt = get_logger_format(include_datetime, name_width, level_width)

            for rtc_logger_instance in cached_loggers:
                python_logger = rtc_logger_instance.logger
                for handler in list(python_logger.handlers):
                    if isinstance(handler, logging.StreamHandler):
                        new_formatter = logging.Formatter(fmt, datefmt)
                        handler.setFormatter(new_formatter)

        except Exception:
            pass

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def _create_instance(
        cls,
        event: Enum_Sync_Events,
        logger_name: Enum,
        src_block_id: str,
        level_name: str,
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

        # Rebalance formatter widths so the ":" column stays aligned
        try:
            from .....addon_config.static_settings import get_logger_format
            desired_dt = "NONE"
            try:
                desired_dt = bpy.context.scene.dgblocks_core_props.logger_include_datetime
            except Exception:
                desired_dt = "NONE"
            cls.update_logger_formatters(desired_dt)
        except Exception:
            pass

        return new_logger

    @classmethod
    def _remove_instance(cls, event: Enum_Sync_Events, logger_name: any):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)

        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key=cache_key_loggers,
            uniqueness_field="logger_name",
            uniqueness_field_value=logger_name,
        )
        logger.debug(f"Removed Logger '{logger_name}'")

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Custom BL→RTC sync for loggers.

        Iterate the persistent `managed_loggers` CollectionProperty rows and
        update each matching RTC_Logger_Instance's `level_name`, then push the
        saved level into the live Python logging.Logger object. This ensures
        choices saved in the .blend file are actually applied at startup.
        """
        BL_data_path = data_mirror_instance.scene_colprop_path
        if BL_data_path is None:
            return

        BL_colprop = bpy.context.scene.path_resolve(BL_data_path)
        if BL_colprop is None:
            return

        cached_loggers = Wrapper_Runtime_Cache.get_cache(cache_key_loggers) or []

        # Build a lookup of RTC loggers by name
        rtc_by_name = {l.logger_name: l for l in cached_loggers}

        for bl_row in BL_colprop:
            name = bl_row.logger_name
            rtc_logger = rtc_by_name.get(name)
            if rtc_logger is None:
                continue
            # Update the dataclass field (keeps RTC in sync with BL)
            rtc_logger.level_name = bl_row.level_name
            # Apply the level to the live Python logger
            try:
                rtc_logger.logger.setLevel(bl_row.level_name)
            except Exception:
                pass

        # Rebalance formatter widths / datetime prefix
        try:
            desired_dt = bpy.context.scene.dgblocks_core_props.logger_include_datetime
        except Exception:
            desired_dt = "NONE"
        cls.update_logger_formatters(desired_dt)

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

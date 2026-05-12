# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from dataclasses import dataclass
from enum import Enum
import logging
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .....addon_helpers.data_structures import Enum_Log_Levels, Enum_Sync_Actions, Enum_Sync_Events, RTC_FWC_Data_Mirror_List_Reference
from ..... import my_addon_config
from .....my_addon_config import base_linebreak_length

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

# ==============================================================================================================================
# PRIVATE HELPERS
# ==============================================================================================================================

def _setup_logger_console_handler(logger, logging_level):
    # Set up a console handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(my_addon_config.logger_format)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging_level)  # Default level (will be overwritten later by scene settings)

# ==============================================================================================================================
# BLENDER DATA 

def _callback_log_level_changed(self, context):
    """
    Callback function that runs when a log level changes.
    This is triggered by the UI dropdown or when set via code.
    """

    logger_name = self.logger_name
    new_level_name = self.level_name

    # Get the actual Python logger and update its level
    idx, logger_instance, cached_loggers = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        member_key=cache_key_loggers,
        uniqueness_field="logger_name",
        uniqueness_field_value=logger_name,
    )
    logger = logger_instance.logger
    old_level_int = logger.level
    logger.setLevel(new_level_name)

    # Log the change event
    new_level_int = logging.getLevelNamesMapping()[new_level_name]
    if old_level_int != new_level_int:
        logger.log(new_level_int, f"Log level changed to: {new_level_name}")

class DGBLOCKS_PG_Logger_Instance(bpy.types.PropertyGroup):

    # The unique logger's name
    logger_name: bpy.props.StringProperty(
        name="Logger Name",
        description="Internal name of this logger. Must be unique",
        default="")  # type: ignore

    # Logging level string
    level_name: bpy.props.EnumProperty(
        name="Log Level",
        description="Minimum level of messages to show",
        items=Enum_Log_Levels.tuple_enum_items(),
        default="INFO",
        update=_callback_log_level_changed)  # type: ignore

    # ID of the block that created this logger
    src_block_id: bpy.props.StringProperty(name="Source Block")  # type: ignore

# ==============================================================================================================================
# RTC DATA

# Used during RTC <-> BL data sync
rtc_sync_key_fields = ["logger_name"]
rtc_sync_data_fields = ["level_name", "src_block_id"]

@dataclass
class RTC_Logger_Instance:
    logger_name: str
    level_name: str
    src_block_id: str
    logger: logging.Logger

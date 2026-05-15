# ==============================================================================================================================
# IMPORTS

from dataclasses import dataclass
from enum import Enum
import logging
import bpy  # type: ignore

# Addon-level imports
from ..... import my_addon_config

# Intra-block imports
from ...core_helpers.constants import  Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# Aliases
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

# ==============================================================================================================================
# LOGGER DATA

class Enum_Log_Levels(Enum):
    DEBUG = ("DEBUG", "Debug", "Show all messages", 10)
    INFO = ("INFO", "Info", "Show info and above", 20)
    WARNING = ("WARNING", "Warning", "Show warnings and above", 30)
    ERROR = ("ERROR", "Error", "Show errors and above", 40)
    CRITICAL = ("CRITICAL", "Critical", "Show only critical errors", 50)
    
    @property
    def desc(self):
        return self.value[2]@property
    
    @property
    def weight(self):
        return self.value[3]@property
    
    @classmethod# Used by scene_loggers.level.items
    def tuple_enum_items(cls):
        """Helper to return tuples for Blender: (identifier, name, description)"""
        # We only take the first 3 elements for the UI
        return [item.value[:3] for item in cls]

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

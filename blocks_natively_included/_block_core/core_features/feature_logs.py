# Sample License, ignore for now

# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from dataclasses import dataclass
from typing import Callable
import types
from enum import Enum
import logging
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helper_funcs import is_bpy_ready, ui_draw_list_headers
from ....addon_data_structures import Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Datawrapper_Instance_Manager, Enum_Log_Levels
from .... import my_addon_config
from ....my_addon_config import base_linebreak_length

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_runtime_cache import Wrapper_Runtime_Cache, get_actual_rtc_key
from ..core_helpers.helper_datasync import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..core_helpers.constants import _BLOCK_ID, Core_Block_Loggers, Core_Block_Loggers, Core_Runtime_Cache_Members
rtc_loggers_key = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

# ==============================================================================================================================
# PUBLIC CONVENIENCE FUNCTIONS
# ==============================================================================================================================

def get_logger(logger_id: Enum):
    
    true_logger_id = get_actual_rtc_key(logger_id)
    try:
        
        all_loggers = Wrapper_Runtime_Cache.get_cache(rtc_loggers_key)
        logger_instance = next((x for x in all_loggers if x.logger_name == true_logger_id), None)
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
# PRIVATE API
# ==============================================================================================================================

def _setup_logger_console_handler(logger, logging_level):
    # Set up a console handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(my_addon_config.logger_format)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging_level) # Default level (will be overwritten later by scene settings)

# ==============================================================================================================================
# MIRRORED DATA FOR RTC & BLENDER
# ==============================================================================================================================

# --------------------------------------------------------------
# Blender data, stored in scene
# --------------------------------------------------------------

def _callback_log_level_changed(self, context):
    """
    Callback function that runs when a log level changes.
    This is triggered by the UI dropdown or when set via code.
    """

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(rtc_loggers_key):
        return
    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, True)
    
    logger_name = self.logger_name
    new_level_name = self.level_name
    
    # Get the actual Python logger and update its level
    idx, logger_instance, all_RTC_loggers = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
        member_key = rtc_loggers_key, 
        uniqueness_field = "logger_name", 
        uniqueness_field_value = logger_name,
    )
    logger = logger_instance.logger
    old_level_int = logger.level
    logger.setLevel(new_level_name)
    
    # Log the change event (using INFO so it shows in most cases)
    new_level_int = logging.getLevelNamesMapping()[new_level_name]
    if old_level_int != new_level_int:
        logger.log(new_level_int, f"Log level changed to: {new_level_name}")

    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, False)

class DGBLOCKS_PG_Logger_Instance(bpy.types.PropertyGroup):
    """
    Mirror Dataclass= 'Logger_Instance'
    Mirror RTC Key= 'REGISTRY_ALL_LOGGERS'
    Used to update logger levels in Debug Mode
    Contains source block id, logger name, & level of all loggers of all blocks used by this addon
    """

    # The unique logger's name
    logger_name: bpy.props.StringProperty(
        name="Logger Name",
        description="Internal name of this logger. Must be unique",
        default="") # type: ignore

    # Logging level string
    level_name: bpy.props.EnumProperty(
        name="Log Level",
        description="Minimum level of messages to show",
        items=Enum_Log_Levels.tuple_enum_items(),
        default="INFO",
        update=_callback_log_level_changed) # type: ignore
    
    # ID of the bloc that created this logger
    src_block_id: bpy.props.StringProperty(name="Source Block") # type: ignore

# --------------------------------------------------------------
# RTC data
# --------------------------------------------------------------

# Used during RTC <-> BL data sync
rtc_sync_key_fields = ["logger_name"]
rtc_sync_data_fields = ["level_name", "src_block_id"]

@dataclass
class RTC_Logger_Instance:
    # Record — instance state only, no manager logic
    # Contains all fields of DGBLOCKS_PG_Logger_Instance
    logger_name: str 
    level_name: str 
    src_block_id: str
    logger: logging.Logger

# ==============================================================================================================================
# MAIN MODULE FEATURE
# ==============================================================================================================================

class Wrapper_Loggers(Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Datawrapper_Instance_Manager):
    
    _fallback_logger: logging.Logger = None
    _log_linebreak_monkeypatch_func: Callable = None

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:

        # Define Monkeypatch func to allow custom features
        def log_with_linebreak(self, log_message:str, length_factor:int = 4):
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
                src_block_id = _BLOCK_ID,
                logger_name = new_logger_enum.name,
                level_name = new_logger_enum.value[1],
            )

        return True

    @classmethod
    def init_post_bpy(cls) -> bool:

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Running post-bpy init for Wrapper_Hooks")
        
        cls.update_BL_with_mirrored_RTC_data()
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        "No action to take. Loggers exist until the addon's final unregister() steps"
        return True
    
    # --------------------------------------------------------------
    # Implemented from Abstract_BL_and_RTC_Data_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls):
        """
        Synchronizes RTC with the Blender Logger info
        """
        #TODO finish
        
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating loggers cache with mirrored Blender data")

        all_RTC_logger_instances = Wrapper_Runtime_Cache.get_cache(rtc_loggers_key)
        loggers_collectionprop = bpy.context.scene.dgblocks_core_props.managed_loggers
        update_dataclasses_to_match_collectionprop(
            dataclass_type = Wrapper_Loggers,
            source = loggers_collectionprop,
            target = all_RTC_logger_instances,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls):
        """
        Synchronizes Blender log levels with the RTC logger info
        """

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating Blender data with mirrored loggers cache")
        
        all_RTC_logger_instances = Wrapper_Runtime_Cache.get_cache(rtc_loggers_key)
        loggers_collectionprop = bpy.context.scene.dgblocks_core_props.managed_loggers
        update_collectionprop_to_match_dataclasses(
            source = all_RTC_logger_instances,
            target = loggers_collectionprop,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields
        )

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(cls, src_block_id:str, logger_name:Enum, level_name:str, skip_BL_sync:bool = False):
        
        action_logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)

        true_logger_id = get_actual_rtc_key(logger_name)
        idx, current_logger, all_RTC_loggers = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(rtc_loggers_key, "logger_name", logger_name)

        # Validate uniquness. Return with no result upon duplication attemptlogger_name
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
            logger_name = logger_name,
            level_name = level_name,
            src_block_id = src_block_id,
            logger = new_logger
        )

        # Update runtime cache with new logger
        all_RTC_loggers.append(RTC_logger_instance)
        Wrapper_Runtime_Cache.set_cache(rtc_loggers_key, all_RTC_loggers)
        action_logger.debug(f"Created Logger '{true_logger_id}'")

        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, False)
        
        return new_logger

    @classmethod
    def destroy_instance(cls, logger_name: any, skip_BL_sync: bool = False):

        logger = get_logger(Core_Block_Loggers.REGISTRATE)
        
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key = rtc_loggers_key, 
            uniqueness_field = "logger_name", 
            uniqueness_field_value = logger_name, 
        )
        logger.debug(f"Removed Logger '{logger_name}'")

        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_loggers_key, False)

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

# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Source Block", "Logger Name", "Log Level")
col_widths = (3, 5, 3)
def _uilayout_draw_logger_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text = f"All Loggers ({len(context.scene.dgblocks_core_props.managed_loggers)})")
    if panel_body is not None:        
        col_names = ("Source Block", "Logger Name", "Log Level")
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw the UIList
        row = panel_body.row()
        row_count = len(core_props.managed_loggers)
        row.template_list(
            "DGBLOCKS_UL_Loggers",
            "",
            core_props, "managed_loggers", # Collection property
            core_props, "managed_loggers_selected_idx", # Active index property
            rows = row_count,
            maxrows = row_count,
            columns = row_count, 
        )

class DGBLOCKS_UL_Loggers(bpy.types.UIList):
    """UIList to display RTC blocks with enable toggle and alert states."""
    
    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
       
        row = container.row(align=True)
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.src_block_id)
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.label(text=item.logger_name)
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.prop(item, "level_name", text = "")
        
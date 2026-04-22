
from dataclasses import dataclass
from typing import Callable
import types
from enum import Enum
import logging
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helper_funcs import is_bpy_ready
from ....addon_data_structures import Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Datawrapper_Instance_Manager, Enum_Log_Levels
from .... import my_addon_config

# --------------------------------------------------------------
# Intra-block importsrtc_loggers_key
# --------------------------------------------------------------
from .feature_runtime_cache import Wrapper_Runtime_Cache, get_actual_rtc_key
from ..core_helpers.helper_datasync import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..core_helpers.helper_uilayouts import ui_box_with_header, uilayout_template_columns_for_propertygroup
from ..core_helpers.constants import _BLOCK_ID, Core_Block_Loggers, Core_Block_Loggers, Core_Runtime_Cache_Members

#=================================================================================
# MODULE VARS & CONSTANTS
#=================================================================================

rtc_loggers_key = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

base_linebreak_length = 20
rtc_sync_key_fields = ["logger_name"]
rtc_sync_data_fields = ["level_name", "src_block_id"]

#=================================================================================
# BLENDER DATA FOR FEATURE - Stored in Scene
#=================================================================================

def _callback_log_level_changed(self, context):
    """
    Callback function that runs when a log level changes.
    This is triggered by the UI dropdown or when set via code.
    """

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_registry_being_synced(rtc_loggers_key):
        return
    Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, True)
    
    logger_name = self.logger_name
    new_level_name = self.level_name
    
    # Get the actual Python logger and update its level
    _, logger_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
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
        print(old_level_int, new_level_int)
        logger.log(new_level_int, f"Log level changed to: {new_level_name}")

    Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, False)
    
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

#=================================================================================
# RTC DATA FOR FEATURE - Stored in Scene
#=================================================================================

@dataclass
class RTC_Logger_Instance:
    # Record — instance state only, no manager logic
    # Contains all fields of DGBLOCKS_PG_Logger_Instance
    logger_name: str 
    level_name: str 
    src_block_id: str
    logger: logging.Logger

#=================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
#=================================================================================

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
        cls.setup_fallback_logger()
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
        return
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating loggers cache with mirrored Blender data")

        all_RTC_logger_instances = Wrapper_Runtime_Cache.get_instance(rtc_loggers_key)
        loggers_collectionprop = bpy.context.scene.dgblocks_core_props.scene_RTC_mirror_for_loggers
        update_dataclasses_to_match_collectionprop(
            source = loggers_collectionprop,
            target = all_RTC_logger_instances,
            dataclass_type = Wrapper_Loggers,
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
        
        all_RTC_logger_instances = Wrapper_Runtime_Cache.get_instance(rtc_loggers_key)
        loggers_collectionprop = bpy.context.scene.dgblocks_core_props.scene_RTC_mirror_for_loggers
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
    def get_instance(cls, logger_id: Enum):
        
        all_loggers = Wrapper_Runtime_Cache.get_instance(rtc_loggers_key)
        true_logger_id = get_actual_rtc_key(logger_id)
        if true_logger_id not in all_loggers.keys():
            return None

        return all_loggers[true_logger_id]

    @classmethod
    def create_instance(cls, src_block_id:str, logger_name:Enum, level_name:str, skip_BL_sync:bool = False):
        
        true_logger_id = get_actual_rtc_key(logger_name)
        core_loggers = Wrapper_Runtime_Cache.get_instance(rtc_loggers_key)

        # Validate new logger name
        if true_logger_id in core_loggers:
            raise Exception(f"Block Logger with name '{true_logger_id}' already defined")
        
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

        # Update runtime cache
        core_loggers.append(RTC_logger_instance)
        Wrapper_Runtime_Cache.set_instance(rtc_loggers_key, core_loggers)

        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, False)
        
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
            Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.set_registry_sync_status(rtc_loggers_key, False)
    
    @classmethod
    def set_instance(cls):
        "no-op"
        return 

    # --------------------------------------------------------------
    # Private funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def setup_fallback_logger(cls):
        
        # setup the fallback logger. Only real usage is during debugging sessions
        cls._fallback_logger = logging.getLogger("_fallback_logger")
        _setup_logger_console_handler(cls._fallback_logger, 10)
        cls._fallback_logger.log_with_linebreak = types.MethodType(cls._log_linebreak_monkeypatch_func, cls._fallback_logger)
        return cls._fallback_logger

#=================================================================================
# PUBLIC CONVENIENCE FUNCTIONS
#=================================================================================

def get_logger(logger_id: Enum):
    
    true_logger_id = get_actual_rtc_key(logger_id)
    try:
        
        all_loggers = Wrapper_Runtime_Cache.get_instance(rtc_loggers_key)
        logger_instance = next((x for x in all_loggers if x.logger_name == true_logger_id), None)
        if logger_instance is None:
            return Wrapper_Loggers._fallback_logger
        else:
            return logger_instance.logger
        
    except Exception as e:

        # print(f"Unable to get logger with ID '{true_logger_id}', reverting to fallback logger")
        fallback_logger = logging.getLogger("_fallback_logger")
        if fallback_logger is None:
            fallback_logger = Wrapper_Loggers.setup_fallback_logger()
        return fallback_logger

def print_github_issue_page_statement(logger:logging.Logger = None):
    
    str_log = ""
    if hasattr(my_addon_config, "my_addon_repository") and my_addon_config.my_addon_repository is not None:
        str_log =  """
            A critical error has occured that prevents this addon from working.        
            This log statement is only triggered by sitations which should not happen. 
            Please create an Issue in Github for this this codebase: 

        """ + my_addon_config.my_addon_repository
        logger.critical(str_log)
    else:
        str_log = "No code repository defined for this addon"
        logger.critical("No code repository defined for this addon")
        
    if logger:
        logger.critical(str_log)
    else:
        print(str_log)

def print_section_separator(text, width=100, char="="):
    
    print(f"\n{char * width}")
    print(text.center(width))
    print(f"{char * width}\n")

#=================================================================================
# PRIVATE API
#=================================================================================

def _setup_logger_console_handler(logger, logging_level):
    # Set up a console handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(my_addon_config.logger_format)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging_level) # Default level (will be overwritten later by scene settings)

def _uilayout_draw_logger_settings(context, container):

    scene_loggers = context.scene.dgblocks_core_props.scene_RTC_mirror_for_loggers
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text = "All Loggers")
    if panel_body is not None:        
        prop_titles = [i.logger_name for i in scene_loggers]
        prop_names = ["level_name" for _ in scene_loggers]
        prop_owners = list(scene_loggers)
        uilayout_template_columns_for_propertygroup(context, panel_body, prop_owners, prop_names, prop_titles)

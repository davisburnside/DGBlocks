
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import bpy # type: ignore

from ...addon_data_structures import Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Feature_Wrapper
from .._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_logs import get_logger

from .constants import Block_Logger_Definitions, Draw_Phase_Types, Block_RTC_Members
from .feature_shader import Shader_Instance

#=================================================================================
# RTC DATA FOR FEATURE
#=================================================================================

@dataclass
class RTC_Draw_Handler_Instance:

    draw_phase_name: str # Unique, always a Draw_Phase_Types value
    region_name: str  # Draw_Handler_Region_Types value

    # Relations to other data structures
    associated_shaders: list = field(default_factory=lambda: [])

    # Callables
    _optional_draw_callback: Callable = field(default=None, repr=False)  # The actual draw function. If None, a hook is triggered instead
    _generated_handle: Callable = field(init=False, default=None, repr=False) # Opaque handle returned from draw_handler_add


# =================================================================================
# WRAPPER CLASS
# =================================================================================

def _placeholder_draw_callback(draw_handler_instance: RTC_Draw_Handler_Instance):

    print(draw_handler_instance.draw_phase_name)
    if draw_handler_instance._optional_draw_callback is None:
        Wrapper_Hooks.run_hooked_funcs(draw_handler_instance = draw_handler_instance)
    else:
        draw_handler_instance._optional_draw_callback(draw_handler_instance = draw_handler_instance)

class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper):
    """
    Manages a fixed set of toggleable members with BL ↔ RTC sync.
    No instance creation/destruction — all members exist at dev time.
    """

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        "Define draw-handlers cache structure at startup. The dict will be populated during later init step"

        logger = logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug("Running pre-bpy init for 'Wrapper_Draw_Handlers'")

        # Unlike most RTC members, draw_handlers is fully populated with instances at startup
        # Member count of Block_RTC_Members.DRAW_PHASES never changes, but instance values will be updated as draw_handlers are disabled/enabled
        initial_rtc_data = {}
        for enum_value in Draw_Phase_Types:
            draw_phase_name = enum_value.name
            draw_handler_instance = RTC_Draw_Handler_Instance(
                    draw_phase_name = draw_phase_name,
                    region_name = None,
                    # _optional_draw_callback = None,
                    # _generated_handle = None,
            )
            initial_rtc_data[draw_phase_name] = draw_handler_instance

        all_handler_names = "'" + "', '".join(list(initial_rtc_data.keys())) + "'"
        logger.debug(f"Created empty draw-handler instances for {all_handler_names}")

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, initial_rtc_data)
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        "no-op"
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:

        logger = logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug("Removing Wrapper 'Wrapper_Draw_Handlers'")
        
        # Shaders and groups are automatically removed
        all_rtc_draw_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
        for draw_phase_name in all_rtc_draw_handlers.keys():
            cls.disable_draw_handler(draw_phase_name)

        return True
    
    # --------------------------------------------------------------
    # Funcs specific to this class
    # --------------------------------------------------------------
    
    def add_shader(shader_enum: Enum, shader_group_id: str):
        
        shader_uid = shader_enum.name
        shader_type = shader_enum.value[0]
        shader_builtin_name = shader_enum.value[1] if isinstance(shader_enum.value[1], str) else None
        is_custom_shader = shader_builtin_name is None
        logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"Creating shader '{shader_enum.name}' for group '{shader_group_id}'")

        all_rtc_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        if shader_uid in all_rtc_shaders.keys():
            raise Exception(f"Shader with ID {shader_uid} already exists")

        if is_custom_shader:
            Shader_Class_To_Use = shader_enum.value[1]
            if not isinstance(Shader_Class_To_Use, Shader_Instance):
                raise Exception("Expected child class of Shader_Instance")

        else:
            Shader_Class_To_Use = Shader_Instance

        # Create the shader, either with 'Shader_Instance' class, or (for custom shaders) something that inherits from it
        shader_instance = Shader_Class_To_Use(
            shader_uid = shader_uid,
            shader_type = shader_type,
            builtin_shader_name = shader_builtin_name,
            shader_group_id = shader_group_id
        )
        all_rtc_shaders[shader_uid] = shader_instance
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, all_rtc_shaders)

    @classmethod
    def enable_draw_handler(
        cls, 
        draw_phase_name: str,
        region_name: str = "WINDOW",
        draw_callback: Optional[Callable] = None,
        ):

        logger = logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"Enabling Draw Handler Phase '{draw_phase_name}'")

        draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)[draw_phase_name]

        # Validate status
        if draw_handler_instance._generated_handle is not None:
            logger.warning("Draw Handler '{draw_phase_name}' is already enabled, returning with no action")
            return
        
        # set optional callback
        draw_handler_instance._optional_draw_callback = draw_callback
        draw_handler_instance.region_name = region_name

        # Finally, generate the actual handle. This is necessary to allow proper handler shutdown later, preventing unwanted lingering draws
        draw_handler_instance._generated_handle = bpy.types.SpaceView3D.draw_handler_add(
            _placeholder_draw_callback,
            (draw_handler_instance,), # args tuple passed to the callback. The self-reference is wonky-adjacent but ok
            region_name, 
            draw_phase_name,
        )
        logger.debug(f"Added draw handler '{draw_phase_name}' to bpy.types.SpaceView3D")

    @classmethod
    def disable_draw_handler(cls, draw_phase_name: str) -> None:
        
        logger = logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"Disabling Draw Handler '{draw_phase_name}'")

        draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)[draw_phase_name]

        # Validate status
        if draw_handler_instance._generated_handle is None:
            logger.warning("Draw Handler '{draw_phase_name}' is already disabled, returning with no action")
            return

        bpy.types.SpaceView3D.draw_handler_remove(draw_handler_instance._generated_handle, draw_handler_instance.region_name)
        draw_handler_instance._generated_handle = None
        draw_handler_instance._optional_draw_callback = None
        draw_handler_instance.region_name = None

        logger.debug(f"Removed draw handler '{draw_phase_name}' from bpy.types.SpaceView3D")

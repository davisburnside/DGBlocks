
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import get_names_of_parent_classes
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.runtime_cache  import Wrapper_Runtime_Cache
from ..block_core.core_features.hooks import Wrapper_Hooks
from ..block_core.core_features.loggers import get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Logger_Definitions, Draw_Phase_Types, Block_RTC_Members
from .feature_shader import Shader_Instance

# ==============================================================================================================================
# RTC DATA FOR FEATURE
# ==============================================================================================================================

@dataclass
class RTC_Draw_Handler_Instance:

    draw_phase_name: str # Unique, always a Draw_Phase_Types value
    region_name: str  # Draw_Handler_Region_Types value
    
    # Shader groups that this handler is 'owner' of
    groups_to_shaders_map: defaultdict[list]

    # Callables
    _optional_draw_callback: Callable = field(default=None, repr=False)  # The actual draw function. If None, a hook is triggered instead
    _generated_handle: Callable = field(init=False, default=None, repr=False) # Opaque handle returned from draw_handler_add

# =================================================================================
# WRAPPER CLASS
# =================================================================================

def _placeholder_draw_callback(draw_handler_instance: RTC_Draw_Handler_Instance):
    """
    There are 2 ways to trigger drawing: by hook, or by direct callback.
    Both methods pass a 'RTC_Draw_Handler_Instance' instance, which contains
    """

    # If am (optional) direct callback is defined for the draw handler, call it
    if draw_handler_instance._optional_draw_callback is None:
        Wrapper_Hooks.run_hooked_funcs(draw_handler_instance = draw_handler_instance)
        
    # Otherwise, trigger a hook (runs blindly- no check for subscriber listeners)
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
                groups_to_shaders_map = defaultdict(list),
                region_name = "WINDOW"
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
            cls.disable_draw_handler(draw_phase_name, remove_shaders = True)

        return True
    
    # --------------------------------------------------------------
    # Funcs specific to this class
    # --------------------------------------------------------------
    
    def add_shader(draw_phase_name: str, shader_enum: Enum, shader_group_id: str):
        
        logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        
        # Get shader info from enum
        shader_uid = shader_enum.name
        shader_type = shader_enum.value[0]
        shader_builtin_name = shader_enum.value[1] if isinstance(shader_enum.value[1], str) else None
        is_custom_shader = shader_builtin_name is None
        gap_str = "custom " if is_custom_shader else ""
        if is_custom_shader:
            Shader_Instance_Subclass = shader_enum.value[1]
            custom_shader_kwargs = shader_enum.value[2]
        
        # Validate uniqueness 
        all_rtc_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        if shader_uid in all_rtc_shaders.keys():
            logger.debug(f"Shader with ID {shader_uid} already exists, returning with no action")
            return        
        logger.debug(f"Creating {gap_str}shader '{shader_enum.name}' for group '{shader_group_id}'")
        
        # validate group input
        if not isinstance(shader_group_id, str):
            raise Exception("Shader Group must be a string: {shader_group_id.__class__}")

        # For custom vertex&fragment shaders, a child class of 'Shader_Instance' is needed. Additional args can be defined too.
        
        if is_custom_shader:
            all_parent_classes = get_names_of_parent_classes(Shader_Instance_Subclass)
            if Shader_Instance_Subclass.__name__ not in all_parent_classes:
                raise Exception("Custom Shader must be a child of class 'Shader_Instance'")
            shader_instance = Shader_Instance_Subclass(
                shader_uid = shader_uid,
                shader_type = shader_type,
                builtin_shader_name = shader_builtin_name,
                shader_group_id = shader_group_id,
                **custom_shader_kwargs,
            )
        
        # For predefined builtin shaders
        else:
            shader_instance = Shader_Instance(
                shader_uid = shader_uid,
                shader_type = shader_type,
                builtin_shader_name = shader_builtin_name,
                shader_group_id = shader_group_id
            )

        # Assign to group & cache the new shader
        draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)[draw_phase_name]
        draw_handler_instance.groups_to_shaders_map[shader_group_id].append(shader_uid)
        
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
    def disable_draw_handler(cls, draw_phase_name: str, remove_shaders = False) -> None:
        
        logger = logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
        logger.debug(f"Disabling Draw Handler '{draw_phase_name}'")

        draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)[draw_phase_name]
        all_rtc_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        
        # Delete shader instances from RTC & clear groups map, if needed
        if remove_shaders:
            for group_id, shader_uids_list in draw_handler_instance.groups_to_shaders_map.items():
                for shader_uid in shader_uids_list:
                    del all_rtc_shaders[shader_uid]
        draw_handler_instance.groups_to_shaders_map = defaultdict(list)

        # Validate status
        if draw_handler_instance._generated_handle is None:
            logger.warning("Draw Handler '{draw_phase_name}' is already disabled, returning with no action")
            return

        # Remove from draw-handlers registry & clear callbacks
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler_instance._generated_handle, draw_handler_instance.region_name)
        draw_handler_instance._generated_handle = None
        draw_handler_instance._optional_draw_callback = None
        draw_handler_instance.region_name = None

        logger.debug(f"Removed draw handler '{draw_phase_name}' from bpy.types.SpaceView3D")


import time
import gpu # type: ignore
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.generic_tools import get_exception_last_n_lines

# --------------------------------------------------------------
# Inter-block imports
from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger
from ...native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Intra-block imports
from .common_constants import Block_Loggers, Block_RTC_Members

# ----------------------------------------------------------
# Public convenience funcs

def set_draw_alpha():
    gpu.state.blend_set('ALPHA')


def set_draw_geometry_occluded():
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(True)


def set_draw_geometry_unoccluded():
    gpu.state.depth_test_set('NONE')
    gpu.state.depth_mask_set(False)

# ----------------------------------------------------------
# Internal Helpers

def _capture_gpu_state() -> dict:
    return {
        "blend":        gpu.state.blend_get(),
        "depth_test":   gpu.state.depth_test_get(),
        "depth_mask":   gpu.state.depth_mask_get(),
        "line_width":   gpu.state.line_width_get(),
    }


def _restore_gpu_state(state: dict):
    gpu.state.blend_set(state["blend"])
    gpu.state.depth_test_set(state["depth_test"])
    gpu.state.depth_mask_set(state["depth_mask"])
    gpu.state.line_width_set(state["line_width"])

def _teardown_draw_handler(draw_handler_instance):

    """Remove the Blender draw handler and discard all shader references."""
    if draw_handler_instance._handle is not None:
        try:
            draw_handler_instance.space.value.draw_handler_remove(draw_handler_instance._handle, draw_handler_instance.region.value)
        except Exception:
            pass  # handler may already be gone (e.g. context teardown)
        draw_handler_instance._handle = None
    draw_handler_instance.shader_names.clear()

# ----------------------------------------------------------
# Drawing function used by all (builtin & custom) UI Shaders

def _universal_draw_callback(handler_instance) -> None:
    """
    # MODULE-LEVEL DRAW CALLBACK
    # One function reused for every draw_handler_add call.
    # The handler instance is passed via Blender's args tuple.
    # No context is used here.
    """

    if (    bpy.context is None 
            or bpy.context.area is None
            or bpy.context.region is None
            or bpy.context.area.type != handler_instance.space.name 
            or bpy.context.region.type != handler_instance.region.name):
        return

    logger = get_logger(Block_Loggers.SHADER_BATCH_EVENTS)

    prev_gpu_state = _capture_gpu_state()

    # Try each draw. Flag shader instance upon expection
    cached_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
    cached_shader_uids = [s.shader_uid for s in cached_shaders]
    shader_count = len(handler_instance.shader_names)
    failed_shaders = []
    logger.debug(f"Drawing {shader_count} Shaders of Drawhandler {handler_instance.space} : {handler_instance.region} : {handler_instance.phase}")
    for shader_uid in handler_instance.shader_names:
        try:
            
            # Fetch shader instance from cache
            cache_idx = cached_shader_uids.index(shader_uid)
            if cache_idx == -1: 
                raise Exception(f"Shader {shader_uid} not found")
            shader = cached_shaders[cache_idx]

            # Draw the shader
            if shader.is_enabled:
                shader.last_draw_attempt_timestamp = time.time()

                # Builtin shaders include optional before/after callbacks, because the '_shader_draw' func is not overrideable in this case
                if shader._is_builtin_shader:
                    shader._builtin_shader_before_draw()
                    shader._shader_draw()
                    shader._builtin_shader_after_draw()

                # Custom shaders are expected to handle all logic in an overridden '_shader_draw' func
                else:
                    shader._shader_draw()

        except Exception as e:
            shader.shader_error_str = get_exception_last_n_lines(2, e)
            failed_shaders.append(shader)

    # restore gpou state
    _restore_gpu_state(prev_gpu_state)

    # Log failures
    f_count = len(failed_shaders)
    if f_count > 0:
        logger.error(f"{f_count} of {shader_count} shaders failed during _shader_draw(). ")
        max_uid_length = max([len(s.shader_uid) for s in failed_shaders])
        for shader in failed_shaders:
            logger.error(f"{shader.shader_uid.ljust(max_uid_length)} : {shader.shader_error_str}")


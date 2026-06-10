
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
from .BL_drawing_structures import _BUILTIN_SHADER_COMPATIBLE_TYPES, _VALID_SPACE_REGION_PHASE_COMBOS

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members

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

def validate_shader_definitions(shader_defs: list) -> None:
    """
    Run all validation checks against a list of Shader_Definition objects.
    Raises ValueError with a descriptive message if any check fails.
    All checks complete before any Blender state is mutated.
    """
    # --- duplicate uid check ---
    seen_uids: set = set()
    for sdef in shader_defs:
        if sdef.shader_uid in seen_uids:
            raise ValueError(
                f"Duplicate shader uid '{sdef.shader_uid}' in definition_accumulator. "
                f"Every Shader_Definition must have a unique uid."
            )
        seen_uids.add(sdef.shader_uid)

    # --- (space, region, phase) allowlist check ---
    for sdef in shader_defs:
        combo = (sdef.space, sdef.region, sdef.phase)
        if combo not in _VALID_SPACE_REGION_PHASE_COMBOS:
            raise ValueError(
                f"Shader '{sdef.shader_uid}': "
                f"({sdef.space.name}, {sdef.region}, {sdef.phase}) "
                f"is not a known-valid (space, region, phase) combination. "
                f"See drawing_constants._VALID_SPACE_REGION_PHASE_COMBOS for the allowlist."
            )

    # --- builtin vs custom mutual-exclusion check ---
    for sdef in shader_defs:
        has_builtin = sdef.builtin_shader_name is not None
        has_custom  = sdef.custom_shader_class is not None
        if has_builtin and has_custom:
            raise ValueError(
                f"Shader '{sdef.shader_uid}': both builtin_shader_name and custom_shader_class "
                f"are set. Exactly one must be provided."
            )
        if not has_builtin and not has_custom:
            raise ValueError(
                f"Shader '{sdef.shader_uid}': neither builtin_shader_name nor custom_shader_class "
                f"is set. Exactly one must be provided."
            )

    # --- shader_type / builtin_shader_name compatibility check (builtin shaders only) ---
    for sdef in shader_defs:
        if sdef.builtin_shader_name is None:
            continue  # custom shader — no builtin compatibility to check
        allowed_types = _BUILTIN_SHADER_COMPATIBLE_TYPES.get(sdef.builtin_shader_name)
        if allowed_types is None:
            raise ValueError(
                f"Shader '{sdef.shader_uid}': builtin shader name "
                f"'{sdef.builtin_shader_name}' is not in the compatibility map. "
                f"Known names: {list(_BUILTIN_SHADER_COMPATIBLE_TYPES.keys())}"
            )
        if sdef.shader_type not in allowed_types:
            raise ValueError(
                f"Shader '{sdef.shader_uid}': builtin shader '{sdef.builtin_shader_name}' "
                f"is not compatible with shader type '{sdef.shader_type}'. "
                f"Allowed types for this builtin: {sorted(str(t) for t in allowed_types)}"
            )


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
        shader = None
        try:
            
            # Fetch shader instance from cache
            if shader_uid not in cached_shader_uids: 
                raise Exception(f"Shader {shader_uid} not found")
            cache_idx = cached_shader_uids.index(shader_uid)
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
            if shader:
                shader.shader_error_str = get_exception_last_n_lines(2, e)
                shader.is_enabled = False
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



import time

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.generic_tools import get_exception_last_n_lines

# --------------------------------------------------------------
# Inter-block imports
from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger

# --------------------------------------------------------------
# Intra-block imports
from .common_constants import Block_Loggers
from .BL_gpu_data_structures import _BUILTIN_SHADER_COMPATIBLE_TYPES, _VALID_SPACE_REGION_PHASE_COMBOS 

# ----------------------------------------------------------
# Drawing function used by all (builtin & custom) UI Shaders
def callback_omnishader_draw(handler_instance) -> None:
    """
    # MODULE-LEVEL DRAW CALLBACK
    # One function reused for every draw_handler_add call.
    # The handler instance is passed via Blender's args tuple.
    # No context is used here.
    """

    logger = get_logger(Block_Loggers.SHADER_BATCH_EVENTS)

    # Try each draw. Flag shader instance upon expection
    t_count = len(handler_instance.shaders)
    failed_shaders = []
    logger.debug(f"Drawing {t_count} Shaders of Drawhandler {handler_instance.space} : {handler_instance.region} : {handler_instance.phase}")
    for shader in handler_instance.shaders:
        try:
            if shader.is_enabled:
                shader.last_draw_attempt_timestamp = time.time()
                # shader._before_shader_draw()
                shader._shader_draw()
                # shader._after_shader_draw()
        except Exception as e:
            shader.is_valid = False
            shader.disabled_reason = get_exception_last_n_lines(2, e)
            failed_shaders.append(shader)

    # Log failures
    f_count = len(failed_shaders)
    
    if f_count > 0:
        logger.error(f"{f_count} of {t_count} shaders failed during draw(). ")

        max_uid_length = max([len(s.shader_uid) for s in failed_shaders])
        for shader in failed_shaders:
            logger.error(f"{shader.shader_uid.ljust(max_uid_length)} : {shader.disabled_reason}")

# ----------------------------------------------------------
# Internal validation 

def validate_shader_definitions(shader_defs: list) -> None:
    """
    Run all validation checks against a list of Shader_Definition objects.
    Raises ValueError with a descriptive message if any check fails.
    All checks complete before any Blender state is mutated.
    """
    # --- duplicate uid check ---
    seen_uids: set = set()
    for sdef in shader_defs:
        if sdef.uid in seen_uids:
            raise ValueError(
                f"Duplicate shader uid '{sdef.uid}' found in set_state call. "
                f"Every Shader_Definition must have a unique uid."
            )
        seen_uids.add(sdef.uid)

    # --- (space, region, phase) allowlist check ---
    for sdef in shader_defs:
        combo = (sdef.space, sdef.region, sdef.phase)
        if combo not in _VALID_SPACE_REGION_PHASE_COMBOS:
            raise ValueError(
                f"Shader '{sdef.uid}': "
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
                f"Shader '{sdef.uid}': both builtin_shader_name and custom_shader_class "
                f"are set. Exactly one must be provided."
            )
        if not has_builtin and not has_custom:
            raise ValueError(
                f"Shader '{sdef.uid}': neither builtin_shader_name nor custom_shader_class "
                f"is set. Exactly one must be provided."
            )

    # --- shader_type / builtin_shader_name compatibility check (builtin shaders only) ---
    for sdef in shader_defs:
        if sdef.builtin_shader_name is None:
            continue  # custom shader — no builtin compatibility to check
        allowed_types = _BUILTIN_SHADER_COMPATIBLE_TYPES.get(sdef.builtin_shader_name)
        if allowed_types is None:
            raise ValueError(
                f"Shader '{sdef.uid}': builtin shader name "
                f"'{sdef.builtin_shader_name}' is not in the compatibility map. "
                f"Known names: {list(_BUILTIN_SHADER_COMPATIBLE_TYPES.keys())}"
            )
        if sdef.shader_type not in allowed_types:
            raise ValueError(
                f"Shader '{sdef.uid}': builtin shader '{sdef.builtin_shader_name}' "
                f"is not compatible with shader type '{sdef.shader_type}'. "
                f"Allowed types for this builtin: {sorted(str(t) for t in allowed_types)}"
            )

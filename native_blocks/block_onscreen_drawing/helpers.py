
from collections import defaultdict
import time
import types
import gpu # type: ignore
import bpy

# Addon-level imports
from ...addon_helpers.generic_tools import get_exception_last_n_lines
from ...addon_helpers.data_structures import Enum_Sync_Events

# Inter-block imports
from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ...native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .BL_drawing_structures import _BUILTIN_SHADER_COMPATIBLE_TYPES, _VALID_SPACE_REGION_PHASE_COMBOS

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import Shader_Instance, Drawhandler_Instance

# Aliases
cache_key_shaders = Block_RTC_Members.SHADERS

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


def _clear_all_shaders(include_BL_data = True) -> None:

    logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)

    rtc_draw_phases = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)
    for handler_instance in rtc_draw_phases:
        _teardown_draw_handler(handler_instance)
        logger.debug(
            f"Torn down handler for ({handler_instance.space.name}, "
            f"{handler_instance.region}, {handler_instance.phase})"
        )

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, [])
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, [])

    if include_BL_data:
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        drawing_props.shader_mirror.clear()
        drawing_props.shader_mirror_selected_idx = 0

    logger.debug("clear complete")


def _rebuild_all_shaders(event: Enum_Sync_Events, sync_BL = True) -> None:
    """
    Full rebuild cycle:
        1. Clear existing draw handlers and shader instances.
        2. Fire hook_get_shader_definitions — downstream blocks return Shader_Definition
            objects.
        3. Validate all collected definitions (uid uniqueness, valid space/region/phase
            combos, builtin-vs-custom exclusivity, shader type compatibility).
        4. Group by (space, region, phase), create Shader_Instances, register one Blender
            draw handler per group.
        5. Restore is_enabled from the BL shader_mirror (user preferences survive rebuilds
            and undo/redo).
        6. Sync BL shader_mirror rows to reflect the current live shader set.
        7. Fire hook_before_first_draw — downstream blocks push initial geometry here.
    """
    logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
    logger.debug("Rebuilding all Shaders")

    _clear_all_shaders()

    # Collect Shader_Definitions from all downstream blocks
    shaders_from_blocks = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name = Block_Hook_Sources.hook_get_shader_definitions,
        should_halt_on_exception=False,
    )
    list_shaders_from_blocks = sum(shaders_from_blocks.values(), []) # Simple list, order-preserving
    inverted_shaders_dict = {shader.shader_uid: key for key, shaders in shaders_from_blocks.items() for shader in shaders}
    if len(list_shaders_from_blocks) == 0:
        logger.info("No Shaders to draw, returning early")
        return
    validate_shader_definitions(list_shaders_from_blocks)

    # Group definitions by (space, region, phase)
    groups: dict = defaultdict(list)
    for sdef in list_shaders_from_blocks:
        key = (sdef.space, sdef.region, sdef.phase)
        groups[key].append(sdef)

    # --- Build Shader_Instances and register draw handlers ---
    rtc_draw_phases = []
    rtc_shaders = []
    for (space, region, phase), sdefs in groups.items():
        handler_instance = Drawhandler_Instance(space=space, region=region, phase=phase)
        for sdef in sdefs:
            source_block_id = inverted_shaders_dict[sdef.shader_uid]
            if sdef.custom_shader_class is not None:
                shader_instance = sdef.custom_shader_class(
                    src_block_id = source_block_id,
                    shader_uid = sdef.shader_uid,
                    shader_type = sdef.shader_type,
                    builtin_shader_name = None,
                    draw_space = sdef.space,
                    draw_region = sdef.region,
                    draw_phase = sdef.phase,
                    **sdef.custom_shader_kwargs,
                )
                logger.debug(
                    f"Created custom Shader_Instance uid='{sdef.shader_uid}' "
                    f"(class={sdef.custom_shader_class.__name__}, type={sdef.shader_type})"
                )
            else:
                shader_instance = Shader_Instance(
                    src_block_id = source_block_id,
                    shader_uid = sdef.shader_uid,
                    shader_type = sdef.shader_type,
                    builtin_shader_name = sdef.builtin_shader_name,
                    draw_space = sdef.space,
                    draw_region = sdef.region,
                    draw_phase = sdef.phase,
                )

                # Monkeypatch optional before/after draw callbacks
                if sdef.builtin_shader_before_draw is not None:
                    shader_instance._builtin_shader_before_draw = types.MethodType(
                        sdef.builtin_shader_before_draw, shader_instance
                    )
                if sdef.builtin_shader_after_draw is not None:
                    shader_instance._builtin_shader_after_draw = types.MethodType(
                        sdef.builtin_shader_after_draw, shader_instance
                    )
                logger.debug(
                    f"Created builtin Shader_Instance uid='{sdef.shader_uid}' "
                    f"({sdef.shader_type}/{sdef.builtin_shader_name})"
                )

            shader_instance._shader_init()
            shader_instance.shader_creation_timestamp = time.time()
            handler_instance.shader_names.append(sdef.shader_uid)
            rtc_shaders.append(shader_instance)

        # Register one Blender draw handler for this (space, region, phase) group
        handler_instance._handle = space.value.draw_handler_add(
            _universal_draw_callback,
            (handler_instance,),
            region.value,
            phase.value,
        )
        rtc_draw_phases.append(handler_instance)
        logger.debug(f"Registered draw handler for ({space.name}, {region}, {phase})")

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, rtc_draw_phases)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, rtc_shaders)
    logger.info(f"Created {len(list_shaders_from_blocks)} Shaders across {len(rtc_draw_phases)} Draw Handlers")

    if sync_BL:
        FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_shaders)
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event = Enum_Sync_Events, 
            BL_is_truth_source = False,
            cache_key = cache_key_shaders,
            FWC_instance = FWC_instance,
            data_mirror_instance = data_mirror_instance,
            actions_denied = set(),
            logger = logger,
        )
        # cls.update_BL_with_mirrored_RTC_data(event, FWC_instance, data_mirror_instance)

    # Notify downstream blocks before the first draw. Blocks can populate Shader Instrance's points/colors arrays from this hook
    Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_before_first_draw,
        should_halt_on_exception=False,
    )

# ----------------------------------------------------------
# Drawing function used by all (builtin & custom) UI Shaders

def _handle_batch_update(shader):

    if shader._needs_new_batch:
        start_ts = time.time()
        shader._shader_update_batch()
        duration = (time.time() - start_ts)
        shader.last_batch_creation_timestamp = start_ts
        shader.last_batch_creation_duration = duration
        shader.batch_count_of_shader += 1
        shader._needs_new_batch = False

def _universal_draw_callback(handler_instance) -> None:
    """
    Universa function reused for every draw_handler_add call.
    Used for both builtin and custom shaders
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
                shader.last_draw_timestamp = time.time()
                shader.draw_count_of_batch += 1

                # Builtin shaders include optional before/after callbacks, because the '_shader_draw' func is not overrideable in this case
                if shader._is_builtin_shader:
                    if shader._builtin_shader_before_draw:
                        shader._builtin_shader_before_draw()
                    _handle_batch_update(shader)
                    shader._shader_draw()
                    if shader._builtin_shader_after_draw:
                        shader._builtin_shader_after_draw()

                # Custom shaders are expected to handle all logic in an overridden '_shader_draw' func
                else:
                    _handle_batch_update(shader)
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


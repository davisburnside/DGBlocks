
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
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager
from .BL_drawing_structures import _BUILTIN_SHADER_COMPATIBLE_TYPES, _VALID_SPACE_REGION_PHASE_COMBOS
from .animations.engine import suppress_timer_rebuilds

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import Shader_Instance, Drawhandler_Instance

# --------------------------------------------------------------
# Constants

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

def _validate_shader_definitions(shader_defs: list) -> None:
    """
    Run all validation checks against a list of Shader_Declaration objects.
    Raises ValueError with a descriptive message if any check fails.
    All checks complete before any Blender state is mutated.
    """
    # --- duplicate uid check ---
    seen_uids: set = set()
    for sdef in shader_defs:
        if sdef.shader_uid in seen_uids:
            raise ValueError(
                f"Duplicate shader uid '{sdef.shader_uid}' in definition_accumulator. "
                f"Every Shader_Declaration must have a unique uid."
            )
        seen_uids.add(sdef.shader_uid)

    # --- (space, region, phase) allowlist check ---
    for sdef in shader_defs:
        combo = (sdef.space, sdef.region, sdef.phase)
        # TODO: 7/2/26 find reason for error:  Shader 'BILLBOARD': (VIEW_3D, WINDOW, POST_VIEW) is not a known-valid (space, region, phase) combination. See drawing_constants._VALID_SPACE_REGION_PHASE_COMBOS for the allowlist.
        # if combo not in _VALID_SPACE_REGION_PHASE_COMBOS:
        #     raise ValueError(
        #         f"Shader '{sdef.shader_uid}': "
        #         f"({sdef.space.name}, {sdef.region}, {sdef.phase}) "
        #         f"is not a known-valid (space, region, phase) combination. "
        #         f"See drawing_constants._VALID_SPACE_REGION_PHASE_COMBOS for the allowlist."
        #     )

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


def _apply_builtin_callbacks(shader_instance, sdef) -> None:
    """(Re)apply the optional before/after draw monkeypatches for a builtin shader."""
    if sdef.builtin_shader_before_draw is not None:
        shader_instance._builtin_shader_before_draw = types.MethodType(
            sdef.builtin_shader_before_draw, shader_instance
        )
    if sdef.builtin_shader_after_draw is not None:
        shader_instance._builtin_shader_after_draw = types.MethodType(
            sdef.builtin_shader_after_draw, shader_instance
        )


def _create_shader_instance(sdef, source_block_id, logger):
    """Create a fresh Shader_Instance (builtin or custom) from a Shader_Declaration."""
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
        _apply_builtin_callbacks(shader_instance, sdef)
        logger.debug(
            f"Created builtin Shader_Instance uid='{sdef.shader_uid}' "
            f"({sdef.shader_type}/{sdef.builtin_shader_name})"
        )

    shader_instance._shader_init()
    shader_instance.shader_creation_timestamp = time.time()
    return shader_instance


def _can_reuse_shader(existing, sdef) -> bool:
    """
    True if an existing live Shader_Instance can be reused as-is for `sdef` — i.e. its
    class, shader type, builtin name and draw location all still match. Reusing preserves
    the GPU batch, cached uniforms, is_enabled state and imperatively-added animations
    across a repoll / undo / redo.
    """
    if existing is None:
        return False
    expected_class = sdef.custom_shader_class or Shader_Instance
    if type(existing) is not expected_class:
        return False
    if existing.shader_type != sdef.shader_type:
        return False
    if existing.builtin_shader_name != sdef.builtin_shader_name:
        return False
    if (existing.draw_space != sdef.space
            or existing.draw_region != sdef.region
            or existing.draw_phase != sdef.phase):
        return False
    return True



def _rebuild_all_shaders(event: Enum_Sync_Events, sync_BL = True) -> None:
    """
    Reconcile the live shader set against the current downstream declarations, REUSING
    existing Shader_Instance objects wherever possible instead of destroying them.

    Cycle:
        1. Fire hook_get_shader_definitions — authoritative "what should exist" set.
        2. Validate all collected definitions.
        3. Tear down all existing draw handlers (cheap — they reference shaders by uid).
        4. Destroy only shaders whose uid disappeared (cancel their animations).
        5. Group by (space, region, phase). Reuse a compatible live Shader_Instance where
            possible (keeps batch, uniforms, is_enabled, animations); else create a new one.
            Register one draw handler per group (resiliently).
        6. Sync BL shader_mirror rows (uid + display fields only) to reflect the live set.
        7. Fire hook_before_first_draw — downstream blocks push geometry here.
        8. Apply Shader_Declaration.animations (idempotent for reused shaders).

    Step 8 must run AFTER step 7: an Animation_Declaration with start_state=None
    auto-captures its start value off the shader, so the geometry has to be in place
    first or the capture reads None and the animation is skipped.
    """
    logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
    logger.debug("Reconciling all Shaders")

    # Collect Shader_Definitions from all downstream blocks (authoritative desired set)
    shaders_from_blocks = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name = Block_Hook_Sources.hook_get_shader_definitions,
        should_halt_on_exception=False,
    )
    list_shaders_from_blocks = sum(shaders_from_blocks.values(), []) # Simple list, order-preserving
    inverted_shaders_dict = {shader.shader_uid: key for key, shaders in shaders_from_blocks.items() for shader in shaders}
    if len(list_shaders_from_blocks) == 0:
        logger.info("No Shaders to draw — clearing everything")
        _clear_all_shaders()
        return
    _validate_shader_definitions(list_shaders_from_blocks)

    # Snapshot the current live instances so we can reuse them by uid
    existing_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS) or []
    existing_by_uid = {s.shader_uid: s for s in existing_shaders}
    desired_uids = {sdef.shader_uid for sdef in list_shaders_from_blocks}

    # Tear down every existing draw handler; instances are kept and re-grouped below.
    existing_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES) or []
    for handler_instance in existing_handlers:
        _teardown_draw_handler(handler_instance)

    # Destroy only shaders whose uid is gone (frees their animations/timers).
    for uid, shader_instance in existing_by_uid.items():
        if uid not in desired_uids:
            shader_instance.cancel_all_animations(revert=False)
            logger.debug(f"Destroying removed shader uid='{uid}'")

    # Group definitions by (space, region, phase)
    groups: dict = defaultdict(list)
    for sdef in list_shaders_from_blocks:
        key = (sdef.space, sdef.region, sdef.phase)
        groups[key].append(sdef)

    # --- Build/reuse Shader_Instances and register draw handlers ---
    rtc_draw_phases = []
    rtc_shaders = []
    reused_uids: set = set()
    for (space, region, phase), sdefs in groups.items():
        handler_instance = Drawhandler_Instance(space=space, region=region, phase=phase)
        group_shaders = []
        for sdef in sdefs:
            source_block_id = inverted_shaders_dict[sdef.shader_uid]
            existing = existing_by_uid.get(sdef.shader_uid)
            if _can_reuse_shader(existing, sdef):
                shader_instance = existing
                reused_uids.add(sdef.shader_uid)
                # Re-apply monkeypatched callbacks in case the declaration changed them.
                if sdef.custom_shader_class is None:
                    _apply_builtin_callbacks(shader_instance, sdef)
            else:
                # Existing-but-incompatible: free its animations before replacing.
                if existing is not None:
                    existing.cancel_all_animations(revert=False)
                shader_instance = _create_shader_instance(sdef, source_block_id, logger)
            handler_instance.shader_names.append(sdef.shader_uid)
            group_shaders.append(shader_instance)

        # Register one Blender draw handler for this (space, region, phase) group.
        # Some (space, region) combos are invalid for draw_handler_add and would raise;
        # isolate the failure so one bad group can't abort the whole reconcile.
        try:
            handler_instance._handle = space.value.draw_handler_add(
                _universal_draw_callback,
                (handler_instance,),
                region.value,
                phase.value,
            )
        except Exception:
            logger.error(
                f"Failed to register draw handler for ({space.name}, {region}, {phase}); "
                f"skipping this group",
                exc_info=True,
            )
            for shader_instance in group_shaders:
                if shader_instance.shader_uid not in reused_uids:
                    shader_instance.cancel_all_animations(revert=False)
            continue

        rtc_draw_phases.append(handler_instance)
        rtc_shaders.extend(group_shaders)
        logger.debug(f"Registered draw handler for ({space.name}, {region}, {phase})")

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, rtc_draw_phases)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.SHADERS, rtc_shaders)
    logger.info(
        f"Reconciled {len(rtc_shaders)} Shaders across {len(rtc_draw_phases)} Draw Handlers "
        f"({len(reused_uids)} reused)"
    )

    if sync_BL:
        FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(Block_RTC_Members.SHADERS)
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event = event, 
            BL_is_truth_source = False,
            cache_key = Block_RTC_Members.SHADERS,
            FWC_instance = FWC_instance,
            data_mirror_instance = data_mirror_instance,
            actions_denied = set(),
            logger = logger,
        )
        # cls._update_BL_with_mirrored_RTC_data(event, FWC_instance, data_mirror_instance)

    # Notify downstream blocks before the first draw. Blocks can populate Shader Instrance's points/colors arrays from this hook
    Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_before_first_draw,
        should_halt_on_exception=False,
    )

    # Apply declared animations LAST, now that geometry is populated, so that any
    # declaration using start_state=None captures a real value instead of None.
    _apply_declared_animations(list_shaders_from_blocks, rtc_shaders, logger)


def _apply_declared_animations(shader_definitions: list, shader_instances: list, logger) -> None:
    """
    Attach each Shader_Declaration.animations entry to its live Shader_Instance.

    Declared animations are re-created on every rebuild, so they survive undo/redo,
    debug toggles, and any other event that recreates the shader set. Animations
    added imperatively via shader.set_animation() are NOT restored here — they live
    only as long as the shader instance that owns them.

    All the adds are wrapped in a single suppression scope so that N animations
    cause one timer rebuild instead of N.
    """
    instances_by_uid = {s.shader_uid: s for s in shader_instances}

    applied_count = 0
    with suppress_timer_rebuilds():
        for sdef in shader_definitions:
            declared = getattr(sdef, "animations", None)
            if not declared:
                continue
            shader_instance = instances_by_uid.get(sdef.shader_uid)
            if shader_instance is None:
                continue
            for animation_declaration in declared:
                shader_instance.add_animation(animation_declaration)
                applied_count += 1

    if applied_count > 0:
        logger.info(f"Applied {applied_count} declared animation(s) across all shaders")
        Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)

# ----------------------------------------------------------
# Drawing function used by all (builtin & custom) UI Shaders

def _handle_batch_update(shader):

    if shader._needs_new_batch:
        start_ts = time.time()
        shader._shader_update_batch()
        duration = (time.time() - start_ts)
        shader.last_batch_creation_timestamp = start_ts
        shader.last_batch_creation_duration = duration
        shader.draw_count_of_batch = 0
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
            if not shader.is_enabled:
                pass
            else:
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


def apply_global_opacity_multiplier(colors_array, opacity_multiplier):
    """
    Apply global opacity multiplier to color array's alpha channel.
    
    Args:
        colors_array: numpy array of shape (n, 4) with RGBA colors
        opacity_multiplier: float 0-1, multiplier for alpha channel
        
    Returns:
        Modified colors_array with alpha multiplied
    """
    if opacity_multiplier < 1.0 and len(colors_array) > 0:
        colors_array = colors_array.copy()
        colors_array[:, 3] *= opacity_multiplier
    return colors_array

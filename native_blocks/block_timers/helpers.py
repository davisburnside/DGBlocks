
from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.generic_tools import force_redraw_ui, get_exception_last_n_lines
from ...addon_helpers.data_structures import Enum_Sync_Events

# Inter-block imports
from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ...native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import Timer_Definition, Timer_Instance

# Aliases
cache_key_timers = Block_RTC_Members.TIMERS

# ==============================================================================================================================
# VALIDATION

def validate_timer_definitions(timer_defs: list) -> None:
    """
    Run all validation checks against a list of Timer_Definition objects.
    Raises ValueError with a descriptive message if any check fails.
    All checks complete before any bpy or RTC state is mutated.
    """
    # --- timer_uid must be a string ---
    for tdef in timer_defs:
        if not isinstance(tdef.timer_uid, str):
            raise ValueError(f"Timer_Definition.timer_uid must be a string, got {type(tdef.timer_uid)}.")

    # --- duplicate non-blank uid check ---
    seen_uids: set = set()
    for tdef in timer_defs:
        if tdef.timer_uid == "":
            continue  # blank UIDs are allowed
        if tdef.timer_uid in seen_uids:
            raise ValueError(
                f"Duplicate timer_uid '{tdef.timer_uid}'. "
                f"Every non-blank Timer_Definition timer_uid must be unique."
            )
        seen_uids.add(tdef.timer_uid)

    # --- frequency must be a positive, non-bool number ---
    for tdef in timer_defs:
        uid_label = tdef.timer_uid if tdef.timer_uid else "<blank>"
        if isinstance(tdef.frequency, bool) or not isinstance(tdef.frequency, (int, float)):
            raise ValueError(
                f"Timer '{uid_label}': frequency must be a number, got {type(tdef.frequency)}."
            )
        if tdef.frequency <= 0:
            raise ValueError(
                f"Timer '{uid_label}': frequency must be > 0, got {tdef.frequency}."
            )

    # --- callback must be callable ---
    for tdef in timer_defs:
        if not callable(tdef.callback):
            uid_label = tdef.timer_uid if tdef.timer_uid else "<blank>"
            raise ValueError(
                f"Timer '{uid_label}': callback must be callable, got {type(tdef.callback)}."
            )

# ==============================================================================================================================
# BPY TIMER REGISTRATION HELPERS

def _make_timer_func(timer_instance: Timer_Instance):
    """
    Return a thin closure for bpy.app.timers.register().
    All actual logic lives in _universal_timer_callback — this closure
    is only the minimal dispatcher that bpy requires.
    """
    def _func():
        return _universal_timer_callback(timer_instance)
    return _func


def _register_bpy_timer(timer_instance: Timer_Instance) -> None:
    """Create and register a bpy.app.timers callable for the given instance."""
    logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)

    if timer_instance._timer_func is not None and bpy.app.timers.is_registered(timer_instance._timer_func):
        logger.debug(f"_register_bpy_timer: '{timer_instance.timer_uid}' already registered, skipping")
        return

    func = _make_timer_func(timer_instance)
    bpy.app.timers.register(func, first_interval=timer_instance.frequency)
    timer_instance._timer_func = func
    logger.debug(f"_register_bpy_timer: registered '{timer_instance.timer_uid}' at {timer_instance.frequency:.3f}s")


def _unregister_bpy_timer(timer_instance: Timer_Instance) -> None:
    """Unregister the bpy.app.timers callable stored on the instance and clear the reference."""
    logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)

    if timer_instance._timer_func is None:
        return

    if bpy.app.timers.is_registered(timer_instance._timer_func):
        bpy.app.timers.unregister(timer_instance._timer_func)
        logger.debug(f"_unregister_bpy_timer: unregistered '{timer_instance.timer_uid}'")

    timer_instance._timer_func = None

# ==============================================================================================================================
# CLEAR / REBUILD

def _clear_all_timers(include_BL_data: bool = True) -> None:

    logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)

    rtc_timers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS)
    for timer_instance in rtc_timers:
        _unregister_bpy_timer(timer_instance)
        logger.debug(f"Torn down timer '{timer_instance.timer_uid}'")

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.TIMERS, [])

    if include_BL_data:
        timers_props = bpy.context.scene.dgblocks_timers_props
        timers_props.timer_mirror.clear()
        timers_props.timer_mirror_selected_idx = 0

    logger.debug("_clear_all_timers: complete")


def _rebuild_all_timers(event: Enum_Sync_Events, sync_BL: bool = True) -> None:
    """
    Full rebuild cycle:
        1. Clear existing bpy timers and Timer_Instance objects.
        2. Fire hook_get_timer_definitions — downstream blocks return Timer_Definition objects.
        3. Validate all collected definitions (uid uniqueness, frequency > 0, callable callback).
        4. Create Timer_Instance objects; auto-assign UIDs for blank definitions.
        5. Restore is_enabled from the BL timer_mirror (user preferences survive rebuilds).
        6. Register bpy.app.timers for each enabled instance.
        7. Sync BL timer_mirror rows to reflect the current live timer set.
    """
    logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
    logger.debug("_rebuild_all_timers: starting")

    _clear_all_timers()

    # Collect Timer_Definitions from all downstream blocks
    timers_from_blocks = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_get_timer_definitions,
        should_halt_on_exception=False,
    )
    list_timers_from_blocks = sum(timers_from_blocks.values(), [])  # order-preserving flat list
    inverted_timers_dict = {
        tdef.timer_uid: block_id
        for block_id, tdefs in timers_from_blocks.items()
        for tdef in tdefs
    }

    if len(list_timers_from_blocks) == 0:
        logger.info("_rebuild_all_timers: no Timer_Definitions returned, returning early")
        return

    validate_timer_definitions(list_timers_from_blocks)

    # Restore is_enabled from BL mirror (keyed by uid) so user toggle survives rebuilds
    timers_props = bpy.context.scene.dgblocks_timers_props
    bl_enabled_by_uid: dict = {
        row.timer_uid: row.is_enabled
        for row in timers_props.timer_mirror
    }

    # Build Timer_Instances
    rtc_timers = []
    auto_uid_counter = 0
    for tdef in list_timers_from_blocks:

        # Assign UID
        if tdef.timer_uid == "":
            uid = f"TIMER_{auto_uid_counter}"
            auto_uid_counter += 1
        else:
            uid = tdef.timer_uid

        source_block_id = inverted_timers_dict.get(tdef.timer_uid, "")

        # Restore is_enabled from BL mirror if available, otherwise default True
        is_enabled = bl_enabled_by_uid.get(uid, True)

        instance = Timer_Instance(
            timer_uid    = uid,
            src_block_id = source_block_id,
            frequency    = tdef.frequency,
            is_enabled   = is_enabled,
        )
        instance._callback = tdef.callback

        if instance.is_enabled:
            _register_bpy_timer(instance)

        rtc_timers.append(instance)
        logger.debug(
            f"Created Timer_Instance uid='{uid}' frequency={tdef.frequency:.3f}s "
            f"src='{source_block_id}' enabled={is_enabled}"
        )

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.TIMERS, rtc_timers)
    logger.info(f"_rebuild_all_timers: created {len(rtc_timers)} timer(s)")

    if sync_BL:
        FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_timers)
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event=Enum_Sync_Events,
            BL_is_truth_source=False,
            cache_key=cache_key_timers,
            FWC_instance=FWC_instance,
            data_mirror_instance=data_mirror_instance,
            actions_denied=set(),
            logger=logger,
        )

# ==============================================================================================================================
# UNIVERSAL TIMER CALLBACK — single hardcoded function used by all timers

def _universal_timer_callback(timer_instance: Timer_Instance) -> Optional[float]:
    """
    Single function executed by bpy.app.timers for every registered timer.
    Calls the callback stored on the Timer_Instance (sourced from the Timer_Definition).

    Returns:
        The timer's frequency in seconds to reschedule, or None to stop the timer.
    """
    logger = get_logger(Block_Loggers.TIMER_FIRE_EVENTS)

    # Guard: instance must still be in RTC (handles stale closures after a rebuild)
    cached_timers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS)
    if timer_instance not in cached_timers:
        logger.debug(
            f"_universal_timer_callback: '{timer_instance.timer_uid}' not found in RTC — stopping"
        )
        return None

    # Guard: disabled timers should not reschedule
    if not timer_instance.is_enabled:
        logger.debug(
            f"_universal_timer_callback: '{timer_instance.timer_uid}' is disabled — stopping"
        )
        return None

    try:
        timer_instance._callback(timer_instance)
        timer_instance.run_count += 1
        timer_instance.timer_error_str = None
        logger.debug(
            f"_universal_timer_callback: '{timer_instance.timer_uid}' fired "
            f"(run #{timer_instance.run_count})"
        )

    except Exception as e:
        timer_instance.timer_error_str = get_exception_last_n_lines(2, e)
        logger.error(f"_universal_timer_callback: exception in '{timer_instance.timer_uid}' ", exc_info = True)

    # Debug mode now lives on the owning block's record (toggled in core's All Blocks UIList)
    debug_mode = False
    try:
        block_records = Wrapper_Runtime_Cache.get_cache("REGISTRY_ALL_BLOCKS")
        for b in block_records or []:
            if b.block_id == "block-timers":
                debug_mode = b.debug_mode_enabled
                break
    except Exception:
        debug_mode = False

    if debug_mode:
        force_redraw_ui(bpy.context)

    return timer_instance.frequency

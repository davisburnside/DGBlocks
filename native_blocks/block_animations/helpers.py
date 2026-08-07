
import copy
import bpy
import numpy as np
from typing import Any, Optional

# Addon-level imports
from ...addon_helpers.data_structures import Enum_Sync_Events
from ...addon_helpers.generic_tools import force_redraw_ui

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_timers.data_structures import Timer_Definition
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager
from ..block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Animation_Instance,
    ANIM_DATA_TYPE_BATCH,
    ANIM_DATA_TYPE_UNIFORMS,
    ANIM_LOOP_PING_PONG,
    ANIM_LOOP_REPEAT,
)


# ==============================================================================================================================
# LERP
# ==============================================================================================================================

def _lerp(start: Any, end: Any, t: float) -> Any:
    """
    Linear interpolation between start and end at position t (0..1).
    Converts both operands to float32 numpy arrays for the computation,
    then returns a scalar float if the result is 0-dimensional, or a
    float32 ndarray otherwise.
    Falls back to returning end (t >= 1) or start (t < 1) on any error.
    """
    try:
        s = np.asarray(start, dtype=np.float32)
        e = np.asarray(end,   dtype=np.float32)
        result = s + (e - s) * np.float32(t)
        if result.ndim == 0:
            return float(result)
        return result
    except Exception:
        return end if t >= 1.0 else start

# ==============================================================================================================================
# SHADER STATE READ / WRITE
# ==============================================================================================================================

def _capture_start_state(shader, data_type: str, data_name: str) -> Any:
    """
    Read the current value of the animated attribute from a Shader_Instance.

    batch_data  → getattr(shader, data_name); numpy arrays are deep-copied.
    uniforms_data → shader.get_uniform(data_name) (returns None if never set).

    Returns None if the attribute does not exist or has not been set.
    """
    if data_type == ANIM_DATA_TYPE_BATCH:
        val = getattr(shader, data_name, None)
        if val is None:
            return None
        if isinstance(val, np.ndarray):
            return val.copy()
        return copy.deepcopy(val)

    elif data_type == ANIM_DATA_TYPE_UNIFORMS:
        return shader.get_uniform(data_name)

    return None


def _apply_lerp_to_shader(anim: Animation_Instance, shader) -> None:
    """
    Compute the lerped value for the current animation position and write it
    to the target shader attribute.

    batch_data    → setattr + _needs_new_batch = True
    uniforms_data → shader.set_uniform()  (also caches value in shader._uniforms)
    """
    t = min(anim._elapsed_time / anim.duration, 1.0) if anim.duration > 0 else 1.0
    lerped = _lerp(anim._start_state, anim.end_state, t)

    if anim.data_type == ANIM_DATA_TYPE_BATCH:
        setattr(shader, anim.data_name, lerped)
        shader._needs_new_batch = True

    elif anim.data_type == ANIM_DATA_TYPE_UNIFORMS:
        shader.set_uniform(anim.data_name, lerped)

    else:
        raise ValueError(
            f"Unknown data_type '{anim.data_type}' for animation '{anim.animation_uid}'. "
            f"Expected '{ANIM_DATA_TYPE_BATCH}' or '{ANIM_DATA_TYPE_UNIFORMS}'."
        )


def _revert_state(anim: Animation_Instance, shader) -> None:
    """
    Restore the shader attribute to the value captured at animation creation time.
    Called on cancel or unhandled tick exception.
    """
    if anim._start_state is None:
        return

    if anim.data_type == ANIM_DATA_TYPE_BATCH:
        setattr(shader, anim.data_name, anim._start_state)
        shader._needs_new_batch = True

    elif anim.data_type == ANIM_DATA_TYPE_UNIFORMS:
        shader.set_uniform(anim.data_name, anim._start_state)


def _handle_loop_boundary(anim: Animation_Instance, logger) -> bool:
    """
    Called when an animation reaches t >= 1.0.

    Returns True if the animation should now be treated as FINISHED, or False if
    it looped and should keep running.

    REPEAT    → carry the overshoot into the next cycle (so cycles never drift)
                and replay start -> end.
    PING_PONG → carry the overshoot and swap start/end, so the next cycle plays
                back the other way.

    loop_count == 0 means infinite; otherwise the animation finishes once
    loops_completed reaches loop_count.
    """
    if not anim.is_looping:
        return True

    # Carry the remainder so repeated cycles never accumulate rounding drift.
    if anim.duration > 0:
        anim._elapsed_time = max(0.0, (anim._elapsed_time - anim.duration) % anim.duration)
    else:
        anim._elapsed_time = 0.0

    anim.loops_completed += 1

    if anim.loop_mode == ANIM_LOOP_PING_PONG:
        anim._start_state, anim.end_state = anim.end_state, anim._start_state

    if anim._callback_after_loop is not None:
        try:
            anim._callback_after_loop(anim)
        except Exception:
            logger.error(
                f"callback_after_loop raised for '{anim.animation_uid}'",
                exc_info=True,
            )

    # loop_count == 0 → infinite
    if anim.loop_count and anim.loops_completed >= anim.loop_count:
        logger.debug(
            f"Animation '{anim.animation_uid}' exhausted loop_count "
            f"({anim.loop_count}) — finishing"
        )
        return True

    return False

# ==============================================================================================================================
# TIMER DEFINITIONS — returned to block_timers via hook_get_timer_definitions

# ==============================================================================================================================

def _get_timer_definitions_from_animations() -> list:
    """
    Build one Timer_Definition per unique framerate found in the active ANIMATIONS list.
    Called from the hook_get_timer_definitions subscriber in __init__.py.
    """
    cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
    seen_framerates: set = set()
    timer_defs = []

    for anim in cached:
        fr = anim.framerate
        if fr not in seen_framerates:
            seen_framerates.add(fr)
            # Use a default-arg capture to avoid the classic late-binding closure bug
            timer_defs.append(Timer_Definition(
                timer_uid = f"ANIM_TIMER_{fr}Hz",
                frequency = 1.0 / fr,
                callback  = lambda ti, framerate=fr: _tick_all_at_framerate(framerate, ti),
            ))

    return timer_defs

# ==============================================================================================================================
# TICK — the shared timer callback for all animations at a given framerate
# ==============================================================================================================================

def _tick_all_at_framerate(framerate: float, timer_instance) -> None:
    """
    Drives all active animations running at `framerate` Hz.

    Per-animation flow:
      1. Count down _delay_remaining; skip if still in delay.
      2. Advance _elapsed_time by dt.
      3. Apply the lerped value to the target shader.
      4. Fire callback_after_every_tick.
      5. If elapsed >= duration mark as finished.

    Post-loop cleanup:
      - Errored animations: revert shader state, remove from RTC, fire
        callback_after_interrupt.
      - Finished animations: remove from RTC first, then fire
        callback_after_finish (so looping is safe from inside the callback).
      - If no animations remain at this framerate: disable the timer and
        schedule a deferred timer rebuild to clean up the RTC timer entry.
    """
    logger = get_logger(Block_Loggers.ANIMATION_TICK_EVENTS)
    dt = 1.0 / framerate

    cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
    active = [
        a for a in cached
        if a.framerate == framerate
        and a.is_enabled
        and not a.is_paused
        and not a.is_finished
    ]

    finished: list = []
    errored:  list = []

    for anim in active:
        try:
            # ── delay countdown ──────────────────────────────────────────
            if anim._delay_remaining > 0.0:
                anim._delay_remaining = max(0.0, anim._delay_remaining - dt)
                if anim._delay_remaining > 0.0:
                    continue

            # ── advance elapsed time ──────────────────────────────────────
            anim._elapsed_time += dt

            # ── fetch shader ──────────────────────────────────────────────
            shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
            if shader is None:
                logger.warning(
                    f"_tick_all_at_framerate: shader '{anim.target_shader_uid}' "
                    f"not found — interrupting '{anim.animation_uid}'"
                )
                errored.append(anim)
                continue

            # ── apply lerp ────────────────────────────────────────────────
            _apply_lerp_to_shader(anim, shader)

            # ── per-tick callback ─────────────────────────────────────────
            if anim._callback_after_every_tick is not None:
                try:
                    anim._callback_after_every_tick(anim)
                except Exception:
                    logger.error(
                        f"callback_after_every_tick raised for '{anim.animation_uid}'",
                        exc_info=True,
                    )

            # ── completion / loop-boundary check ──────────────────────────
            t = min(anim._elapsed_time / anim.duration, 1.0) if anim.duration > 0 else 1.0
            if t >= 1.0:
                # Looping animations reset their phase here and keep running.
                if _handle_loop_boundary(anim, logger):
                    finished.append(anim)


        except Exception:
            logger.error(
                f"_tick_all_at_framerate: unhandled exception for '{anim.animation_uid}'",
                exc_info=True,
            )
            errored.append(anim)

    # ── process errored: revert, remove, interrupt callback ──────────────
    for anim in errored:
        if anim in cached:
            shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
            if shader is not None:
                _revert_state(anim, shader)
            cached.remove(anim)
            logger.debug(f"Removed errored animation '{anim.animation_uid}'")
            if anim._callback_after_interrupt is not None:
                try:
                    anim._callback_after_interrupt(anim)
                except Exception:
                    logger.error(
                        f"callback_after_interrupt raised for '{anim.animation_uid}'",
                        exc_info=True,
                    )

    # ── process finished: remove first, then finish callback ─────────────
    for anim in finished:
        if anim in cached:
            cached.remove(anim)
            logger.debug(f"Animation '{anim.animation_uid}' completed")

            # Opt-in only: by default an animation LANDS on end_state.
            if anim.revert_on_finish:
                shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
                if shader is not None:
                    _revert_state(anim, shader)

            if anim._callback_after_finish is not None:

                try:
                    anim._callback_after_finish(anim)
                except Exception:
                    logger.error(
                        f"callback_after_finish raised for '{anim.animation_uid}'",
                        exc_info=True,
                    )

    # ── auto-stop timer when framerate has no remaining animations ────────
    remaining_at_framerate = [
        a for a in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
        if a.framerate == framerate and not a.is_finished
    ]
    if not remaining_at_framerate:
        timer_instance.is_enabled = False
        logger.debug(
            f"No remaining animations at {framerate} Hz — "
            f"disabling timer, scheduling rebuild"
        )
        # Deferred rebuild so we don't mutate the RTC timer list while inside a timer callback
        bpy.app.timers.register(
            lambda: Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE),
            first_interval=0.01,
        )

    force_redraw_ui(bpy.context)

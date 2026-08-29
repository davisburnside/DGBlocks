
import copy
from typing import Any
import bpy
import numpy as np

# Addon-level imports
from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.generic_tools import force_redraw_ui

# Inter-block imports
from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...block_core.core_features.loggers.feature_wrapper import get_logger
from ...block_timers.data_structures import Timer_Definition
from ...block_timers.feature_timer_manager import Wrapper_Timer_Manager

# Intra-block imports
from ..common_declarations import Block_Loggers, Block_RTC_Members
from .constants import (
    ANIM_DATA_TYPE_BATCH,
    ANIM_DATA_TYPE_UNIFORMS,
    ANIM_EASE_EASE_OUT_BACK,
    ANIM_EASE_EASE_OUT_BOUNCE,
    ANIM_EASE_EASE_OUT_CIRC,
    ANIM_EASE_EASE_OUT_CUBIC,
    ANIM_EASE_EASE_OUT_ELASTIC,
    ANIM_EASE_EASE_OUT_EXPO,
    ANIM_EASE_EASE_OUT_QUAD,
    ANIM_EASE_EASE_OUT_QUART,
    ANIM_EASE_EASE_OUT_QUINT,
    ANIM_EASE_EASE_OUT_SINE,
    ANIM_EASE_LINEAR,
    ANIM_FORBIDDEN_DATA_NAME,
    ANIM_LOOP_PING_PONG,
    ANIM_VALID_EASINGS,
    ANIM_VALID_LOOP_MODES,
)
from .data_structures import Animation_Instance

# ==============================================================================================================================
# VALIDATION
# ==============================================================================================================================

def validate_animation_declaration(decl, logger) -> bool:
    """True when the declaration is structurally usable. Logs the reason when not."""

    if not decl.animation_uid:
        logger.error("animation_uid is empty, skipping")
        return False

    if decl.data_type not in (ANIM_DATA_TYPE_BATCH, ANIM_DATA_TYPE_UNIFORMS):
        logger.error(
            f"invalid data_type '{decl.data_type}' for '{decl.animation_uid}' — expected "
            f"'{ANIM_DATA_TYPE_BATCH}' or '{ANIM_DATA_TYPE_UNIFORMS}', skipping"
        )
        return False

    # Topology indices are integer lookups, not interpolatable values.
    if decl.data_type == ANIM_DATA_TYPE_BATCH and decl.data_name == ANIM_FORBIDDEN_DATA_NAME:
        logger.error(
            f"'{ANIM_FORBIDDEN_DATA_NAME}' cannot be animated "
            f"(requested by '{decl.animation_uid}'), skipping"
        )
        return False

    if decl.easing not in ANIM_VALID_EASINGS:
        logger.error(
            f"invalid easing '{decl.easing}' for '{decl.animation_uid}' — "
            f"expected one of {ANIM_VALID_EASINGS}, skipping"
        )
        return False

    if decl.loop_mode not in ANIM_VALID_LOOP_MODES:
        logger.error(
            f"invalid loop_mode '{decl.loop_mode}' for '{decl.animation_uid}' — "
            f"expected one of {ANIM_VALID_LOOP_MODES}, skipping"
        )
        return False

    if decl.loop_count < 0:
        logger.error(
            f"loop_count must be >= 0 for '{decl.animation_uid}' "
            f"(got {decl.loop_count}), skipping"
        )
        return False

    if decl.duration <= 0:
        logger.error(
            f"duration must be > 0 for '{decl.animation_uid}' (got {decl.duration}), skipping"
        )
        return False

    if decl.framerate <= 0:
        logger.error(
            f"framerate must be > 0 for '{decl.animation_uid}' (got {decl.framerate}), skipping"
        )
        return False

    return True

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
# EASING — transforms the raw linear time fraction (t) before it reaches _lerp
# ==============================================================================================================================

def _ease_out_bounce(t: float) -> float:
    """Standard 'ease out bounce': overshoots into a series of decaying bounces that land
    exactly on 1.0 at t=1.0. Input/output both in [0, 1]."""
    n1, d1 = 7.5625, 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    t -= 1.0
    return 1.0 + c3 * t ** 3 + c1 * t ** 2


def _ease_out_elastic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    c4 = (2.0 * np.pi) / 3.0
    return 2.0 ** (-10.0 * t) * np.sin((t * 10.0 - 0.75) * c4) + 1.0


# One "Out" curve per easings.net family — the "essentials" subset (Out reads best for UI
# motion). Formulas per https://easings.net/.
_EASING_FUNCS = {
    ANIM_EASE_LINEAR:           lambda t: t,
    ANIM_EASE_EASE_OUT_SINE:    lambda t: np.sin((t * np.pi) / 2.0),
    ANIM_EASE_EASE_OUT_QUAD:    lambda t: 1.0 - (1.0 - t) ** 2,
    ANIM_EASE_EASE_OUT_CUBIC:   lambda t: 1.0 - (1.0 - t) ** 3,
    ANIM_EASE_EASE_OUT_QUART:   lambda t: 1.0 - (1.0 - t) ** 4,
    ANIM_EASE_EASE_OUT_QUINT:   lambda t: 1.0 - (1.0 - t) ** 5,
    ANIM_EASE_EASE_OUT_EXPO:    lambda t: 1.0 if t >= 1.0 else 1.0 - 2.0 ** (-10.0 * t),
    ANIM_EASE_EASE_OUT_CIRC:    lambda t: np.sqrt(1.0 - (t - 1.0) ** 2),
    ANIM_EASE_EASE_OUT_BACK:    _ease_out_back,
    ANIM_EASE_EASE_OUT_ELASTIC: _ease_out_elastic,
    ANIM_EASE_EASE_OUT_BOUNCE:  _ease_out_bounce,
}


def _apply_easing(easing: str, t: float) -> float:
    """Maps the raw linear t (0..1) through the named easing curve. Unknown names fall back
    to linear — validate_animation_declaration() is what actually rejects those upfront."""
    return _EASING_FUNCS.get(easing, _EASING_FUNCS[ANIM_EASE_LINEAR])(t)

# ==============================================================================================================================
# SHADER STATE READ / WRITE
# ==============================================================================================================================


def capture_start_state(shader, data_type: str, data_name: str) -> Any:
    """
    Read the current value of the animated attribute from a Shader_Instance.

    batch_data    -> getattr(shader, data_name); numpy arrays are deep-copied.
    uniforms_data -> shader.get_uniform(data_name) (returns None if never set).

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

    batch_data    -> setattr + _needs_new_batch = True
    uniforms_data -> shader.set_uniform() (also caches value in shader._uniforms)
    """
    t = min(anim._elapsed_time / anim.duration, 1.0) if anim.duration > 0 else 1.0
    lerped = _lerp(anim._start_state, anim.end_state, _apply_easing(anim.easing, t))

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


def revert_state(anim: Animation_Instance, shader) -> None:
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

    REPEAT    -> carry the overshoot into the next cycle (so cycles never drift)
                 and replay start -> end.
    PING_PONG -> carry the overshoot and swap start/end, so the next cycle plays
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

    # loop_count == 0 -> infinite
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


_timer_rebuild_suppressed = False


class suppress_timer_rebuilds:
    """
    Context manager that batches timer rebuilds.

    Applying N declared animations would otherwise call request_timer_rebuild()
    up to N times, and each rebuild re-fires hook_get_timer_definitions across
    every block. Wrap a bulk apply in this and issue a single rebuild afterwards.
    """

    def __enter__(self):
        global _timer_rebuild_suppressed
        self._previous = _timer_rebuild_suppressed
        _timer_rebuild_suppressed = True
        return self

    def __exit__(self, *exc_info):
        global _timer_rebuild_suppressed
        _timer_rebuild_suppressed = self._previous
        return False


def request_timer_rebuild_unless_suppressed() -> None:
    """Single choke point for every animation-driven timer rebuild request."""
    if _timer_rebuild_suppressed:
        return
    Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)


def iter_all_animations():
    """
    Yield (shader, animation) for every animation owned by every live shader.
    Animations are stored on their shader, so the SHADERS cache is the only
    registry that needs walking.
    """
    cached_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS) or []
    for shader in cached_shaders:
        # list() so callers may mutate shader._animations while iterating
        for anim in list(shader._animations.values()):
            yield shader, anim


def get_timer_definitions_from_animations() -> list:
    """
    Build one Timer_Definition per unique framerate found across all shader-owned
    animations. Called from the hook_get_timer_definitions subscriber in __init__.py.
    """
    seen_framerates: set = set()
    timer_defs = []

    for _shader, anim in iter_all_animations():
        fr = anim.framerate
        if fr not in seen_framerates:
            seen_framerates.add(fr)
            # Default-arg capture avoids the classic late-binding closure bug
            timer_defs.append(Timer_Definition(
                timer_uid = f"ANIM_TIMER_{fr}Hz",
                frequency = 1.0 / fr,
                callback  = lambda ti, framerate=fr: tick_all_at_framerate(framerate, ti),
            ))

    return timer_defs

# ==============================================================================================================================
# TICK — the shared timer callback for all animations at a given framerate
# ==============================================================================================================================


def tick_all_at_framerate(framerate: float, timer_instance) -> None:
    """
    Drives all active animations running at `framerate` Hz.

    Per-animation flow:
      1. Count down _delay_remaining; skip if still in delay.
      2. Advance _elapsed_time by dt.
      3. Apply the lerped value to the owning shader.
      4. Fire callback_after_every_tick.
      5. If elapsed >= duration, handle the loop boundary / finish.

    Post-loop cleanup:
      - Errored animations: revert shader state, detach, fire callback_after_interrupt.
      - Finished animations: detach first, then fire callback_after_finish (so
        re-adding an animation from inside the callback is safe).
      - If no animations remain at this framerate: disable the timer and schedule
        a deferred rebuild to clean up the RTC timer entry.

    Because each animation is owned by its shader, there is no uid lookup and no
    "shader not found" case — a destroyed shader takes its animations with it.
    """
    logger = get_logger(Block_Loggers.ANIMATION_TICK_EVENTS)
    dt = 1.0 / framerate

    # (shader, anim) pairs so cleanup can detach from the correct owner
    active = [
        (shader, anim)
        for shader, anim in iter_all_animations()
        if anim.framerate == framerate
        and anim.is_enabled
        and not anim.is_paused
        and not anim.is_finished
    ]

    finished: list = []
    errored:  list = []

    for shader, anim in active:
        try:
            # ── delay countdown ───────────────────────────────────────────
            if anim._delay_remaining > 0.0:
                anim._delay_remaining = max(0.0, anim._delay_remaining - dt)
                if anim._delay_remaining > 0.0:
                    continue

            # ── advance elapsed time ──────────────────────────────────────
            anim._elapsed_time += dt

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
                    finished.append((shader, anim))

        except Exception:
            logger.error(
                f"tick_all_at_framerate: unhandled exception for '{anim.animation_uid}' "
                f"on shader '{shader.shader_uid}'",
                exc_info=True,
            )
            errored.append((shader, anim))

    # ── process errored: revert, detach, interrupt callback ───────────────
    for shader, anim in errored:
        if shader._animations.pop(anim.animation_uid, None) is None:
            continue
        revert_state(anim, shader)
        logger.debug(
            f"Removed errored animation '{anim.animation_uid}' from '{shader.shader_uid}'"
        )
        if anim._callback_after_interrupt is not None:
            try:
                anim._callback_after_interrupt(anim)
            except Exception:
                logger.error(
                    f"callback_after_interrupt raised for '{anim.animation_uid}'",
                    exc_info=True,
                )

    # ── process finished: detach first, then finish callback ──────────────
    for shader, anim in finished:
        if shader._animations.pop(anim.animation_uid, None) is None:
            continue
        logger.debug(f"Animation '{anim.animation_uid}' on '{shader.shader_uid}' completed")

        # Opt-in only: by default an animation LANDS on end_state.
        if anim.revert_on_finish:
            revert_state(anim, shader)

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
        a for _s, a in iter_all_animations()
        if a.framerate == framerate and not a.is_finished
    ]
    if not remaining_at_framerate:
        timer_instance.is_enabled = False
        logger.debug(
            f"No remaining animations at {framerate} Hz — disabling timer, scheduling rebuild"
        )
        # Deferred rebuild so we don't mutate the RTC timer list from inside a timer callback
        bpy.app.timers.register(
            lambda: Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE),
            first_interval=0.01,
        )

    force_redraw_ui(bpy.context)

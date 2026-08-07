
# Addon-level imports
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager
from ..block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Animation_Declaration,
    Animation_Instance,
    ANIM_DATA_TYPE_BATCH,
    ANIM_DATA_TYPE_UNIFORMS,
    ANIM_FORBIDDEN_DATA_NAME,
    ANIM_LOOP_ONCE,
    ANIM_LOOP_PING_PONG,
    ANIM_LOOP_REPEAT,
)
from .helpers import _capture_start_state, _revert_state

_VALID_LOOP_MODES = (ANIM_LOOP_ONCE, ANIM_LOOP_REPEAT, ANIM_LOOP_PING_PONG)


class Wrapper_Animation_Manager(Abstract_Feature_Wrapper):

    # ----------------------------------------------------------
    # Internal helpers

    @classmethod
    def _validate_declaration(cls, decl, logger) -> bool:
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

        if decl.loop_mode not in _VALID_LOOP_MODES:
            logger.error(
                f"invalid loop_mode '{decl.loop_mode}' for '{decl.animation_uid}' — "
                f"expected one of {_VALID_LOOP_MODES}, skipping"
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

    @classmethod
    def _resolve_start_state(cls, decl, shader, logger):
        """Explicit start_state wins; otherwise read the live value off the shader."""

        if decl.start_state is not None:
            return decl.start_state

        start_state = _capture_start_state(shader, decl.data_type, decl.data_name)
        if start_state is None:
            logger.error(
                f"could not auto-capture start_state for '{decl.animation_uid}' "
                f"(data_type='{decl.data_type}', data_name='{decl.data_name}'). "
                f"Provide an explicit start_state in the declaration."
            )
        return start_state

    @classmethod
    def _build_instance(cls, decl, start_state) -> Animation_Instance:

        instance = Animation_Instance(
            animation_uid     = decl.animation_uid,
            target_shader_uid = decl.target_shader_uid,
            data_type         = decl.data_type,
            data_name         = decl.data_name,
            end_state         = decl.end_state,
            delay_start       = decl.delay_start,
            duration          = decl.duration,
            framerate         = decl.framerate,
            loop_mode         = decl.loop_mode,
            loop_count        = decl.loop_count,
            revert_on_finish  = decl.revert_on_finish,
        )
        instance._start_state               = start_state
        instance._delay_remaining           = decl.delay_start
        instance._callback_after_every_tick = decl.callback_after_every_tick
        instance._callback_after_loop       = decl.callback_after_loop
        instance._callback_after_finish     = decl.callback_after_finish
        instance._callback_after_interrupt  = decl.callback_after_interrupt
        return instance

    # ----------------------------------------------------------
    # Public API


    @classmethod
    def add_animations(cls, declarations: list) -> None:
        """
        Create Animation_Instance objects from a list of Animation_Declarations and
        store them in the RTC.

        For each declaration:
          - Validates data_type, duration, framerate, and uid uniqueness.
          - Fetches the target Shader_Instance; skips the declaration if not found.
          - Captures start_state automatically from the shader (or uses the caller-
            supplied value if provided).
          - Creates and stores an Animation_Instance in Block_RTC_Members.ANIMATIONS.

        If any new framerate is introduced, triggers a timer rebuild via
        Wrapper_Timer_Manager.request_timer_rebuild() so block_timers picks up the
        new Timer_Definitions returned by hook_get_timer_definitions.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)

        existing_uids       = {a.animation_uid for a in cached}
        existing_framerates = {a.framerate for a in cached}
        new_framerates: set = set()

        for decl in declarations:
            if not decl.enabled:
                logger.debug(f"add_animations: skipping disabled declaration '{decl.animation_uid}'")
                continue

            # ── validation ────────────────────────────────────────────────
            if not cls._validate_declaration(decl, logger):
                continue

            if decl.animation_uid in existing_uids:
                logger.warning(
                    f"add_animations: animation_uid '{decl.animation_uid}' is already active — "
                    f"skipping. Use set_animation() to update a live animation in place."
                )
                continue

            # ── fetch target shader ───────────────────────────────────────
            shader = Wrapper_Shader_Manager.get_shader(decl.target_shader_uid)
            if shader is None:
                logger.error(
                    f"add_animations: shader '{decl.target_shader_uid}' not found — "
                    f"skipping animation '{decl.animation_uid}'"
                )
                continue

            # ── capture start state ───────────────────────────────────────
            start_state = cls._resolve_start_state(decl, shader, logger)
            if start_state is None:
                continue

            # ── build instance ────────────────────────────────────────────
            cached.append(cls._build_instance(decl, start_state))

            existing_uids.add(decl.animation_uid)

            if decl.framerate not in existing_framerates:
                new_framerates.add(decl.framerate)
                existing_framerates.add(decl.framerate)

            logger.debug(
                f"add_animations: created '{decl.animation_uid}' "
                f"target='{decl.target_shader_uid}' data_type='{decl.data_type}' "
                f"data_name='{decl.data_name}' duration={decl.duration:.2f}s "
                f"framerate={decl.framerate}Hz delay={decl.delay_start:.3f}s"
            )

        # ── trigger timer rebuild for any newly required framerates ───────
        if new_framerates:
            logger.debug(
                f"add_animations: new framerates {new_framerates} — requesting timer rebuild"
            )
            Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)

    @classmethod
    def set_animation(cls, declaration) -> None:
        """
        Upsert a single animation — the one call to reach for whenever the data
        being animated changes.

        If `declaration.animation_uid` is not active, this behaves exactly like
        add_animations([declaration]).

        If it IS active, the live instance is updated IN PLACE and its phase
        (_elapsed_time) is preserved, so swapping in a new point/color set never
        produces a visual jump — the animation simply continues from wherever it
        was with the new data. This is what makes a looping "pulse" seamless
        across data changes.

        Notes
        -----
        - start_state=None re-captures from the shader on CREATE only. For an
          update, leaving it None keeps the existing start_state, because
          re-capturing mid-lerp would read a half-interpolated value.
        - delay_start is not re-applied on update (the animation is already running).
        - Changing framerate triggers a timer rebuild.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)

        existing = next(
            (a for a in cached if a.animation_uid == declaration.animation_uid), None
        )
        if existing is None:
            cls.add_animations([declaration])
            return

        if not cls._validate_declaration(declaration, logger):
            return

        old_framerate = existing.framerate

        existing.target_shader_uid = declaration.target_shader_uid
        existing.data_type         = declaration.data_type
        existing.data_name         = declaration.data_name
        existing.end_state         = declaration.end_state
        existing.duration          = declaration.duration
        existing.framerate         = declaration.framerate
        existing.loop_mode         = declaration.loop_mode
        existing.loop_count        = declaration.loop_count
        existing.revert_on_finish  = declaration.revert_on_finish
        existing.is_enabled        = declaration.enabled

        if declaration.start_state is not None:
            existing._start_state = declaration.start_state

        existing._callback_after_every_tick = declaration.callback_after_every_tick
        existing._callback_after_loop       = declaration.callback_after_loop
        existing._callback_after_finish     = declaration.callback_after_finish
        existing._callback_after_interrupt  = declaration.callback_after_interrupt

        # Phase is preserved, but a shortened duration could leave elapsed past the end.
        if existing._elapsed_time > existing.duration:
            existing._elapsed_time = existing._elapsed_time % existing.duration

        logger.debug(
            f"set_animation: updated '{existing.animation_uid}' in place "
            f"(phase preserved at {existing.completion_factor:.3f})"
        )

        if declaration.framerate != old_framerate:
            logger.debug(
                f"set_animation: framerate changed {old_framerate} -> {declaration.framerate} "
                f"— requesting timer rebuild"
            )
            Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)

    @classmethod
    def update_animation(cls, uid: str, **fields) -> None:
        """
        Patch individual fields on a live animation, preserving its phase.

        Accepts any Animation_Instance field, plus the convenience aliases
        `start_state` and the callback names used by Animation_Declaration.
        Logs a warning and does nothing if `uid` is not active — use
        set_animation() when the animation may or may not exist yet.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)

        anim = next((a for a in cached if a.animation_uid == uid), None)
        if anim is None:
            logger.warning(
                f"update_animation: animation '{uid}' not found in RTC — "
                f"use set_animation() to create it"
            )
            return

        _ALIASES = {
            "start_state":               "_start_state",
            "callback_after_every_tick": "_callback_after_every_tick",
            "callback_after_loop":       "_callback_after_loop",
            "callback_after_finish":     "_callback_after_finish",
            "callback_after_interrupt":  "_callback_after_interrupt",
        }

        old_framerate = anim.framerate

        for name, value in fields.items():
            attr = _ALIASES.get(name, name)
            if not hasattr(anim, attr):
                logger.error(f"update_animation: '{uid}' has no field '{name}', ignoring")
                continue
            if attr == "data_name" and value == ANIM_FORBIDDEN_DATA_NAME:
                logger.error(
                    f"update_animation: '{ANIM_FORBIDDEN_DATA_NAME}' cannot be animated "
                    f"(requested by '{uid}'), ignoring"
                )
                continue
            setattr(anim, attr, value)

        if anim.duration > 0 and anim._elapsed_time > anim.duration:
            anim._elapsed_time = anim._elapsed_time % anim.duration

        logger.debug(f"update_animation: patched '{uid}' fields {list(fields.keys())}")

        if anim.framerate != old_framerate:
            Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)

    @classmethod
    def get_animation(cls, uid: str):
        """Return the live Animation_Instance for uid, or None."""
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
        return next((a for a in cached if a.animation_uid == uid), None)

    @classmethod
    def has_animation(cls, uid: str) -> bool:
        """True when an animation with this uid is currently active."""
        return cls.get_animation(uid) is not None

    @classmethod
    def pause_animation(cls, uid: str) -> None:

        """
        Toggle is_paused on the Animation_Instance matching uid.
        While paused, the elapsed time and delay countdown freeze; the shader is
        not updated.  The timer continues firing (other animations at the same
        framerate are unaffected).
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
        for anim in cached:
            if anim.animation_uid == uid:
                anim.is_paused = not anim.is_paused
                state = "paused" if anim.is_paused else "resumed"
                logger.debug(f"pause_animation: '{uid}' {state}")
                return
        logger.warning(f"pause_animation: animation '{uid}' not found in RTC")

    @classmethod
    def cancel_animation(cls, uid: str, revert: bool = True) -> None:
        """
        Immediately remove an animation from the RTC — the interrupt entry point.

        Steps:
          1. If `revert` (default), restore the target shader attribute to the value
             captured at creation. Pass revert=False to freeze the shader at whatever
             value the animation last wrote.
          2. Remove the Animation_Instance from the RTC.
          3. Fire callback_after_interrupt (if set).
          4. If this was the last animation at its framerate, trigger a timer rebuild
             so the now-unused timer is cleaned up.
        """

        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)

        anim = next((a for a in cached if a.animation_uid == uid), None)
        if anim is None:
            logger.warning(f"cancel_animation: animation '{uid}' not found in RTC")
            return

        framerate = anim.framerate

        # Revert shader state
        if revert:
            shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
            if shader is not None:
                _revert_state(anim, shader)

        # Remove from RTC
        cached.remove(anim)
        logger.debug(f"cancel_animation: cancelled '{uid}' (revert={revert})")


        # Interrupt callback
        if anim._callback_after_interrupt is not None:
            try:
                anim._callback_after_interrupt(anim)
            except Exception:
                logger.error(
                    f"cancel_animation: callback_after_interrupt raised for '{uid}'",
                    exc_info=True,
                )

        # Clean up timer if framerate no longer needed
        remaining = [a for a in cached if a.framerate == framerate]
        if not remaining:
            logger.debug(
                f"cancel_animation: no remaining animations at {framerate} Hz — "
                f"requesting timer rebuild"
            )
            Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)

    @classmethod
    def get_active_animations(cls) -> list:
        """Return a snapshot list of all current Animation_Instance objects in the RTC."""
        return list(Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS))

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        logger.debug("Wrapper_Animation_Manager._init_wrapper")
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.ANIMATIONS, [])
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        """
        Cancel all active animations (reverts shader state) and clear the RTC list.
        No callbacks are fired during shutdown.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
        logger.debug("Wrapper_Animation_Manager._remove_wrapper — cancelling all animations")

        cached = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.ANIMATIONS)
        for anim in list(cached):
            shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
            if shader is not None:
                _revert_state(anim, shader)

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.ANIMATIONS, [])

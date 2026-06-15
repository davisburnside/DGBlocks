
# Addon-level imports
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager
from ..block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import Animation_Declaration, Animation_Instance, ANIM_DATA_TYPE_BATCH, ANIM_DATA_TYPE_UNIFORMS
from .helpers import _capture_start_state, _revert_state


class Wrapper_Animation_Manager(Abstract_Feature_Wrapper):

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
            if not decl.animation_uid:
                logger.error("add_animations: animation_uid is empty, skipping")
                continue

            if decl.animation_uid in existing_uids:
                logger.warning(
                    f"add_animations: animation_uid '{decl.animation_uid}' is already active, skipping"
                )
                continue

            if decl.data_type not in (ANIM_DATA_TYPE_BATCH, ANIM_DATA_TYPE_UNIFORMS):
                logger.error(
                    f"add_animations: invalid data_type '{decl.data_type}' for "
                    f"'{decl.animation_uid}' — expected '{ANIM_DATA_TYPE_BATCH}' or "
                    f"'{ANIM_DATA_TYPE_UNIFORMS}', skipping"
                )
                continue

            if decl.duration <= 0:
                logger.error(
                    f"add_animations: duration must be > 0 for '{decl.animation_uid}' "
                    f"(got {decl.duration}), skipping"
                )
                continue

            if decl.framerate <= 0:
                logger.error(
                    f"add_animations: framerate must be > 0 for '{decl.animation_uid}' "
                    f"(got {decl.framerate}), skipping"
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
            if decl.start_state is not None:
                start_state = decl.start_state
            else:
                start_state = _capture_start_state(shader, decl.data_type, decl.data_name)
                if start_state is None:
                    logger.error(
                        f"add_animations: could not auto-capture start_state for "
                        f"'{decl.animation_uid}' (data_type='{decl.data_type}', "
                        f"data_name='{decl.data_name}'). "
                        f"Provide an explicit start_state in the declaration."
                    )
                    continue

            # ── build instance ────────────────────────────────────────────
            instance = Animation_Instance(
                animation_uid     = decl.animation_uid,
                target_shader_uid = decl.target_shader_uid,
                data_type         = decl.data_type,
                data_name         = decl.data_name,
                end_state         = decl.end_state,
                delay_start       = decl.delay_start,
                duration          = decl.duration,
                framerate         = decl.framerate,
            )
            instance._start_state               = start_state
            instance._delay_remaining           = decl.delay_start
            instance._callback_after_every_tick = decl.callback_after_every_tick
            instance._callback_after_finish     = decl.callback_after_finish
            instance._callback_after_interrupt  = decl.callback_after_interrupt

            cached.append(instance)
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
    def cancel_animation(cls, uid: str) -> None:
        """
        Immediately remove an animation from the RTC.

        Steps:
          1. Revert the target shader attribute to the value captured at creation.
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
        shader = Wrapper_Shader_Manager.get_shader(anim.target_shader_uid)
        if shader is not None:
            _revert_state(anim, shader)

        # Remove from RTC
        cached.remove(anim)
        logger.debug(f"cancel_animation: cancelled '{uid}'")

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

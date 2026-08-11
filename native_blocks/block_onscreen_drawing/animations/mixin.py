
from typing import Optional

# Inter-block imports
from ...block_core.core_features.loggers.feature_wrapper import get_logger

# Intra-block imports
from ..common_declarations import Block_Loggers
from .constants import ANIM_FORBIDDEN_DATA_NAME
from .data_structures import Animation_Instance
from .engine import (
    capture_start_state,
    request_timer_rebuild_unless_suppressed,
    revert_state,
    validate_animation_declaration,
)


class Animatable_Mixin:
    """
    Gives a Shader_Instance the ability to own and drive its own animations.

    Animations live in `self._animations` (uid -> Animation_Instance), which is
    declared as a field on Shader_Instance. Because the animations are owned by
    the shader, they are destroyed automatically when the shader is — there is no
    orphan-cleanup pass and no global animation registry.

    UIDs are scoped per shader: two different shaders may each own an animation
    called "pulse" without collision.
    """

    # ----------------------------------------------------------
    # Internal helpers

    def _build_animation_instance(self, decl, start_state) -> Animation_Instance:

        instance = Animation_Instance(
            animation_uid    = decl.animation_uid,
            data_type        = decl.data_type,
            data_name        = decl.data_name,
            end_state        = decl.end_state,
            delay_start      = decl.delay_start,
            duration         = decl.duration,
            framerate        = decl.framerate,
            loop_mode        = decl.loop_mode,
            loop_count       = decl.loop_count,
            revert_on_finish = decl.revert_on_finish,
        )
        instance._start_state               = start_state
        instance._delay_remaining           = decl.delay_start
        instance._callback_after_every_tick = decl.callback_after_every_tick
        instance._callback_after_loop       = decl.callback_after_loop
        instance._callback_after_finish     = decl.callback_after_finish
        instance._callback_after_interrupt  = decl.callback_after_interrupt
        return instance

    def _resolve_animation_start_state(self, decl, logger):
        """Explicit start_state wins; otherwise read the live value off this shader."""

        if decl.start_state is not None:
            return decl.start_state

        start_state = capture_start_state(self, decl.data_type, decl.data_name)
        if start_state is None:
            logger.error(
                f"could not auto-capture start_state for '{decl.animation_uid}' on shader "
                f"'{self.shader_uid}' (data_type='{decl.data_type}', "
                f"data_name='{decl.data_name}'). Provide an explicit start_state, or ensure "
                f"the shader data is populated before the animation is created."
            )
        return start_state

    # ----------------------------------------------------------
    # Public API

    def add_animation(self, declaration) -> None:
        """
        Create a new animation on this shader.

        Validates the declaration, captures start_state (from the declaration or
        live off this shader), and stores the Animation_Instance. Does nothing if
        an animation with this uid is already active on this shader — use
        set_animation() to upsert instead.

        Requests a timer rebuild when the animation introduces a new framerate.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)

        if not declaration.enabled:
            logger.debug(
                f"add_animation: skipping disabled declaration '{declaration.animation_uid}'"
            )
            return

        if not validate_animation_declaration(declaration, logger):
            return

        if declaration.animation_uid in self._animations:
            logger.warning(
                f"add_animation: '{declaration.animation_uid}' is already active on shader "
                f"'{self.shader_uid}' — skipping. Use set_animation() to update it in place."
            )
            return

        start_state = self._resolve_animation_start_state(declaration, logger)
        if start_state is None:
            return

        known_framerates = {a.framerate for a in self._animations.values()}
        self._animations[declaration.animation_uid] = self._build_animation_instance(
            declaration, start_state
        )

        logger.debug(
            f"add_animation: created '{declaration.animation_uid}' on '{self.shader_uid}' "
            f"data_type='{declaration.data_type}' data_name='{declaration.data_name}' "
            f"duration={declaration.duration:.2f}s framerate={declaration.framerate}Hz "
            f"delay={declaration.delay_start:.3f}s"
        )

        if declaration.framerate not in known_framerates:
            request_timer_rebuild_unless_suppressed()

    def set_animation(self, declaration) -> None:
        """
        Upsert an animation — the call to reach for whenever the data being
        animated changes.

        If the uid is not active on this shader, behaves exactly like add_animation().

        If it IS active, the live instance is updated IN PLACE and its phase
        (_elapsed_time) is preserved, so swapping in a new point/color set never
        produces a visual jump — the animation simply continues from wherever it
        was with the new data. This is what makes a looping "pulse" seamless
        across data changes.

        Notes
        -----
        - start_state=None re-captures from the shader on CREATE only. On update it
          keeps the existing start_state, because re-capturing mid-lerp would read
          a half-interpolated value.
        - delay_start is not re-applied on update (the animation is already running).
        - Changing framerate triggers a timer rebuild.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)

        existing = self._animations.get(declaration.animation_uid)
        if existing is None:
            self.add_animation(declaration)
            return

        if not validate_animation_declaration(declaration, logger):
            return

        old_framerate = existing.framerate

        existing.data_type        = declaration.data_type
        existing.data_name        = declaration.data_name
        existing.end_state        = declaration.end_state
        existing.duration         = declaration.duration
        existing.framerate        = declaration.framerate
        existing.loop_mode        = declaration.loop_mode
        existing.loop_count       = declaration.loop_count
        existing.revert_on_finish = declaration.revert_on_finish
        existing.is_enabled       = declaration.enabled

        if declaration.start_state is not None:
            existing._start_state = declaration.start_state

        existing._callback_after_every_tick = declaration.callback_after_every_tick
        existing._callback_after_loop       = declaration.callback_after_loop
        existing._callback_after_finish     = declaration.callback_after_finish
        existing._callback_after_interrupt  = declaration.callback_after_interrupt

        # Phase is preserved, but a shortened duration could leave elapsed past the end.
        if existing.duration > 0 and existing._elapsed_time > existing.duration:
            existing._elapsed_time = existing._elapsed_time % existing.duration

        logger.debug(
            f"set_animation: updated '{existing.animation_uid}' on '{self.shader_uid}' "
            f"in place (phase preserved at {existing.completion_factor:.3f})"
        )

        if declaration.framerate != old_framerate:
            request_timer_rebuild_unless_suppressed()

    def update_animation(self, uid: str, **fields) -> None:
        """
        Patch individual fields on a live animation of this shader, preserving phase.

        Accepts any Animation_Instance field, plus the convenience aliases
        `start_state` and the callback names used by Animation_Declaration.
        Logs a warning and does nothing if `uid` is not active — use
        set_animation() when the animation may or may not exist yet.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)

        anim = self._animations.get(uid)
        if anim is None:
            logger.warning(
                f"update_animation: '{uid}' not found on shader '{self.shader_uid}' — "
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
            request_timer_rebuild_unless_suppressed()

    def get_animation(self, uid: str) -> Optional[Animation_Instance]:
        """Return the live Animation_Instance for uid on this shader, or None."""
        return self._animations.get(uid)

    def has_animation(self, uid: str) -> bool:
        """True when an animation with this uid is currently active on this shader."""
        return uid in self._animations

    def get_active_animations(self) -> list:
        """Return a snapshot list of all Animation_Instance objects on this shader."""
        return list(self._animations.values())

    def pause_animation(self, uid: str) -> None:
        """
        Toggle is_paused on the matching animation of this shader.
        While paused, elapsed time and the delay countdown freeze and the shader is
        not updated. The timer keeps firing (other animations are unaffected).
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)

        anim = self._animations.get(uid)
        if anim is None:
            logger.warning(f"pause_animation: '{uid}' not found on shader '{self.shader_uid}'")
            return

        anim.is_paused = not anim.is_paused
        logger.debug(
            f"pause_animation: '{uid}' {'paused' if anim.is_paused else 'resumed'}"
        )

    def cancel_animation(self, uid: str, revert: bool = True) -> None:
        """
        Immediately remove an animation from this shader — the interrupt entry point.

        Steps:
          1. If `revert` (default), restore the animated attribute to the value
             captured at creation. Pass revert=False to freeze the shader at
             whatever value the animation last wrote.
          2. Detach the Animation_Instance from this shader.
          3. Fire callback_after_interrupt (if set).
          4. If this was the last animation at its framerate, request a timer
             rebuild so the now-unused timer is cleaned up.

        This is the only way to stop an infinite (loop_count=0) looping animation.
        """
        logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)

        anim = self._animations.pop(uid, None)
        if anim is None:
            logger.warning(f"cancel_animation: '{uid}' not found on shader '{self.shader_uid}'")
            return

        if revert:
            revert_state(anim, self)

        logger.debug(
            f"cancel_animation: cancelled '{uid}' on '{self.shader_uid}' (revert={revert})"
        )

        if anim._callback_after_interrupt is not None:
            try:
                anim._callback_after_interrupt(anim)
            except Exception:
                logger.error(
                    f"cancel_animation: callback_after_interrupt raised for '{uid}'",
                    exc_info=True,
                )

        # Clean up the timer if this shader no longer needs that framerate.
        # Other shaders may still be using it; the tick loop disables the timer
        # itself once no animation anywhere is left at that framerate.
        if not any(a.framerate == anim.framerate for a in self._animations.values()):
            request_timer_rebuild_unless_suppressed()

    def cancel_all_animations(self, revert: bool = True) -> None:
        """Cancel every animation on this shader. Used during shader teardown."""
        for uid in list(self._animations.keys()):
            self.cancel_animation(uid, revert=revert)


from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .constants import ANIM_LOOP_ONCE, ANIM_LOOP_PING_PONG, ANIM_LOOP_REPEAT

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================


@dataclass
class Animation_Declaration:
    """
    Flat descriptor for a single animation.

    Animations are owned by the Shader_Instance they drive, so there is no
    target_shader_uid field — the target is whichever shader the declaration is
    applied to. Two ways to apply one:

      1. Declaratively, via Shader_Definition.animations. These are re-created
         automatically on every shader rebuild (undo/redo, debug toggles, etc).
      2. Imperatively, via shader.set_animation(declaration). These live only as
         long as the shader instance does.

    Fields
    ------
    animation_uid       Unique string identifier WITHIN the owning shader. Two
                        different shaders may each have an animation named "pulse".

    data_type           'uniforms_data' or 'batch_data'.
                        uniforms_data -> calls shader.set_uniform(data_name, value) each tick.
                        batch_data    -> writes directly to shader.<data_name> and sets
                                        _needs_new_batch = True each tick.
    data_name           For batch_data: the Python attribute name on the Shader_Instance,
                          e.g. '_points', '_colors', '_sizes'.
                        For uniforms_data: the uniform name string, e.g. 'color', 'alpha'.
    end_state           Target value the animation lerps toward. Must share dtype / shape
                        with the captured start_state.
    start_state         Optional explicit start value. If None (default), the value is
                        auto-captured from the shader via getattr / get_uniform at
                        creation time.
    delay_start         Seconds to wait before the lerp begins (default 0).
    duration            Seconds for the full lerp from start to end (default 1.0).
    framerate           Ticks per second. Animations that share a framerate share one timer.
    enabled             If False the animation is not created (default True).
    loop_mode           ANIM_LOOP_ONCE (default), ANIM_LOOP_REPEAT or ANIM_LOOP_PING_PONG.
                        REPEAT    -> on reaching end_state, jump back to start_state and replay.
                        PING_PONG -> on reaching end_state, swap start/end and play back.
                        Looping animations never "finish" on their own unless loop_count
                        is exhausted; remove them with shader.cancel_animation().
    loop_count          Number of cycles to play when looping. 0 (default) = infinite.
                        Ignored when loop_mode is ANIM_LOOP_ONCE.
    revert_on_finish    If True, the shader attribute is restored to start_state once the
                        animation completes. Default False -> the animation lands on
                        end_state, which is what most callers expect.
    callback_after_every_tick   Called as callback(anim_instance) after each lerp step.
    callback_after_loop         Called as callback(anim_instance) at each loop boundary.
    callback_after_finish       Called as callback(anim_instance) after the animation ends
                                and is removed from its shader.
    callback_after_interrupt    Called as callback(anim_instance) when cancel_animation() or
                                an internal error removes the animation before completion.

    Rules (the complete list — there is no other hidden behaviour)
    -------------------------------------------------------------
    1. `_indices` can never be animated; every other batch attribute and uniform can.
    2. shader.add_animation() ignores a declaration whose uid is already active on
       that shader. shader.set_animation() upserts instead, preserving the live
       animation's phase.
    3. A looping animation runs until cancel_animation() or loop_count exhaustion.
    4. An animation dies with its shader. Use Shader_Definition.animations for
       animations that must survive a rebuild.
    """
    animation_uid:     str
    data_type:         str   # ANIM_DATA_TYPE_UNIFORMS | ANIM_DATA_TYPE_BATCH
    data_name:         str
    end_state:         Any

    start_state:       Any   = None   # None -> auto-capture from shader at creation time
    delay_start:       float = 0.0
    duration:          float = 1.0
    framerate:         float = 60.0
    enabled:           bool  = True
    loop_mode:         str   = ANIM_LOOP_ONCE
    loop_count:        int   = 0      # 0 = infinite
    revert_on_finish:  bool  = False

    callback_after_every_tick:  Optional[Callable] = None
    callback_after_loop:        Optional[Callable] = None
    callback_after_finish:      Optional[Callable] = None
    callback_after_interrupt:   Optional[Callable] = None


@dataclass
class Animation_Instance:
    """
    Live runtime record for a single animation.
    Owned by a Shader_Instance (in its _animations dict) — do not construct directly.
    """

    # Identity (mirrored from declaration)
    animation_uid:     str
    data_type:         str
    data_name:         str
    end_state:         Any
    delay_start:       float
    duration:          float
    framerate:         float

    # Loop behaviour (mirrored from declaration)
    loop_mode:        str  = ANIM_LOOP_ONCE
    loop_count:       int  = 0        # 0 = infinite
    revert_on_finish: bool = False

    # Status
    is_enabled:  bool = True
    is_paused:   bool = False
    is_finished: bool = False

    # Number of completed cycles so far (a PING_PONG out-and-back counts as 2)
    loops_completed: int = 0

    # Private — set after construction by Animatable_Mixin
    _start_state:               Any                = field(init=False, default=None, repr=False)
    _delay_remaining:           float              = field(init=False, default=0.0,  repr=False)
    _elapsed_time:              float              = field(init=False, default=0.0,  repr=False)
    _callback_after_every_tick: Optional[Callable] = field(init=False, default=None, repr=False)
    _callback_after_loop:       Optional[Callable] = field(init=False, default=None, repr=False)
    _callback_after_finish:     Optional[Callable] = field(init=False, default=None, repr=False)
    _callback_after_interrupt:  Optional[Callable] = field(init=False, default=None, repr=False)

    @property
    def is_looping(self) -> bool:
        return self.loop_mode in (ANIM_LOOP_REPEAT, ANIM_LOOP_PING_PONG)

    @property
    def completion_factor(self) -> float:
        """Position within the CURRENT cycle, 0.0 -> 1.0."""
        if self.duration <= 0:
            return 1.0
        return min(self._elapsed_time / self.duration, 1.0)

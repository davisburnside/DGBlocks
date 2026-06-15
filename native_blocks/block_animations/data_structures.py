
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

# Valid values for Animation_Declaration.data_type
ANIM_DATA_TYPE_UNIFORMS = 'uniforms_data'
ANIM_DATA_TYPE_BATCH    = 'batch_data'


@dataclass
class Animation_Declaration:
    """
    Flat descriptor for a single animation.  Supplied by callers to
    Wrapper_Animation_Manager.add_animations().

    Fields
    ------
    animation_uid       Unique string identifier.  Must not already be active.
    target_shader_uid   UID of the Shader_Instance this animation drives.
    data_type           'uniforms_data' or 'batch_data'.
                        uniforms_data → calls shader.set_uniform(data_name, value) each tick.
                        batch_data    → writes directly to shader.<data_name> and sets
                                        _needs_new_batch = True each tick.
    data_name           For batch_data: the Python attribute name on the Shader_Instance,
                          e.g. '_points', '_colors', '_sizes'.
                        For uniforms_data: the uniform name string, e.g. 'color', 'alpha'.
    end_state           Target value the animation lerps toward.  Must share dtype / shape
                        with the captured start_state.
    start_state         Optional explicit start value.  If None (default), the block
                        auto-captures the current shader value via getattr / get_uniform
                        at add_animations() time.
    delay_start         Seconds to wait before the lerp begins (default 0).
    duration            Seconds for the full lerp from start to end (default 1.0).
    framerate           Ticks per second.  Animations that share a framerate share one timer.
    enabled             If False the animation is not created (default True).
    callback_after_every_tick   Called as callback(anim_instance) after each lerp step.
    callback_after_finish       Called as callback(anim_instance) after the animation ends
                                and is removed from RTC.  Safe to call add_animations() here
                                for looping (use a small delay_start to avoid deep recursion).
    callback_after_interrupt    Called as callback(anim_instance) when cancel_animation() or
                                an internal error removes the animation before completion.
    """
    animation_uid:     str
    target_shader_uid: str
    data_type:         str   # ANIM_DATA_TYPE_UNIFORMS | ANIM_DATA_TYPE_BATCH
    data_name:         str
    end_state:         Any

    start_state:       Any   = None   # None → auto-capture from shader at add_animations() time
    delay_start:       float = 0.0
    duration:          float = 1.0
    framerate:         float = 60.0
    enabled:           bool  = True

    callback_after_every_tick:  Optional[Callable] = None
    callback_after_finish:      Optional[Callable] = None
    callback_after_interrupt:   Optional[Callable] = None


@dataclass
class Animation_Instance:
    """
    Live runtime record for a single animation.
    Fully managed by Wrapper_Animation_Manager — do not construct directly.
    """

    # Identity (mirrored from declaration)
    animation_uid:     str
    target_shader_uid: str
    data_type:         str
    data_name:         str
    end_state:         Any
    delay_start:       float
    duration:          float
    framerate:         float

    # Status
    is_enabled:  bool = True
    is_paused:   bool = False
    is_finished: bool = False

    # Private — set after construction by Wrapper_Animation_Manager.add_animations()
    _start_state:               Any            = field(init=False, default=None,  repr=False)
    _delay_remaining:           float          = field(init=False, default=0.0,   repr=False)
    _elapsed_time:              float          = field(init=False, default=0.0,   repr=False)
    _callback_after_every_tick: Optional[Callable] = field(init=False, default=None, repr=False)
    _callback_after_finish:     Optional[Callable] = field(init=False, default=None, repr=False)
    _callback_after_interrupt:  Optional[Callable] = field(init=False, default=None, repr=False)

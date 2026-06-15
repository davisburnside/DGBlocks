
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

@dataclass
class Timer_Definition:
    """
    Flat descriptor for a single timer. Supplied by downstream blocks inside
    hook_get_timer_definitions.

    timer_uid may be left as an empty string; Wrapper_Timer_Manager will
    auto-assign a unique ID ("TIMER_0", "TIMER_1", …) during rebuild.
    Two definitions with the same non-blank timer_uid are a validation error.

    callback is called by _universal_timer_callback each time the timer fires.
    Signature:  callback(timer_instance: Timer_Instance) -> None
    """
    timer_uid: str
    frequency: float           # Seconds between fires. Must be > 0.
    callback: Callable         # (timer_instance) -> None


@dataclass
class Timer_Instance:
    """
    Live runtime record for a single timer.
    Fully managed by Wrapper_Timer_Manager — do not construct directly.
    """

    # Identity
    timer_uid: str             # Unique within a rebuild cycle; auto-assigned if definition had ""
    src_block_id: str          # Block that supplied the Timer_Definition
    frequency: float           # Seconds

    # Status
    is_enabled: bool = True
    run_count: int = 0
    timer_error_str: Optional[str] = None   # None = healthy; set on exception, clears is_enabled

    # Runtime — set at creation time from the Timer_Definition
    _callback: Optional[Callable] = field(init=False, default=None, repr=False)

    # bpy.app.timers handle — thin closure stored so it can be unregistered later
    _timer_func: Optional[Callable] = field(init=False, default=None, repr=False)

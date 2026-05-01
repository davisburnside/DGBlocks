
from enum import Enum
import bpy # type: ignore

# =============================================================================
# BLOCK LOGGERS
# =============================================================================

class Block_Logger_Definitions(Enum):
    """Logger definitions for this block"""
    TIMER_FIRE = ("timer-exec", "INFO")
    TIMER_LIFECYCLE = ("timer-lifecycle", "DEBUG")

# =============================================================================
# BLOCK HOOKS
# =============================================================================

class Block_Hooks(Enum):
    """Hook definitions that this block provides to subscriber blocks"""
    TIMER_FIRE = ("hook_timer_fire", {
        "context": bpy.types.Context, "timer_name": str
    })

# =============================================================================
# RUNTIME CACHE MEMBERS
# =============================================================================

class Block_Runtime_Cache_Members(Enum):
    """Runtime cache keys for this block.
    Format: KEY_NAME = ("cache-key-string", default_value)
    TIMER_INSTANCES stores Dict[str, Timer_Wrapper.Instance_Data] — one entry per named timer.
    The Instance_Data dataclass holds all metadata AND the bpy.app.timers callable reference.
    """
    TIMER_INSTANCES = ("timer-instances", {})

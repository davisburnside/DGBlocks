
from enum import Enum, StrEnum, auto
import bpy

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Block_Logger_Definitions(Enum):    
    DRAWHANDLER_LIFECYCLE = ("drawhandler_lifecycle", "INFO")
    SHADER_BATCH_EVENTS = ("shader_batch_events", "INFO")

# name = RTC Member ID 
# value[0] = actual RTC dict key / data structure
# value[1] = default data for RTC key
class Block_RTC_Members(Enum):
    DRAW_PHASES = ("draw_phases", [])



# =================================================================================
# CONSTANTS & ENUM — Single source of truth for all members
# =================================================================================

class Draw_Phase_Types(StrEnum):
    """
    Every member of the fixed list. Add/remove entries here,
    then update the PropertyGroup and sync functions to match.
    
    The enum name IS the uid.
    The value tuple is (display_name, default_is_enabled).
    """
    MEMBER_ALPHA = auto()
    MEMBER_BETA  = auto()
    MEMBER_GAMMA = auto()
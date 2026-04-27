
from enum import Enum, StrEnum, auto
import bpy

#=================================================================================
# BLOCK-SPECIFIC DATA
#=================================================================================

class Draw_Phase_Types(StrEnum):
    POST_PIXEL = auto()
    POST_VIEW  = auto()

#=================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
#=================================================================================

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Block_Hook_Sources(Enum):
    DRAW_EVENT = ("hook_draw_event", {"draw_handler_instance": any})

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Block_Logger_Definitions(Enum):    
    DRAWHANDLER_LIFECYCLE = ("drawhandler_lifecycle", "DEBUG")
    SHADER_BATCH_EVENTS = ("shader_batch_events", "DEBUG")

# name = RTC Member ID 
# value[0] = actual RTC dict key / data structure
# value[1] = default data for RTC key
class Block_RTC_Members(Enum):
    DRAW_PHASES = ("draw_phases", {})

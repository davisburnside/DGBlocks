
from enum import Enum
import bpy # type: ignore

#=================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
# Enum classes are used to allow typing & autocomplete, minimizing "magic-strings" antipattern
# Enum class values must have both unique names & unique values. Non-unique values cause names to become aliases of each other
#=================================================================================

# name = hook ID
# value[0] = hooked function name (caps included)
# value[1] = expected function arguments & types
class Block_Logger_Definitions(Enum):    
    MODAL_LIFECYCLE = ("modal-lifecycle", "INFO")
    MODAL_EVENTS = ("modal-events", "DEBUG")

# name = logger ID
# value[0] = logger display name & default level
# value[1] = logger display name & default level
class Block_Hooks(Enum):
    
    KEY_EVENT = ("hook_modal_key_event", {
        "context": bpy.types.Context, 
        "event": bpy.types.Event
    })
    
    MOUSE_EVENT = ("hook_modal_mouse_event", {
        "context": bpy.types.Context,
        "event": bpy.types.Event
    })
    
    AREA_CHANGE_EVENT = ("hook_modal_area_change", {
        "context": bpy.types.Context,
        "event": bpy.types.Event,
        "old_area": bpy.types.Area,
        "new_area": bpy.types.Area
    })

# name = RTC Member ID 
# value[0] = actual RTC dict key / data structure
# value[1] = default data for RTC key
class Block_RTC_Members(Enum):
    # MODAL_INSTANCE = ("modal-instance", None) # Unlike timers which can have multiple instances, the modal is singular.
    MODALS_CACHE = ("modals-cache", [])

#=================================================================================
# OTHER
#=================================================================================

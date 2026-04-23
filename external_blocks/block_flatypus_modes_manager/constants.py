
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
    ASSEMBLY_MODE_LIFECYCLE = ("assembly-mode-lifecycle", "INFO")

# name = logger ID
# value[0] = logger display name & default level
# value[1] = logger display name & default level
# class Block_Hooks(Enum):
#     ASSEMBLY_MODE_BEFORE_ACTIVATION = ("hook_modal_key_event", {
#         "context": bpy.types.Context, 
#         "event": bpy.types.Event
#     })
    

# name = RTC Member ID 
# value[0] = actual RTC dict key / data structure
# value[1] = default data for RTC key
class Block_RTC_Members(Enum):
    IS_ASSEMBLY_MODE_ACTIVE = ("flatypus-assembly-mode-active", False)

#=================================================================================
# OTHER
#=================================================================================

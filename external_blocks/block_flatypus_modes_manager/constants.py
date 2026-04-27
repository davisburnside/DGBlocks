
from enum import Enum
import bpy # type: ignore

from .custom_shaders.billboard_image_shader import Billboard_Shader

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

# name = RTC Member ID 
# value[0] = actual RTC dict key / data structure
# value[1] = default data for RTC key
class Block_RTC_Members(Enum):
    IS_ASSEMBLY_MODE_ACTIVE = ("flatypus-assembly-mode-active", False)

#=================================================================================
# OTHER
#=================================================================================

class Assembly_Mode_Shader_Definitions(Enum):
    TRIS_DEFAULT = ('POLYLINE_SMOOTH_COLOR', 'LINES')
    DEBUG_DOT = ('POLYLINE_UNIFORM_COLOR', 'POINTS')
    BILLBOARD = (Billboard_Shader, 'TRIS')
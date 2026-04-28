
from enum import Enum, StrEnum, auto
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
# BLOCK-SPECIFIC CONSTANTS
#=================================================================================

# name = Shader UID
# value[0] = Shader type: always a value from 'Shader_Types'
# value[1] (When using builtin shader) = Always a value from 'Builtin_Shader_Names'
# value[1] (When using custom shader) = Class reference of Shader, must inherit from 'Shader_Instance'
# value[2] (Only when using custom shader) = Additional kwargs for custom shader
class Assembly_Mode_Shader_Definitions(Enum):
    LINES_T1 = ('LINES', 'POLYLINE_SMOOTH_COLOR')
    DEBUG_DOT = ('POINTS', 'POLYLINE_UNIFORM_COLOR')
    BILLBOARD = ('TRIS', Billboard_Shader, {"image_name" : "img"})
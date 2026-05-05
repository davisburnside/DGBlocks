
from enum import Enum, StrEnum, auto

# ==========================================
# Cache Key Constants
class Block_Hook_Definitions(Enum):
    TIMER_FIRE = ("timer_fire", {"timer_instance" : any})

# ==========================================
# Loggers user by this block
class Block_Loggers(Enum):
    TIMER_LIFECYCLE = ("timer_lifecycle", "DEBUG")

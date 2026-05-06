from enum import Enum

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
# ==============================================================================================================================

class Block_Hook_Sources(Enum):
    pass

class Block_Loggers(Enum):
    EXAMPLE_USECASE_02B = ("example_usecase_02b", "INFO")

class Block_RTC_Members(Enum):
    MIRROR_ITEMS = ("MIRROR_ITEMS", [])

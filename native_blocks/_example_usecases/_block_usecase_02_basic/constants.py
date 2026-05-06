from enum import Enum

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members
# ==============================================================================================================================

class Block_Hook_Sources(Enum):
    pass

class Block_Loggers(Enum):
    EXAMPLE_USECASE_01 = ("example_usecase_01", "INFO")

class Block_RTC_Members(Enum):
    DEMO_DATA = ("EXAMPLE_SIMPLE_2_DEMO_DATA", {})

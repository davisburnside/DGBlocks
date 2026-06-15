
from ...addon_helpers.data_structures import Logger_Declaration, RTC_Member_Declaration, String_Comparable_Mixin

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Loggers(String_Comparable_Mixin):
    ANIMATION_LIFECYCLE   = Logger_Declaration("DEBUG")
    ANIMATION_TICK_EVENTS = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    ANIMATIONS = RTC_Member_Declaration([])  # list[Animation_Instance]

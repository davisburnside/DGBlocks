
from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, String_Comparable_Mixin

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    hook_draw_event     = Hook_Source_Declaration({"draw_handler_instance": any})
    before_first_draw   = Hook_Source_Declaration({"draw_handler_instance": any})
    after_last_draw     = Hook_Source_Declaration({"draw_handler_instance": any})


class Block_Loggers(String_Comparable_Mixin):    
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("DEBUG")
    SHADER_BATCH_EVENTS = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration({})
    SHADERS = RTC_Member_Declaration({})

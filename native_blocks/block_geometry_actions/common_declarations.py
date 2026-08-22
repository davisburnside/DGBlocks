
from ...addon_helpers.data_structures import (
    Logger_Declaration,
    RTC_Member_Declaration,
    String_Comparable_Mixin,
)

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
#
# This block is demand-driven: callers invoke
# Wrapper_Geometry_Actions.run_geometry_action_for_object() directly. There are no hook
# sources, no data mirrors and no UIList — nothing here is persisted to BL data, because
# every payload is a numpy array.
# ==============================================================================================================================

class Block_Loggers(String_Comparable_Mixin):
    GEOMETRY_ACTIONS_LIFECYCLE = Logger_Declaration("INFO")
    GEOMETRY_ACTIONS_EVENTS    = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    # dict[str, Geometry_Actions_Result_Instance]
    # key = "<declaration_id>|<object_session_uid>"; a later run of that action replaces it
    GEOMETRY_ACTION_RESULTS     = RTC_Member_Declaration({})
    # Monotonic counter used to stamp each Action_Record with a unique action_uid
    GEOMETRY_ACTION_UID_COUNTER = RTC_Member_Declaration(0)

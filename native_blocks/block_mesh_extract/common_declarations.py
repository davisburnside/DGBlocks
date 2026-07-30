
from ...addon_helpers.data_structures import (
    Logger_Declaration,
    RTC_Member_Declaration,
    String_Comparable_Mixin,
)

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
#
# This block is demand-driven: callers invoke Wrapper_Mesh_Extract.run_mesh_action_for_object()
# directly. There are no hook sources, no data mirrors and no UIList — nothing here is
# persisted to BL data, because every payload is a numpy array.
# ==============================================================================================================================

class Block_Loggers(String_Comparable_Mixin):
    MESH_EXTRACT_LIFECYCLE = Logger_Declaration("INFO")
    MESH_EXTRACT_EVENTS    = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    # list[RTC_Mesh_Extract_Instance] — keyed by (object_name, slot)
    MESH_EXTRACT_INSTANCES   = RTC_Member_Declaration([])
    # dict[str, deque[RTC_Mesh_Extract_Instance]] — keyed by "object_name|slot"
    MESH_EXTRACT_HISTORY     = RTC_Member_Declaration({})
    # Monotonic counter used to stamp each Mesh_Action_Record with a unique action_uid
    MESH_ACTION_UID_COUNTER  = RTC_Member_Declaration(0)

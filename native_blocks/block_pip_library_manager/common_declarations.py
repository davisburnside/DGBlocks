from ...addon_helpers.data_structures import (
    Hook_Source_Declaration,
    Logger_Declaration,
    RTC_Member_Declaration,
    String_Comparable_Mixin,
)


class Block_Hook_Sources(String_Comparable_Mixin):
    hook_get_python_library_requirements = Hook_Source_Declaration({})
    hook_python_library_requirement_available = Hook_Source_Declaration({
        "requirement_uid": str,
        "action_token": str,
    })


class Block_Loggers(String_Comparable_Mixin):
    PIP_LIBRARY_LIFECYCLE = Logger_Declaration("INFO")
    PIP_LIBRARY_OPERATIONS = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    LIBRARY_INFOS = RTC_Member_Declaration({})
    REQUIREMENT_INFOS = RTC_Member_Declaration({})
    MODULE_CACHE = RTC_Member_Declaration({})
    INSTALL_REQUESTS = RTC_Member_Declaration({})
    INSTALL_OPERATIONS = RTC_Member_Declaration({})
    MANAGED_PATH_STATE = RTC_Member_Declaration(None)

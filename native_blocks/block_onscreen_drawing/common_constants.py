
from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, RTC_Member_Data_Mirror_Declaration, String_Comparable_Mixin

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


class Block_Data_Mirrors(String_Comparable_Mixin):
    # SHADERS is a dict-keyed RTC member, so default list-based sync is unsuited.
    # Wrapper_Draw_Handlers implements both custom sync methods.
    SHADERS_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "SHADERS",
        FWC_name = "Wrapper_Draw_Handlers",
        mirrored_key_field_names = ["shader_uid"],
        mirrored_data_field_names = ["is_enabled"],
        default_data_path_in_scene = None,
    )

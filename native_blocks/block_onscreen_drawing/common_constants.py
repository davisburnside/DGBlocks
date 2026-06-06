
from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, RTC_Member_Data_Mirror_Declaration, String_Comparable_Mixin

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    hook_get_shader_definitions = Hook_Source_Declaration({"definition_accumulator": list})
    hook_before_first_draw      = Hook_Source_Declaration({})


class Block_Loggers(String_Comparable_Mixin):    
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("DEBUG")
    SHADER_BATCH_EVENTS   = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration({})
    SHADERS     = RTC_Member_Declaration({})


class Block_Data_Mirrors(String_Comparable_Mixin):
    SHADER_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key                  = "SHADERS",
        FWC_name                 = "Wrapper_Shader_Manager",
        mirrored_key_field_names = ["uid"],
        mirrored_data_field_names= ["is_enabled"],
        # Custom sync path: Wrapper_Shader_Manager must implement both
        # update_RTC_with_mirrored_BL_data and update_BL_with_mirrored_RTC_data.
        # The framework calls them during all sync events (undo/redo/init).
        default_data_path_in_scene = None,
    )

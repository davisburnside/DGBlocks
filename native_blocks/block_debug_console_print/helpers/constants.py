
from enum import Enum
import bpy

from ....addon_helpers.data_structures import Hook_Source_Declaration

class Block_Hook_Sources(Enum):

    hook_debug_get_state_data_to_print = Hook_Source_Declaration({})
    hook_debug_uilayout_draw_console_print_settings = Hook_Source_Declaration({"ui_container": bpy.types.UILayout})


# The single radio-button range at the top of the "Settings Dropdown body Box".
# Only the selected section's body is drawn below the radio row.
debug_console_print_filter_section_items = [
        ("GENERAL", "General", "General output settings"),
        ("KEYS", "Dict Keys Filter", "Filter by dict / dataclass keys"),
        ("DATA", "Num/Str Filter", "Filter by numeric / string leaf values")]

# Include vs Exclude mode shared by the numeric and string data filters.
debug_console_print_filter_mode_items = [
        ("INCLUDE", "Include Matches", "Keep only leaves that match the filter set"),
        ("EXCLUDE", "Exclude Matches", "Drop leaves that match the filter set")]

# Numeric leaf comparison operators (one row per added filter).
numeric_comparison_enum_items = [
        (">", ">", "greater than"),
        (">=", ">=", "greater than or equal"),
        ("==", "==", "equal"),
        ("!=", "!=", "not equal"),
        ("<=", "<=", "less than or equal"),
        ("<", "<", "less than")]

# String leaf comparison operators (one row per added filter). Case-insensitive.
string_comparison_enum_items = [
        ("contains", "contains", "substring match"),
        ("equals", "equals", "exact match"),
        ("startswith", "starts with", "prefix match"),
        ("endswith", "ends with", "suffix match")]

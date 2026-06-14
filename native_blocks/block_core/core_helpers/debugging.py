
import bpy

from datetime import datetime
from enum import StrEnum, auto

# Addon-level imports
from ....addon_helpers.data_tools import get_propertygroup_values
from ....addon_helpers.generic_tools import print_section_separator
from ....addon_helpers.text_formatting_tools import make_table_string_from_data

# Intra-block imports
from ..core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .constants import Core_Runtime_Cache_Members

# ==============================================================================================================================
# DATA STRUCTURES

class Debugging_Print_Options(StrEnum):
    HOOK_SOURCES = auto()
    HOOK_SUBSCRIBERS = auto()
    ALL_BLOCKS_RTC_MEMBERS = auto()
    ALL_BLOCKS_BL_SCENE_PROPS = auto()
    ALL_BLOCKS_BL_PREFERENCES_PROPS = auto()

debug_sort_hooks_choice_items = [
    ("last_run_timestamp", "Time Last Called", "Time Last Called"),
    ("is_hook_enabled", "Is Enabled", "Is Enabled"),
    ("count_hook_propagate_success", "Success Count", "Number of successful hook calls"),
    ("count_hook_propagate_failure", "Failure Count", "Number of hook calls that raised an exception"),
    ("count_bypass_via_data_filter", "Bypass: Data Filter", "Bypassed by @hook_data_filter predicate"),
    ("count_bypass_via_status", "Bypass: Status", "Bypassed by manual flag or re-entrancy guard"),
    ("count_bypass_via_frequency", "Bypass: Frequency", "Bypassed by min_ms_between_runs rate limit"),
    ("average_runtime", "(ms) Avg Exec Time", "Average execution time per successful call"),
]

# ==============================================================================================================================
# HELPER FUNCS

def _get_data_for_subscriber_hook_table(column_rename_map):
        
        reformatted_hooks_data = {}
        all_subscriber_hooks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS)
        for hook_func_name in all_subscriber_hooks:
            reformatted_hooks_data[hook_func_name] = {}
            for bhm in all_subscriber_hooks[hook_func_name]:
                
                # Reformat (RTC_Hook_Subscriber_Instance -> dict) & rename columns of hook data for printing
                if bhm.total_running_time == 0:
                    avg_ms_runtime = 0
                else:
                    avg_ms_runtime = (bhm.count_hook_propagate_success + bhm.count_hook_propagate_failure) / (bhm.total_running_time * 1000)
                raw_data = {
                    debug_sort_hooks_choice_items[0][0] : datetime.fromtimestamp(bhm.last_run_timestamp/1000).strftime(("%Y-%m-%d %H:%M:%S.%f")),
                    debug_sort_hooks_choice_items[1][0] : not bhm.is_hook_enabled,
                    debug_sort_hooks_choice_items[2][0] : bhm.count_hook_propagate_success,
                    debug_sort_hooks_choice_items[3][0] : bhm.count_hook_propagate_failure,
                    debug_sort_hooks_choice_items[4][0] : bhm.count_bypass_via_data_filter,
                    debug_sort_hooks_choice_items[5][0] : bhm.count_bypass_via_status,
                    debug_sort_hooks_choice_items[6][0] : bhm.count_bypass_via_frequency,
                    debug_sort_hooks_choice_items[7][0] : avg_ms_runtime,
                }
                renamed_data = {column_rename_map.get(k, k): v for k, v in raw_data.items()}
                block_id = bhm.subscriber_block_module._BLOCK_ID
                reformatted_hooks_data[hook_func_name][block_id] = renamed_data
        
        return reformatted_hooks_data


def _get_data_for_unused_hooks_list():
        
        all_hook_subscribers = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS)
        unused_hooks = [h for h in all_hook_subscribers if len(all_hook_subscribers[h]) == 0]
        if len(unused_hooks) == 0:
            return "No Unused Hooks"
        str_unused_hooks = "\n\nUnused Hooks:\n- " + "\n- ".join(unused_hooks)
        return str_unused_hooks


def debug_extract_core_block_data_to_print(context, other_input):
    
    debug_settings = context.scene.dgblocks_debug_console_print_props
    data_to_return = {}
    
    # Return unfiltered table string, of hook subscriber metadata
    if other_input == Debugging_Print_Options.HOOK_SUBSCRIBERS:
        print_section_separator("All Hooks in Addon")
        
        column_rename_map = {item[0]: item[1] for item in debug_sort_hooks_choice_items}
        sort_key = column_rename_map[debug_settings.debug_block_hooks_table_sort_by]
        formatted_data = _get_data_for_subscriber_hook_table(column_rename_map)
        
        data_to_return = "\n"
        data_to_return += make_table_string_from_data(formatted_data, sort_key = sort_key)
        data_to_return += _get_data_for_unused_hooks_list()
             
    # Return entire runtime cache
    elif other_input == Debugging_Print_Options.ALL_BLOCKS_RTC_MEMBERS:
        print_section_separator(f"All Runtime Cache Data")
        data_to_return = Wrapper_Runtime_Cache._cache
    
    # Return JSON representation of all current-scene properties related to Blocks
    elif other_input == Debugging_Print_Options.ALL_BLOCKS_BL_SCENE_PROPS:
        print_section_separator(f"All Scene-Owned Addon data")
        data_to_return = get_propertygroup_values(context.scene, prefix = "dgblock")
        
    # elif other_input == Debugging_Print_Options.ALL_BLOCKS_BL_PREFERENCES_PROPS:
    #     print_section_separator(f"All Scene-Owned Addon data")
    #     prefs = get_addon_preferences(context)
    #     data_to_return = get_members_and_values_of_propertygroup_with_name_prefix(prefs, "dgblock")

    else:
        data_to_return = ""

    return data_to_return


def debug_ui_draw_core_block_printing_options(context:bpy.context, container:bpy.types.UILayout, block_id:str):
    
    debug_settings = context.scene.dgblocks_debug_console_print_props
    button_scale = 1.5
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All Hook Data (Table, Unfiltered)")
    op.source_block_id = block_id
    op.other_input = Debugging_Print_Options.HOOK_SUBSCRIBERS
    split = box.split()
    row_l = split.row()
    row_r = split.row()
    # row_l.label(text = "Sort by")
    row_l.prop(debug_settings, "debug_block_hooks_table_sort_by") 
    # row_r.prop(debug_settings, "debug_block_hooks_table_include_unused") 

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "All RTC Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Debugging_Print_Options.ALL_BLOCKS_RTC_MEMBERS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Scene Data (JSON, Filtered)")
    op.source_block_id = block_id
    op.other_input = Debugging_Print_Options.ALL_BLOCKS_BL_SCENE_PROPS
    
    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "BL-Preferences Data (JSONified, Filtered)")
    op.source_block_id = block_id
    op.other_input = Debugging_Print_Options.ALL_BLOCKS_BL_PREFERENCES_PROPS

    box = container.box()
    row = box.row()
    row.scale_y = button_scale
    op = row.operator(f"dgblocks.debug_console_print_block_diagnostics", text = "UNIT TESTS")
    op.source_block_id = "TEST"


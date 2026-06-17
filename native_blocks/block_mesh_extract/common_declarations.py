
from ...addon_helpers.data_structures import (
    Hook_Source_Declaration,
    Logger_Declaration,
    RTC_Member_Declaration,
    RTC_Member_Data_Mirror_Declaration,
    Shared_UIList_Declaration,
    String_Comparable_Mixin,
)
from .ui import _uilist_draw_row, _uilist_draw_selection_details

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    """
    hook_get_mesh_extract_targets : Downstream blocks return list[Mesh_Extract_Target].
                                    Called at the start of every extraction cycle.
    hook_mesh_extract_ready       : Fired after all objects have been extracted and cached.
                                    Kwargs: object_names (list[str]) — names that were processed.
    """
    hook_get_mesh_extract_targets = Hook_Source_Declaration({})
    hook_mesh_extract_ready       = Hook_Source_Declaration({"object_names": list})


class Block_Loggers(String_Comparable_Mixin):
    MESH_EXTRACT_LIFECYCLE = Logger_Declaration("INFO")
    MESH_EXTRACT_EVENTS    = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    MESH_EXTRACT_INSTANCES = RTC_Member_Declaration([])


class Block_Data_Mirrors(String_Comparable_Mixin):
    MESH_EXTRACT_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key                   = "MESH_EXTRACT_INSTANCES",
        FWC_name                  = "Wrapper_Mesh_Extract",
        mirrored_key_field_names  = ["object_name"],
        mirrored_data_field_names = ["is_valid"],
        scene_colprop_path        = "dgblocks_mesh_extract_props.extract_mirror",
    )


class Block_UIList_Configs(String_Comparable_Mixin):
    MESH_EXTRACT_UILIST = Shared_UIList_Declaration(
        col_names  = ["Object", "Valid", "Time (ms)", "Reads"],
        col_widths = [4, 1, 2, 1],
        scene_parent_path                            = "dgblocks_mesh_extract_props",
        scene_colprop_path                           = "extract_mirror",
        scene_colprop_path_UIList_selection_idx_path = "extract_mirror_selected_idx",
        RTC_key                                      = Block_RTC_Members.MESH_EXTRACT_INSTANCES,
        callback_draw_row             = _uilist_draw_row,
        callback_draw_details_section = _uilist_draw_selection_details,
    )

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import bpy
from ..native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..native_blocks.block_core.core_helpers.constants import Core_Runtime_Cache_Members
from ..addon_config.static_settings import min_width_for_weblink_btn_spawn, separator_width_factor, weblink_button_width_factor

# --------------------------------------------------------------
# "Blind draw" functions: All drawing logic is contained inside the function
# --------------------------------------------------------------

def ui_draw_list_headers(container, col_names: set, col_widths: set):

    if len(col_names) != len(col_widths):
        raise Exception(f"lists must match length {len(col_names)} : {len(col_widths)}")

    header = container.row()
    header.separator(factor=0.5)  # Account for UIList left padding

    for i in range(len(col_names)):
        sub = header.row()
        sub.ui_units_x = col_widths[i]
        sub.label(text = col_names[i])

def ui_draw_static_list(container, data_rows: list, col_widths):



    box = container.box()
    # header.separator(factor=0.5)  # Account for UIList left padding

    for data_row in data_rows:
        if len(data_row) != len(col_widths):
            raise Exception(f"lists must match length {len(data_row)} : {len(col_widths)}")
        row = box.row()
        for i, data_col in enumerate(data_row):
            sub = row.row()
            sub.ui_units_x = col_widths[i]
            sub.label(text = data_col)

def ui_draw_block_panel_header(context:bpy.context, container:bpy.types.UILayout, header_text:str, url_enum:Enum = None, icon_name:str = None):

    container.separator(factor = separator_width_factor, type = "LINE")
    container.use_property_split = False
    container.alignment="EXPAND"
    if icon_name is not None:
        container.label(text = "", icon = icon_name)
    container.label(text = header_text)
    row = container.row()
    row.alignment = 'RIGHT'
    if url_enum is not None and context.region.width > min_width_for_weblink_btn_spawn and context.scene.dgblocks_core_props.documentation_weblinks_enabled:
        row.separator(factor = separator_width_factor, type = "LINE")
        row.scale_x = weblink_button_width_factor
        op = row.operator("dgblocks.open_help_page", text="", icon = "QUESTION")
        op.web_documentation_url = url_enum.value

def uilayout_section_separator(container, lines_count:int = 2, extra_space:float = 1):

    if extra_space > 0:
        container.separator(factor = extra_space)
    for _ in range(lines_count):
        container.separator(type="LINE", factor = 0.4)
    if extra_space > 0:
        container.separator(factor = extra_space)

# --------------------------------------------------------------
# "Interactive draw" functions: Returns UILayout objects to be used in further draws
# --------------------------------------------------------------

def create_ui_box_with_header(context:bpy.context, container:bpy.types.UILayout, header_text:list[str], icon:str = None, separator_factor:float = 0.2, skip_box:bool = False):

    if isinstance(header_text, str):
        header_text = [header_text]
    if skip_box:
        self_container = container
    else:
        self_container = container.box()
    for idx, str_item in enumerate(header_text):
        row = self_container.row()
        row.alignment = "CENTER"
        row.scale_y = 0.7
        row.label(text = str_item)
        if icon is not None and idx == 0:
            row.label(text = "", icon = icon)

    if separator_factor > 0.0:
        self_container.separator(type="LINE", factor = separator_factor)
    return self_container


# --------------------------------------------------------------
# Shared UIList class: contains an optional details section
# --------------------------------------------------------------


def v2_draw_shared_uilist(context, container, cached_uilist_config):
   
    # Draw header
    ui_draw_list_headers(container, cached_uilist_config.col_names, cached_uilist_config.col_widths)
    
    RTC_key = cached_uilist_config.RTC_key
    colprop_path = cached_uilist_config.scene_colprop_path
    colprop_idx_path = cached_uilist_config.scene_colprop_path_UIList_selection_idx_path 
    BL_scene_parent = context.scene.path_resolve(cached_uilist_config.scene_parent_path)
    BL_colprop = BL_scene_parent.path_resolve(colprop_path)
    selected_idx = BL_scene_parent.path_resolve(colprop_idx_path)
    row_count = len(BL_colprop)

    # Draw UIList
    row = container.row()
    row.template_list(
        "DGBLOCKS_UL_Shared_Debug_List",
        colprop_path,
        BL_scene_parent, 
        colprop_path,
        BL_scene_parent, 
        colprop_idx_path,
        rows = row_count, 
        columns = len(cached_uilist_config.col_names),
    )

    # Draw details if selected and details_func exists
    # idx: int = getattr(collection_owner, active_idx_prop)
    # collection: bpy.types.CollectionProperty = getattr(collection_owner, collection_prop)
    if cached_uilist_config.callback_draw_details_section and 0 <= selected_idx < row_count:
        BL_item = BL_colprop[selected_idx]
        RTC_item = None
        if RTC_key:
            associated_cache = Wrapper_Runtime_Cache.get_cache(RTC_key)
            RTC_item = associated_cache[selected_idx]
        cached_uilist_config.callback_draw_details_section(context, container, BL_item, RTC_item, selected_idx)




class DGBLOCKS_UL_Shared_Debug_List(bpy.types.UIList):
    """
    Generic UIList for debug panels. Uses a (non-hook) callback to draw each row
    This allows multiple UILists, with differing structures, to share this class
    """

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):

        _, uillist_config_instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            "SHARED_UILIST_CONFIGS",
            "scene_colprop_path_UIList_selection_idx_path",
            active_propname
        )

        RTC_item = None
        RTC_key = uillist_config_instance.RTC_key
        if RTC_key:
            associated_cache = Wrapper_Runtime_Cache.get_cache(RTC_key)
            RTC_item = associated_cache[index]

        uillist_config_instance.callback_draw_row(context, container, item, RTC_item, index)

        # configs = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS)

        # print(uillist_config_instance)

        # v2_draw_shared_uilist(context, container, uillist_config_instance)
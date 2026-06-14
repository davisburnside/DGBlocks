from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
from typing import Optional
import bpy

from ..addon_helpers.generic_tools import get_Wrapper_Runtime_Cache
from ..addon_config.static_settings import min_width_for_weblink_btn_spawn, separator_width_factor, weblink_button_width_factor

# --------------------------------------------------------------
# "Blind draw" functions: All drawing logic is contained inside the function
# --------------------------------------------------------------

def format_timestamp_for_ui(timestamp) -> str:
    if not timestamp:
        return "Never"
    dt = datetime.fromtimestamp(timestamp)
    return f"{dt.strftime('%H:%M:%S')}.{int((timestamp % 1) * 1_000_000):06d}"

def ui_draw_generic_instance_data(context, layout, instance, structure: dict):
    scene = context.scene

    for category, entries in structure.items():
        box = layout.box()
        box.label(text=category)

        col = box.column(align=True)
        for entry in entries:
            split = col.split(factor=0.6)
            
            # 3-tuple
            if len(entry) == 3:
                label, var_name, third_item = entry
                split.label(text=label)
                if callable(third_item):
                    raw_data = getattr(instance, var_name)
                    func = third_item
                    formatted_data = func(raw_data)
                    split.label(text = str(formatted_data))
                else:
                    scene_data_path = third_item
                    property_name = var_name
                    owner = scene.path_resolve(scene_data_path)
                    split.prop(owner, property_name, text=label)

            # (For non-BL data only)
            # 2-tuple, draw instance variable directly
            else:
                label, var_name = entry
                raw_data = getattr(instance, var_name)
                split.label(text = label)
                split.label(text = str(raw_data))
                # if callable(accessor):
                #     label_value = accessor(stats)
                # else:
                #     label_value = getattr(stats, accessor)
                # split.label(text = label_value)

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
        container.separator(type="LINE", factor = 0.2)
    if extra_space > 0:
        container.separator(factor = extra_space)

def ui_draw_subpanel(context, container, panel_uid, header_text, _callback_draw_contents, **kwargs):

    box = container.box()
    panel_header, panel_body = box.panel(idname = f"_dummy_dgblocks_core_scene_{panel_uid}", default_closed=True)
    if header_text:
        panel_header.label(text = header_text)
    if panel_body is not None:
        uilayout_section_separator(box, extra_space = 0)
        _callback_draw_contents(context, box, **kwargs)
        uilayout_section_separator(box, extra_space = 0, lines_count = 0)
    return panel_header, panel_body

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

def draw_shared_uilist(context, container, scene_data_path):
   
    # Get UIList config metadata
    _dirty_wrapper_RTC = get_Wrapper_Runtime_Cache()
    _, uillist_config_instance, _ = _dirty_wrapper_RTC.get_unique_instance_from_registry_list(
        "SHARED_UILIST_CONFIGS", 
        "scene_colprop_path",
        scene_data_path,
    )
    RTC_key = uillist_config_instance.RTC_key
    colprop_path = uillist_config_instance.scene_colprop_path
    colprop_idx_path = uillist_config_instance.scene_colprop_path_UIList_selection_idx_path 
    BL_scene_parent = context.scene.path_resolve(uillist_config_instance.scene_parent_path)
    BL_colprop = BL_scene_parent.path_resolve(colprop_path)
    selected_idx = BL_scene_parent.path_resolve(colprop_idx_path)
    row_count = len(BL_colprop)

    # Draw list header
    ui_draw_list_headers(container, uillist_config_instance.col_names, uillist_config_instance.col_widths)

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
        columns = len(uillist_config_instance.col_names),
    )

    # Draw details if selected and details_func exists
    if uillist_config_instance.callback_draw_details_section and 0 <= selected_idx < row_count:
        BL_item = BL_colprop[selected_idx]
        RTC_item = None
        if RTC_key:
            associated_cache = _dirty_wrapper_RTC.get_cache(RTC_key)
            RTC_item = associated_cache[selected_idx]
        uillist_config_instance.callback_draw_details_section(context, container, uillist_config_instance, BL_item, RTC_item, selected_idx)


class DGBLOCKS_UL_Shared_Debug_List(bpy.types.UIList):
    """
    Generic UIList for debug panels. Uses a (non-hook) callback to draw each row
    This allows multiple UILists, with differing structures, to share this class
    """

    def draw_item(self, context, container, data, BL_item, icon, active_data, active_propname, selected_list_index):

        # Get the associated uilist_config instance
        _dirty_wrapper_RTC = get_Wrapper_Runtime_Cache()
        _, uillist_config_instance, _ = _dirty_wrapper_RTC.get_unique_instance_from_registry_list(
            "SHARED_UILIST_CONFIGS",
            "scene_colprop_path_UIList_selection_idx_path",
            active_propname
        )

        # Get the associated RTC member, if it exists
        RTC_item = None
        RTC_key = uillist_config_instance.RTC_key
        if RTC_key:
            associated_cache = _dirty_wrapper_RTC.get_cache(RTC_key)
            RTC_item = associated_cache[selected_list_index]

        # instance-specific draw callback
        uillist_config_instance.callback_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, selected_list_index)

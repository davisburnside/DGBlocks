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

# @dataclass()
# class Shared_UIList_Definition:
#     uid: str
#     col_names: list[str]
#     col_widths: list[int]
#     callback_list_row: callable
#     callback_details_footer: Optional[callable] = field(default_factory = None)


    # callback_list_row: callable
    # callback_details_footer: Optional[callable] = field(default_factory = None)



# def get_shared_uilist_config(list_id):
#     configs = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS)
#     return configs.get(list_id)


# def set_shared_uilist_config(list_id, col_names, col_widths, row_func = None, details_func=None):
#     configs = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS)
#     configs[list_id] = {
#         "col_names": col_names,
#         "col_widths": col_widths,
#         # "columns_def": columns_def,
#         "details_func": details_func,
#         "row_func": row_func,
#     }


def ui_draw_shared_debug_list(context, container, list_id, collection_owner, collection_prop, active_idx_prop, rows=5):
    config = get_shared_uilist_config(list_id)
    if not config:
        container.label(text=f"No config for {list_id}")
        return

    # Draw header
    ui_draw_list_headers(container, config["col_names"], config["col_widths"])

    # Draw UIList
    row = container.row()
    row.template_list(
        "DGBLOCKS_UL_Shared_Debug_List",
        list_id,
        collection_owner, collection_prop,
        collection_owner, active_idx_prop,
        rows=rows, maxrows=rows, columns=len(config["col_names"])
    )

    # Draw details if selected and details_func exists
    idx: int = getattr(collection_owner, active_idx_prop)
    collection: bpy.types.CollectionProperty = getattr(collection_owner, collection_prop)
    if config.get("details_func") and 0 <= idx < len(collection):
        item = collection[idx]
        config["details_func"](context, container, item, idx)


class DGBLOCKS_UL_Shared_Debug_List(bpy.types.UIList):
    """
    Generic UIList for debug panels. Uses a (non-hook) callback to draw each row
    This allows multiple UILists, with differing structures, to share this class
    """

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
        config = get_shared_uilist_config(self.list_id)
        if not config:
            container.label(text=f"Missing config for {self.list_id}")
            return

        config["row_func"](context, container, item, index)
from enum import Enum
import bpy # type: ignore
from ..my_addon_config import min_width_for_weblink_btn_spawn, separator_width_factor, weblink_button_width_factor

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

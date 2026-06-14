
from ...addon_helpers.ui import format_timestamp_for_ui, ui_draw_generic_instance_data, ui_draw_subpanel


def _uilist_draw_uilist_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()
    # header.separator(factor=0.5)  # Account for UIList left padding

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = RTC_item.shader_uid)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    drawhandler_info = f"{RTC_item.draw_phase}/{RTC_item.draw_region}/{RTC_item.draw_space}"
    sub.label(text = drawhandler_info)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.prop(BL_item, "is_enabled", text = "")

ui_structure_for_shader_instance = {
    "Creation Times": [
        ("Shader Creation Time", "shader_creation_timestamp", format_timestamp_for_ui),
        ("Batch Creation Time", "last_batch_creation_timestamp", format_timestamp_for_ui),
        ("Last Draw Time", "last_draw_timestamp", format_timestamp_for_ui)
    ],
    "Draw Statistics":[
        ("Draw Count, of Current Batch", "draw_count_of_batch"),
        ("Batch Count, of Current Shader)", "batch_count_of_shader"),
        ("Batch Creation Duration", "last_batch_creation_duration_nanos")
    ]
}

def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    box = container.box()
    kwargs = {"instance": RTC_item, "structure": ui_structure_for_shader_instance}
    ui_draw_generic_instance_data(context, box, RTC_item, ui_structure_for_shader_instance)


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

def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    box = container.box()

    box.label(text = f"{RTC_item.last_draw_attempt_timestamp}")

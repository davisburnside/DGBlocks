
from ...addon_helpers.ui import ui_draw_generic_instance_data


def _uilist_draw_uilist_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text=RTC_item.timer_uid)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text=f"{RTC_item.frequency:.3f}s")

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.label(text=str(RTC_item.run_count))

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "is_enabled", text="")


ui_structure_for_timer_instance = {
    "Timer Info": [
        ("UID",         "timer_uid"),
        ("Frequency",   "frequency"),
        ("Source Block","src_block_id"),
    ],
    "Runtime Statistics": [
        ("Run Count",   "run_count"),
        ("Error",       "timer_error_str"),
    ],
}


def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    box = container.box()
    ui_draw_generic_instance_data(context, box, RTC_item, ui_structure_for_timer_instance)

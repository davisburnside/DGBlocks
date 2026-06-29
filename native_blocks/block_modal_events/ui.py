
from ...addon_helpers.ui import format_timestamp_for_ui, ui_draw_generic_instance_data


def _uilist_draw_uilist_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text=RTC_item.src_block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text=str(RTC_item.priority))

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.label(text=str(RTC_item.event_count))

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "is_enabled", text="")


ui_structure_for_listener_instance = {
    "Listener Info": [
        ("Source Block", "src_block_id"),
        ("Priority",     "priority"),
        ("Enabled",      "is_enabled"),
    ],
    "Event Filters": [
        ("Ignore Mouse Clicks", "ignore_mouse_click_events"),
        ("Ignore Mouse Move",   "ignore_mouse_move"),
        ("Ignore Scroll",       "ignore_scroll_events"),
        ("Ignore Keyboard",     "ignore_keyboard_events"),
        ("Ignore Window",       "ignore_window_events"),
    ],
    "Runtime Statistics": [
        ("Event Count",       "event_count"),
        ("Last Return",       "last_return"),
        ("Modal Start Time",  "modal_start_timestamp", format_timestamp_for_ui),
        ("Last Event Time",   "last_event_timestamp", format_timestamp_for_ui),
        ("Error",             "listener_error_str"),
    ],
}


def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    box = container.box()
    ui_draw_generic_instance_data(context, box, RTC_item, ui_structure_for_listener_instance)

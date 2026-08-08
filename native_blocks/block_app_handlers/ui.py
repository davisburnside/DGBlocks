
from ...addon_helpers.ui.helpers import format_timestamp_for_ui

# ==============================================================================================================================
# UILIST ROW DRAW
# ==============================================================================================================================

def _uilist_draw_row(context, container, uilist_config_instance, BL_item, RTC_item, list_idx):
    """
    Draws a single row in the App Handler Status UIList.
    Columns: Handler | Enabled | Registered | Subs | Freq (s) | Fires
    """
    col_widths = uilist_config_instance.col_widths
    row = container.row()

    # Handler name
    sub = row.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text=BL_item.handler_type_name)

    # Enabled checkbox (BL prop — allows user to toggle from UIList)
    sub = row.row()
    sub.ui_units_x = col_widths[1]
    sub.prop(BL_item, "is_enabled", text="")

    # Registered icon
    sub = row.row()
    sub.ui_units_x = col_widths[2]
    icon = "CHECKMARK" if (RTC_item is not None and RTC_item.is_registered) else "X"
    sub.label(text="", icon=icon)

    # Subscriber count
    sub = row.row()
    sub.ui_units_x = col_widths[3]
    sub.label(text=str(RTC_item.subscriber_count) if RTC_item else "—")

    # Frequency filter (seconds)
    sub = row.row()
    sub.ui_units_x = col_widths[4]
    if RTC_item and RTC_item.frequency_filter_seconds > 0.0:
        sub.label(text=f"{RTC_item.frequency_filter_seconds:.2f}s")
    else:
        sub.label(text="—")

    # Fire count
    sub = row.row()
    sub.ui_units_x = col_widths[5]
    sub.label(text=str(RTC_item.fire_count) if RTC_item else "—")


# ==============================================================================================================================
# DETAILS SECTION
# ==============================================================================================================================

def _uilist_draw_selection_details(context, container, uilist_config_instance, BL_item, RTC_item, list_idx):
    """
    Draws the details pane below the UIList for the currently selected handler row.
    """
    if RTC_item is None:
        return

    box = container.box()

    # Header
    icon = "CHECKMARK" if RTC_item.is_registered else "X"
    box.label(text=RTC_item.handler_type_name, icon=icon)

    col = box.column(align=True)

    # Registered / enabled status
    row = col.row()
    row.label(text="Registered:")
    row.label(text=str(RTC_item.is_registered))

    row = col.row()
    row.label(text="Enabled:")
    row.label(text=str(RTC_item.is_enabled))

    # Subscriber count
    row = col.row()
    row.label(text="Subscribers:")
    row.label(text=str(RTC_item.subscriber_count))

    col.separator(factor=0.5)

    # Firing statistics
    row = col.row()
    row.label(text="Fire count:")
    row.label(text=str(RTC_item.fire_count))

    row = col.row()
    row.label(text="Last fired:")
    row.label(text=format_timestamp_for_ui(RTC_item.last_fired_timestamp))

    row = col.row()
    row.label(text="Freq. filter (s):")
    if RTC_item.frequency_filter_seconds > 0.0:
        row.label(text=f"{RTC_item.frequency_filter_seconds:.3f}s")
    else:
        row.label(text="None")

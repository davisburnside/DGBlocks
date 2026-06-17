
from ...addon_helpers.ui import ui_draw_generic_instance_data

# ==============================================================================================================================
# UILIST ROW DRAW
# ==============================================================================================================================

def _uilist_draw_row(context, container, uilist_config_instance, BL_item, RTC_item, list_idx):
    """
    Draws a single row in the Mesh Extract UIList.
    Columns: Object Name | Valid | Total Time (ms) | Read Count
    """
    col_widths = uilist_config_instance.col_widths

    row = container.row()

    # Object name
    sub = row.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text=RTC_item.object_name)

    # Valid icon
    sub = row.row()
    sub.ui_units_x = col_widths[1]
    icon = "CHECKMARK" if RTC_item.is_valid else "ERROR"
    sub.label(text="", icon=icon)

    # Total time (ms)
    sub = row.row()
    sub.ui_units_x = col_widths[2]
    total_meta = RTC_item.extract_metadata.get("_total", {})
    duration_ms = total_meta.get("duration_ms", 0.0)
    sub.label(text=f"{duration_ms:.2f}")

    # Read count
    sub = row.row()
    sub.ui_units_x = col_widths[3]
    read_count = total_meta.get("read_count", 0)
    sub.label(text=str(read_count))


# ==============================================================================================================================
# DETAILS SECTION
# ==============================================================================================================================

_ui_structure_for_extract_instance = {
    "Object Info": [
        ("Object",    "object_name"),
        ("Valid",     "is_valid"),
        ("Error",     "error_str"),
    ],
}


def _uilist_draw_selection_details(context, container, uilist_config_instance, BL_item, RTC_item, list_idx):
    """
    Draws the details pane below the UIList for the currently selected row.
    Shows per-attribute timing metadata and error info.
    """
    if RTC_item is None:
        return

    box = container.box()

    # Object header info
    ui_draw_generic_instance_data(context, box, RTC_item, _ui_structure_for_extract_instance)

    # Per-attribute metadata table
    metadata = RTC_item.extract_metadata
    if not metadata:
        box.label(text="No metadata available", icon="INFO")
        return

    col = box.column(align=True)
    col.label(text="Attribute Timing:", icon="TIME")

    header_row = col.row()
    header_row.label(text="Attribute")
    header_row.label(text="Time (ms)")
    header_row.label(text="Shape")
    header_row.label(text="Reads")

    col.separator(factor=0.5)

    for label, meta in metadata.items():
        row = col.row()
        row.label(text=label)
        row.label(text=f"{meta.get('duration_ms', 0.0):.3f}")
        row.label(text=str(meta.get("shape", 0)))
        row.label(text=str(meta.get("read_count", 0)))

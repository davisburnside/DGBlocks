
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

def _format_shape(shape) -> str:
    """Return a tidy shape string: '(1024, 3)' or '-' for missing/empty."""
    if not shape:
        return "-"
    return str(shape)


def _uilist_draw_selection_details(context, container, uilist_config_instance, BL_item, RTC_item, list_idx):
    """
    Draws the details pane below the UIList for the currently selected row.
    Shows validity, error info, and per-attribute timing/shape metadata.
    """
    if RTC_item is None:
        return

    box = container.box()

    # ---- Header: object name + validity ----
    header = box.row()
    icon = "CHECKMARK" if RTC_item.is_valid else "ERROR"
    header.label(text=RTC_item.object_name, icon=icon)

    # ---- Error string (shown prominently when invalid) ----
    if not RTC_item.is_valid and RTC_item.error_str:
        err_box = box.box()
        err_box.alert = True
        for line in RTC_item.error_str.splitlines():
            err_box.label(text=line, icon="ERROR" if line == RTC_item.error_str.splitlines()[0] else "NONE")

    # ---- Per-attribute metadata table ----
    metadata = RTC_item.extract_metadata
    if not metadata:
        box.label(text="No metadata available", icon="INFO")
        return

    # Separate the _total summary row from per-attribute rows
    attr_rows = {k: v for k, v in metadata.items() if k != "_total"}
    total_meta = metadata.get("_total", {})

    if attr_rows:
        col = box.column(align=True)
        col.label(text="Attributes:", icon="TIME")

        header_row = col.row()
        header_row.label(text="Attribute")
        header_row.label(text="ms")
        header_row.label(text="Shape")
        header_row.label(text="Reads")

        col.separator(factor=0.3)

        for label, meta in attr_rows.items():
            row = col.row()
            row.label(text=label)
            row.label(text=f"{meta.get('duration_ms', 0.0):.3f}")
            row.label(text=_format_shape(meta.get("shape")))
            row.label(text=str(meta.get("read_count", 0)))

    # ---- Total summary ----
    if total_meta:
        box.separator(factor=0.5)
        summary = box.row()
        summary.label(text=f"Total: {total_meta.get('duration_ms', 0.0):.2f} ms", icon="SORTTIME")
        summary.label(text=f"Run #{total_meta.get('read_count', 0)}")

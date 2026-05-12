# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

import bpy  # type: ignore
from .....addon_helpers.ui_drawing_helpers import ui_draw_list_headers

# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Source Block", "Logger Name", "Log Level")
col_widths = (3, 5, 3)


def _uilayout_draw_logger_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text=f"All Loggers ({len(context.scene.dgblocks_core_props.managed_loggers)})")
    if panel_body is not None:

        # Draw column titles
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw UIList body
        row = panel_body.row()
        row_count = len(core_props.managed_loggers)
        row.template_list(
            "DGBLOCKS_UL_Loggers",
            "",
            core_props, "managed_loggers",          # Collection property
            core_props, "managed_loggers_selected_idx",  # Active index property
            rows=row_count,
            maxrows=row_count,
            columns=row_count,
        )


class DGBLOCKS_UL_Loggers(bpy.types.UIList):
    """UIList to display RTC loggers with log-level dropdown."""

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):

        row = container.row(align=True)
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.src_block_id)
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.label(text=item.logger_name)
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.prop(item, "level_name", text="")

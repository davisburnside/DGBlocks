# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

import bpy  # type: ignore
from .....addon_helpers.ui import ui_draw_shared_debug_list, set_shared_uilist_config

# ==============================================================================================================================
# UI
# ==============================================================================================================================

set_shared_uilist_config(
    list_id="LOGGERS_LIST",
    col_names=("Source Block", "Logger Name", "Log Level"),
    col_widths=(3, 5, 3),
    columns_def=[
        {"type": "LABEL", "field": "src_block_id"},
        {"type": "LABEL", "field": "logger_name"},
        {"type": "PROP", "field": "level_name", "icon_only": False}
    ],
    details_func=None
)


def _uilayout_draw_logger_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text=f"All Loggers ({len(core_props.managed_loggers)})")
    if panel_body is not None:
        ui_draw_shared_debug_list(
            context, panel_body, "LOGGERS_LIST", 
            core_props, "managed_loggers", "managed_loggers_selected_idx", 
            rows=max(1, len(core_props.managed_loggers))
        )

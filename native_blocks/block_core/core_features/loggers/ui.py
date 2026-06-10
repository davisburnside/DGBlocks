# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

import bpy  # type: ignore
from .....addon_helpers.ui import v2_draw_shared_uilist

# ==============================================================================================================================
# UI
# ==============================================================================================================================


def _uilayout_draw_logger_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_loggers", default_closed=True)
    panel_header.label(text=f"All Loggers ({len(core_props.managed_loggers)})")
    if panel_body is not None:
        v2_draw_shared_uilist(
            context, panel_body, "LOGGERS_LIST", 
            core_props, "managed_loggers", "managed_loggers_selected_idx", 
            rows=max(1, len(core_props.managed_loggers))
        )

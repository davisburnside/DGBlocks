# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

import bpy
from .....addon_helpers.ui import ui_draw_shared_debug_list, set_shared_uilist_config
from ...core_helpers.constants import _BLOCK_ID as core_block_id, Core_Runtime_Cache_Members
from ...core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache  # type: ignore

# ==============================================================================================================================
# UI
# ==============================================================================================================================

def _uilayout_draw_blocks_uilist_selection_detail(context, container, item):
    if not item.is_valid:
        box = container.box()
        box.alert = True
        box.label(text=f"Error: {item.error_message}", icon='ERROR')
    elif not item.is_block_enabled:
        box = container.box()
        box.alert = True
        box.label(text="Block is disabled.", icon='INFO')
    else:
        box = container.box()
        box.label(text="Block is active and valid.", icon='CHECKMARK')

set_shared_uilist_config(
    list_id="BLOCKS_LIST",
    col_names=("Valid", "Block ID", "Enabled"),
    col_widths=(1, 3, 1),
    columns_def=[
        {"type": "ICON", "field": "is_valid", "icon_true": "CHECKMARK", "icon_false": "ERROR"},
        {"type": "LABEL", "field": "block_id"},
        {"type": "ICON", "field": "is_block_enabled", "icon_true": "CHECKMARK", "icon_false": "X"}
    ],
    details_func=_uilayout_draw_blocks_uilist_selection_detail
)

def _uilayout_draw_block_manager_settings(context, container):

    box = container.box()
    core_props = context.scene.dgblocks_core_props

    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_block_mgmt", default_closed=True)
    panel_header.label(text=f"All Blocks ({len(core_props.managed_blocks)})")
    if panel_body is not None:
        ui_draw_shared_debug_list(
            context, panel_body, "BLOCKS_LIST", 
            core_props, "managed_blocks", "managed_blocks_selected_idx", 
            rows=max(1, len(core_props.managed_blocks))
        )

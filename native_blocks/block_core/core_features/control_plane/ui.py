# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

import bpy  # type: ignore
from .....addon_helpers.ui_drawing_helpers import ui_draw_list_headers
from ...core_helpers.constants import _BLOCK_ID as core_block_id

# ==============================================================================================================================
# UI
# ==============================================================================================================================

col_names = ("Name", "Should Enable?", "Is Enabled?")
col_widths = (2, 1, 1)


def _uilayout_draw_block_uilist_selection_detail(context, container):

    # Show disabled reason for selected alert row
    core_props = context.scene.dgblocks_core_props
    is_anything_selected = 0 <= core_props.managed_blocks_selected_idx < len(core_props.managed_blocks)
    if core_props.managed_blocks and is_anything_selected:
        active_block = core_props.managed_blocks[core_props.managed_blocks_selected_idx]
        is_alert = active_block.should_block_be_enabled and not active_block.is_block_enabled
        if is_alert and active_block.block_disabled_reason:
            box = container.box()
            box.alert = True
            box.label(text=f"Reason: {active_block.block_disabled_reason}", icon='INFO')


def _uilayout_draw_block_manager_settings(context, container):

    box = container.box()
    core_props = context.scene.dgblocks_core_props
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_block_mgmt", default_closed=True)
    panel_header.label(text=f"All Blocks ({len(context.scene.dgblocks_core_props.managed_blocks)})")
    if panel_body is not None:

        # Draw column headers - should match draw_item layout exactly
        ui_draw_list_headers(panel_body, col_names, col_widths)

        # Draw the UIList
        row = panel_body.row()
        row_count = len(core_props.managed_blocks)
        row.template_list(
            "DGBLOCKS_UL_Blocks",
            "",
            core_props, "managed_blocks",           # Collection property
            core_props, "managed_blocks_selected_idx",  # Active index property
            rows=row_count,
            maxrows=row_count,
            columns=row_count,
        )

        # Show disabled reason for selected alert row
        _uilayout_draw_block_uilist_selection_detail(context, container)


class DGBLOCKS_UL_Blocks(bpy.types.UIList):
    """UIList to display RTC blocks with enable toggle and alert states."""

    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):

        is_alert = item.should_block_be_enabled and not item.is_block_enabled
        if is_alert:
            container.alert = True
        row = container.row()
        row.enabled = item.block_id != core_block_id  # Prevent core block from being disabled

        # Block name
        sub = row.row()
        sub.ui_units_x = col_widths[0]
        sub.label(text=item.block_id)

        # Should enable toggle
        sub = row.row()
        sub.ui_units_x = col_widths[1]
        sub.prop(item, "should_block_be_enabled", text="", icon='CHECKBOX_HLT' if item.should_block_be_enabled else 'CHECKBOX_DEHLT')

        # Is enabled status
        sub = row.row()
        sub.ui_units_x = col_widths[2]
        sub.label(text="", icon='CHECKMARK' if item.is_block_enabled else 'X')

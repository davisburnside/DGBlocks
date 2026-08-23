"""Debug UI for latest geometry-action results."""

import time

from ...addon_helpers.ui.helpers import ui_draw_subpanel
from .data_structures import Enum_Op_Type


_OP_ICONS = {
    Enum_Op_Type.READ:     "IMPORT",
    Enum_Op_Type.CALLBACK: "SCRIPTPLUGINS",
}


def _clock_str(timestamp: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def _draw_action_body(context, container, action) -> None:
    info = container.row()
    info.enabled = False
    info.label(
        text=f"{action.geometry_type} · {action.geometry_target} · {action.read_source} · "
             f"{action.object_mode} · {action.read_count}R / {action.callback_count}C"
    )
    info.label(text=f"Run at {_clock_str(action.timestamp_start)}")

    if action.error_str:
        error_box = container.box()
        error_box.alert = True
        for line in str(action.error_str).splitlines():
            error_box.label(text=line, icon="ERROR")

    if not action.ops:
        return

    headings = container.split(factor=0.68)
    headings.label(text="Name")
    remaining = headings.split(factor=0.55)
    remaining.label(text="Duration")
    remaining.label(text="Shape")

    col = container.column(align=True)
    for op in action.ops:
        row = col.split(factor=0.68)
        if not op.is_valid:
            row.alert = True
        row.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
        remaining = row.split(factor=0.55)
        remaining.label(text=f"{op.duration_ms:.3f} ms")
        remaining.label(text=op.shape or "-")

        if op.error_file and op.error_line is not None:
            location_row = col.row()
            location_row.alert = True
            location_row.label(text=f"{op.error_file}:{op.error_line}", icon="FILE_SCRIPT")
        if op.error_str:
            error_row = col.row()
            error_row.alert = True
            error_row.label(text=op.error_str, icon="ERROR")


def ui_draw_geometry_action_results(context, layout, results: dict) -> None:
    """Draw results in first-call insertion order; replacement runs retain their position."""
    if not results:
        layout.label(text="No stored geometry actions", icon="INFO")
        return

    for result_key, result in results.items():
        action = result.last_action
        if action is None:
            continue

        panel_uid = f"geometry_action_{result.declaration_id}_{result.object_session_uid}"
        panel_header, _panel_body = ui_draw_subpanel(
            context, layout, panel_uid, "", _draw_action_body, action=action,
        )

        status = panel_header.row(align=True)
        status.alert = not action.is_valid
        status.label(text="", icon="CHECKMARK" if action.is_valid else "ERROR")

        left = panel_header.row(align=True)
        left.alignment = "LEFT"
        left.label(text=f"Duration: {action.duration_ms:.3f} ms")
        left.label(text=f"Run Count: {action.action_uid}")
        left.label(text=f"{action.label} · {result.object_name}")

        right = panel_header.row(align=True)
        right.alignment = "RIGHT"
        clear = right.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH", emboss=False
        )
        clear.declaration_id = result.declaration_id
        clear.object_name = result.object_name
        copy = right.operator(
            "dgblocks.geometry_actions_copy_result", text="", icon="COPYDOWN", emboss=False
        )
        copy.result_key = result_key
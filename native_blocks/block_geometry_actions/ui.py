"""Debug UI for latest geometry-action results."""

import time

from ...addon_helpers.ui.helpers import ui_draw_subpanel
from .data_structures import Enum_Op_Type


_OP_ICONS = {
    Enum_Op_Type.READ:     "IMPORT",
    Enum_Op_Type.CALLBACK: "SCRIPTPLUGINS",
}

def _pad_width_for(values, min_width: int = 0) -> int:
    """Widest rendered length among `values`, so every row's text pads to a shared column
    width without guessing a pixel-per-character conversion for ui_units_x."""
    return max([min_width, *(len(str(value)) for value in values)])


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

    headings = container.split(factor=0.62)
    headings.label(text="Name")
    remaining = headings.split(factor=0.42)
    remaining.label(text="Duration")
    shape_and_type = remaining.split(factor=0.55)
    shape_and_type.label(text="Shape")
    shape_and_type.label(text="Type")

    col = container.column(align=True)
    for op in action.ops:
        row = col.split(factor=0.62)
        if not op.is_valid:
            row.alert = True
        row.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
        remaining = row.split(factor=0.42)
        remaining.label(text=f"{op.duration_ms:.3f} ms")
        shape_and_type = remaining.split(factor=0.55)
        shape_and_type.label(text=op.shape or "-")
        shape_and_type.label(text=op.data_type or "-")

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

    visible = [(key, r) for key, r in results.items() if r.last_action is not None]
    if not visible:
        return

    # Right/zero-pad the numbers themselves to a shared width instead of guessing a
    # ui_units_x cell size — the label then shrink-wraps to that fixed-length text, so
    # every row lines up without over-allocating space the content doesn't need.
    duration_width = _pad_width_for(
        (f"{r.last_action.duration_ms:.3f}" for _, r in visible)
    )
    run_count_width = _pad_width_for(
        (r.last_action.action_uid for _, r in visible), min_width=3
    )

    for result_key, result in visible:
        action = result.last_action

        panel_uid = f"geometry_action_{result.declaration_id}_{result.object_session_uid}"
        panel_header, _panel_body = ui_draw_subpanel(
            context, layout, panel_uid, "", _draw_action_body, action=action,
        )

        status = panel_header.row(align=True)
        status.alert = not action.is_valid
        status.label(text="", icon="CHECKMARK" if action.is_valid else "ERROR")

        # A bare label() defaults to EXPAND alignment, so sibling labels dropped straight
        # on panel_header would fight over the header's width instead of sizing to their
        # own content. Grouping runtime+run-count in one LEFT-aligned row makes that row
        # shrink-wrap to its text, leaving the desc row (left at default EXPAND) everything
        # else, right up to the RIGHT-pinned buttons.
        info = panel_header.row(align=True)
        info.alignment = "LEFT"
        info.label(text=f"{action.duration_ms:>{duration_width}.3f} ms")
        info.separator()
        info.label(text=f"{action.action_uid:0{run_count_width}d} runs")

        panel_header.label(text=f"{action.label} · {result.object_name}")

        buttons = panel_header.row(align=True)
        buttons.alignment = "RIGHT"
        buttons.ui_units_x = 3.2
        clear = buttons.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH"
        )
        clear.declaration_id = result.declaration_id
        clear.object_name = result.object_name
        copy = buttons.operator(
            "dgblocks.geometry_actions_copy_result", text="", icon="COPYDOWN"
        )
        copy.result_key = result_key
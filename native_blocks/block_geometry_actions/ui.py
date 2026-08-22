"""
ui.py — debug draw for stored geometry-action results.

There is no UIList and no data mirror: results hold numpy arrays that cannot be
represented in Blender data. This is a plain looped draw straight off the RTC results.

COLLAPSIBILITY
    Blender's real sub-panels (bl_parent_id) cannot be generated per runtime record, so
    every action/object result is a box + a TRIA toggle backed by one CSV StringProperty of
    expanded keys (`debug_expanded_keys`). The stable key does not include the run number,
    so a live replacement preserves the open state.

Key: "<declaration_id>|<object_session_uid>"
"""

import time

from .data_structures import Enum_Op_Type

_OP_ICONS = {
    Enum_Op_Type.READ:     "IMPORT",
    Enum_Op_Type.CALLBACK: "SCRIPTPLUGINS",
}


# ==============================================================================================================================
# EXPANSION STATE  (CSV set on one StringProperty)
# ==============================================================================================================================

def expanded_keys(props) -> set:
    return {k for k in (props.debug_expanded_keys or "").split(",") if k}


def is_expanded(props, key: str) -> bool:
    return key in expanded_keys(props)


def toggle_expanded_key(props, key: str) -> None:
    keys = expanded_keys(props)
    keys.discard(key) if key in keys else keys.add(key)
    props.debug_expanded_keys = ",".join(sorted(keys))


def _clock_str(timestamp: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def _draw_toggle(layout, props, key: str, text: str, icon: str = "NONE"):
    """Draw a collapsible header row and return (row, is_open)."""
    row = layout.row(align=True)
    open_now = is_expanded(props, key)
    toggle = row.operator(
        "dgblocks.geometry_actions_toggle_expanded",
        text   = "",
        icon   = "TRIA_DOWN" if open_now else "TRIA_RIGHT",
        emboss = False,
    )
    toggle.expand_key = key
    row.label(text=text, icon=icon)
    return row, open_now


def _draw_action(box, action) -> None:
    info = box.row()
    info.enabled = False
    info.label(
        text=f"{action.geometry_type} · {action.geometry_target} · {action.read_source} · "
             f"{action.object_mode} · {action.read_count}R / {action.callback_count}C"
    )

    if action.error_str:
        error_box = box.box()
        error_box.alert = True
        for line in str(action.error_str).splitlines():
            error_box.label(text=line, icon="ERROR")

    if not action.ops:
        return

    headings = box.split(factor=0.68)
    headings.label(text="Name")
    remaining = headings.split(factor=0.55)
    remaining.label(text="Duration")
    remaining.label(text="Shape")

    col = box.column(align=True)
    for op in action.ops:
        row = col.split(factor=0.68)
        if not op.is_valid:
            row.alert = True
        row.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
        remaining = row.split(factor=0.55)
        remaining.label(text=f"{op.duration_ms:.3f} ms")
        remaining.label(text=op.shape or "-")
        if op.error_str:
            error_row = col.row()
            error_row.alert = True
            error_row.label(text=op.error_str, icon="ERROR")


# ==============================================================================================================================
# PUBLIC PANEL DRAW
# ==============================================================================================================================

def ui_draw_geometry_action_results(context, layout, results: dict, props) -> None:
    """Draw every latest action/object result, most recent activity first."""
    if not results:
        layout.label(text="No stored geometry actions", icon="INFO")
        return

    for result_key, result in sorted(
        results.items(), key=lambda item: item[1].timestamp_last_action, reverse=True
    ):
        action = result.last_action
        if action is None:
            continue
        outer  = layout.box()

        row, open_now = _draw_toggle(
            outer, props, result_key,
            f"#{action.action_uid}  {action.label}  ·  {result.object_name}",
            icon = "CHECKMARK" if result.is_valid else "ERROR",
        )
        summary = row.row()
        summary.alignment = "RIGHT"
        summary.label(text=_clock_str(action.timestamp_start))
        summary.label(text=f"{action.duration_ms:.2f} ms")

        clear = row.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH", emboss=False
        )
        clear.declaration_id = result.declaration_id
        clear.object_name    = result.object_name

        if not open_now:
            continue

        _draw_action(outer, action)

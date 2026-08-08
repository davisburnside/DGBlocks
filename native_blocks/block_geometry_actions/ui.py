"""
ui.py — debug draw for stored geometry-action results.

There is no UIList and no data mirror: results hold numpy arrays that cannot be
represented in Blender data. This is a plain looped draw straight off the RTC stacks.

COLLAPSIBILITY
    Blender's real sub-panels (bl_parent_id) cannot be generated per runtime record, so
    every level here is a box + a TRIA toggle backed by one CSV StringProperty of expanded
    keys (`debug_expanded_keys`). That makes every level — object stack, individual pass,
    op group — independently collapsible at any depth.

Keys are hierarchical strings:
    "<declaration_id>|<object_name>"                  → a result stack
    "<declaration_id>|<object_name>#<action_uid>"     → one pass inside it
"""

import time

from .data_structures import Enum_Op_Type

_OP_ICONS = {
    Enum_Op_Type.READ:     "IMPORT",
    Enum_Op_Type.CALLBACK: "SCRIPTPLUGINS",
    Enum_Op_Type.GROUP:    "DOWNARROW_HLT",
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


def _counts_str(instance) -> str:
    return " ".join(
        f"{name[0]}{getattr(instance, name).count}" for name in instance.domain_names
    )


# ==============================================================================================================================
# ONE PASS (action record)
# ==============================================================================================================================

def _draw_action(layout, action, props, stack_key: str) -> None:
    key = f"{stack_key}#{action.action_uid}"
    box = layout.box()

    row, open_now = _draw_toggle(
        box, props, key,
        f"#{action.action_uid}  {action.label}",
        icon = "CHECKMARK" if action.is_valid else "ERROR",
    )
    meta = row.row()
    meta.alignment = "RIGHT"
    meta.label(text=_clock_str(action.timestamp_start))
    meta.label(text=f"{action.duration_ms:.2f} ms")

    if not open_now:
        return

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

    col = box.column(align=True)
    target = col
    for op in action.ops:
        if op.op_type == Enum_Op_Type.GROUP:
            target = col.box()
            target.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
            continue
        row = target.row()
        if not op.is_valid:
            row.alert = True
        row.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
        row.label(text=f"{op.duration_ms:.3f}")
        row.label(text=op.shape or "-")
        if op.error_str:
            row.label(text=op.error_str, icon="ERROR")


# ==============================================================================================================================
# PUBLIC PANEL DRAW
# ==============================================================================================================================

def ui_draw_geometry_action_stacks(context, layout, stacks: dict, props) -> None:
    """Draw every retained result stack, most recent activity first."""
    if not stacks:
        layout.label(text="No stored geometry actions", icon="INFO")
        return

    def _latest_timestamp(item) -> float:
        _key, stack = item
        return stack[-1].timestamp_last_action if len(stack) else 0.0

    for stack_key, stack in sorted(stacks.items(), key=_latest_timestamp, reverse=True):
        if not len(stack):
            continue
        newest = stack[-1]
        outer  = layout.box()

        row, open_now = _draw_toggle(
            outer, props, stack_key,
            f"{newest.object_name}  ·  {newest.declaration_id}",
            icon = "CHECKMARK" if newest.is_valid else "ERROR",
        )
        summary = row.row()
        summary.alignment = "RIGHT"
        summary.label(text=_counts_str(newest))
        summary.label(text=f"{len(stack)}/{stack.maxlen} kept")

        clear = row.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH", emboss=False
        )
        clear.declaration_id = newest.declaration_id
        clear.object_name    = newest.object_name

        if not open_now:
            continue

        max_actions = max(1, props.debug_max_actions_shown)
        # Newest result first, and newest pass first within each result.
        for instance in reversed(stack):
            actions_newest_first = list(reversed(instance.actions))
            for action in actions_newest_first[:max_actions]:
                _draw_action(outer, action, props, stack_key)
            hidden = len(actions_newest_first) - max_actions
            if hidden > 0:
                hidden_row = outer.row()
                hidden_row.enabled = False
                hidden_row.label(text=f"...{hidden} older pass(es) hidden")

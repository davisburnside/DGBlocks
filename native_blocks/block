"""
ui.py — debug draw for stored mesh-extract instances.

There is no UIList and no data mirror: instances hold numpy arrays that cannot be
represented in Blender data. This is a plain looped draw straight off the RTC list.

Group_Tag ops are rendered as section headers; subsequent ops are nested under the
most recent group until another Group_Tag appears.
"""

import time

from .data_structures import Enum_Mesh_Op_Type

_OP_ICONS = {
    Enum_Mesh_Op_Type.READ:     "IMPORT",
    Enum_Mesh_Op_Type.CALLBACK: "SCRIPTPLUGINS",
    Enum_Mesh_Op_Type.WRITE:    "EXPORT",
    Enum_Mesh_Op_Type.GROUP:    "DOWNARROW_HLT",
}


def _instance_key(instance) -> str:
    return f"{instance.object_name}|{instance.slot}"


def _clock_str(timestamp: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


# ==============================================================================================================================
# INSTANCE HEADER + BODY
# ==============================================================================================================================

def _draw_instance_header(layout, instance, props, is_expanded: bool) -> None:
    row = layout.row(align=True)

    toggle = row.operator(
        "dgblocks.mesh_extract_toggle_instance",
        text  = "",
        icon  = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT",
        emboss = False,
    )
    toggle.instance_key = _instance_key(instance)

    row.label(text="", icon="CHECKMARK" if instance.is_valid else "ERROR")

    name_row = row.row()
    name_row.label(text=instance.object_name)
    if instance.slot != "default":
        name_row.label(text=f"[{instance.slot}]")

    counts = row.row()
    counts.alignment = "RIGHT"
    counts.label(
        text=f"v{instance.vertex.count} e{instance.edge.count} "
             f"f{instance.face.count} c{instance.corner.count}"
    )
    counts.label(text=f"{len(instance.actions)} action(s)")

    clear = row.operator("dgblocks.mesh_extract_clear", text="", icon="TRASH", emboss=False)
    clear.object_name = instance.object_name


def _draw_data_inventory(layout, instance) -> None:
    box = layout.box()
    box.label(text="Stored Data", icon="RNA")
    for domain_name in ("vertex", "edge", "face", "corner"):
        domain_obj = getattr(instance, domain_name)
        populated  = domain_obj.populated_field_names()
        if not populated:
            continue
        row = box.row()
        row.label(text=f"{domain_name}:")
        col = row.column(align=True)
        for name in populated:
            col.label(text=name)
    if instance.derived:
        row = box.row()
        row.label(text="derived:")
        col = row.column(align=True)
        for key in instance.derived:
            col.label(text=key)


def _draw_action(layout, action, show_ops: bool) -> None:
    box = layout.box()

    header = box.row(align=True)
    header.label(text="", icon="CHECKMARK" if action.is_valid else "ERROR")
    header.label(text=f"#{action.action_uid}  {action.label}")

    meta = header.row()
    meta.alignment = "RIGHT"
    meta.label(text=_clock_str(action.timestamp_start))
    meta.label(text=f"{action.duration_ms:.2f} ms")

    detail = box.row()
    detail.enabled = False
    detail.label(
        text=f"{action.read_source} · {action.object_mode} · "
             f"{action.read_count}R / {action.callback_count}C / {action.write_count}W"
    )

    if action.error_str:
        error_box = box.box()
        error_box.alert = True
        for line in str(action.error_str).splitlines():
            error_box.label(text=line, icon="ERROR")

    if not show_ops or not action.ops:
        return

    # Render ops, grouping those that follow a Group_Tag under an indented section.
    current_group_box = None
    col = box.column(align=True)

    for op in action.ops:
        if op.op_type == Enum_Mesh_Op_Type.GROUP:
            # Start a new group section
            current_group_box = col.box()
            current_group_box.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
            continue

        target = current_group_box if current_group_box is not None else col
        head = target.row()
        head.label(text="Op")
        head.label(text="ms")
        head.label(text="Shape")
        head.label(text="Detail")
        break

    # Second pass: actual op rows (after the header row above)
    current_group_box = None
    for op in action.ops:
        if op.op_type == Enum_Mesh_Op_Type.GROUP:
            current_group_box = col.box()
            current_group_box.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
            continue
        target = current_group_box if current_group_box is not None else col
        row = target.row()
        if not op.is_valid:
            row.alert = True
        row.label(text=op.label, icon=_OP_ICONS.get(op.op_type, "DOT"))
        row.label(text=f"{op.duration_ms:.3f}")
        row.label(text=op.shape or "-")
        row.label(text=op.error_str or op.detail or "")


# ==============================================================================================================================
# PUBLIC PANEL DRAW
# ==============================================================================================================================

def ui_draw_mesh_extract_instances(context, layout, instances, props) -> None:
    """Draw every stored instance, newest activity first."""
    if not instances:
        layout.label(text="No stored mesh actions", icon="INFO")
        return

    ordered = sorted(instances, key=lambda i: i.timestamp_last_action, reverse=True)
    max_actions = max(1, props.debug_max_actions_shown)

    for instance in ordered:
        outer       = layout.box()
        key         = _instance_key(instance)
        is_expanded = props.debug_expanded_instance_key == key

        _draw_instance_header(outer, instance, props, is_expanded)
        if not is_expanded:
            continue

        _draw_data_inventory(outer, instance)

        actions_newest_first = list(reversed(instance.actions))
        hidden = len(actions_newest_first) - max_actions
        for action in actions_newest_first[:max_actions]:
            _draw_action(outer, action, props.debug_show_op_details)
        if hidden > 0:
            row = outer.row()
            row.enabled = False
            row.label(text=f"...{hidden} older action(s) hidden")
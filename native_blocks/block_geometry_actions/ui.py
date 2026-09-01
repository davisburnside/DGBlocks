"""Debug UI for latest geometry-action results."""

import time

from ...addon_helpers.ui.helpers import ui_draw_subpanel, wrap_text_to_lines
from .data_structures import Enum_Op_Type


_OP_ICONS = {
    Enum_Op_Type.READ:     "IMPORT",
    Enum_Op_Type.CALLBACK: "SCRIPTPLUGINS",
    Enum_Op_Type.SETUP:    "TIME",
}

# Plain-language meaning of each summary-line field, keyed by its raw enum string.
# Drawn on-demand by the [?] popup so the always-visible line can stay terse.
_GEOMETRY_TYPE_INFO = {
    "MESH": (
        "This GeoAction ran against Mesh data — vertices, edges, faces, and face "
        "corners — instead of a Curves object's points and splines."
    ),
    "CURVES": (
        "This GeoAction ran against Curves data — points and splines — instead of "
        "a Mesh object's vertices, edges, and faces."
    ),
    "UNKNOWN": (
        "DGBlocks could not resolve a supported geometry type (neither Mesh nor "
        "Curves) for the target object."
    ),
}

_GEOMETRY_TARGET_INFO = {
    "AUTO": (
        "The declaration let DGBlocks pick automatically: NATIVE_DATA for Mesh, "
        "Curve, and Curves objects, or MESH_EVALUATED (post-modifier mesh) for "
        "everything else — Metaball, Font, Surface, Point Cloud, etc."
    ),
    "MESH_EVALUATED": (
        "Data came from the object's evaluated, post-modifier mesh via to_mesh() — "
        "always mesh domains, even for non-mesh source objects. Index space may not "
        "match the original object, so this is read-only, not write-back safe."
    ),
    "NATIVE_DATA": (
        "Data came from the object's own native datablock — mesh domains for Mesh "
        "objects, curve domains (point/curve) for Curve and Curves objects."
    ),
}

_READ_SOURCE_INFO = {
    "EVALUATED": (
        "Read through evaluated_get(depsgraph) — post-modifier data. Index space "
        "may not match the original object, so it is not safe to write these "
        "results back."
    ),
    "ORIGINAL": (
        "Read from the editable base datablock — Object Mode reads object.data "
        "directly, Edit Mode reads it after update_from_editmode(). Index space "
        "matches the original object, so it is safe to write back."
    ),
}

_OBJECT_MODE_INFO = {
    "OBJECT":        "The object was in Object Mode — data reflects its stored state, with no in-progress edit-mode changes.",
    "EDIT":          "The object was in Edit Mode — data may include unsaved edits not yet committed to the base datablock.",
    "SCULPT":        "The object was in Sculpt Mode.",
    "VERTEX_PAINT":  "The object was in Vertex Paint Mode.",
    "WEIGHT_PAINT":  "The object was in Weight Paint Mode.",
    "TEXTURE_PAINT": "The object was in Texture Paint Mode.",
    "PARTICLE_EDIT": "The object was in Particle Edit Mode.",
    "POSE":          "The object's armature was in Pose Mode.",
}


def _object_mode_description(object_mode: str) -> str:
    if not object_mode:
        return "No object mode was recorded for this action."
    return _OBJECT_MODE_INFO.get(
        object_mode, f"The object was in {object_mode.title()} mode when this action ran."
    )


def ui_draw_geometry_action_explanation(
    layout, geometry_type: str, geometry_target: str, read_source: str, object_mode: str
) -> None:
    """Popup body for the [?] button: plain-language meaning of one action's
    geometry_type / geometry_target / read_source / object_mode values."""
    sections = (
        ("Geometry Type", geometry_type, _GEOMETRY_TYPE_INFO.get(
            geometry_type, f"Unrecognized geometry type '{geometry_type}'."
        )),
        ("Geometry Target", geometry_target, _GEOMETRY_TARGET_INFO.get(
            geometry_target, f"Unrecognized geometry target '{geometry_target}'."
        )),
        ("Read Source", read_source, _READ_SOURCE_INFO.get(
            read_source, f"Unrecognized read source '{read_source}'."
        )),
        ("Object Mode", object_mode or "-", _object_mode_description(object_mode)),
    )
    for index, (title, value, description) in enumerate(sections):
        if index > 0:
            layout.separator(factor=0.5)
        box = layout.box()
        box.label(text=f"{title} — {value}", icon="DOT")
        # Blender labels have no bold/brightness toggle short of `alert` (which reads as
        # an error state). Dimming the body instead gives the header the same visual lift
        # by contrast, without borrowing the alert color.
        body = box.column()
        body.enabled = False
        for line in wrap_text_to_lines(description, max_width_px=340):
            body.label(text=line)


def _pad_width_for(values, min_width: int = 0) -> int:
    """Widest rendered length among `values`, so every row's text pads to a shared column
    width without guessing a pixel-per-character conversion for ui_units_x."""
    return max([min_width, *(len(str(value)) for value in values)])


def _clock_str(timestamp: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(timestamp))


def _draw_action_body(context, container, action) -> None:
    # `info` is left at the default EXPAND alignment on purpose: non-EXPAND alignment
    # (LEFT/CENTER/RIGHT) sizes a label from a rough character estimate rather than its
    # real rendered width, which is fine for short fixed-length text (the timestamp
    # below) but was silently truncating this row's long metadata string. help_btn is an
    # icon-only operator so it stays naturally small regardless; timestamp is pinned to a
    # fixed width since "Run at HH:MM:SS" is always short — that leaves text_row, the only
    # other EXPAND-flagged child, free to claim the rest of the row's real width.
    info = container.row()

    help_btn = info.operator(
        "dgblocks.geometry_actions_explain_action", text="", icon="QUESTION"
    )
    help_btn.geometry_type = str(action.geometry_type)
    help_btn.geometry_target = str(action.geometry_target)
    help_btn.read_source = str(action.read_source)
    help_btn.object_mode = str(action.object_mode)

    text_row = info.row()
    text_row.enabled = False
    text_row.label(
        text=f"{action.geometry_type} | {action.geometry_target} | "
             f"{action.read_source} | {action.object_mode}"
    )

    timestamp = info.row()
    timestamp.enabled = False
    timestamp.alignment = "RIGHT"
    timestamp.ui_units_x = 6.5
    timestamp.label(text=f"Run at {_clock_str(action.timestamp_start)}")

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
        info.label(text="|")
        info.label(text=f"{action.action_uid:0{run_count_width}d} runs")

        # CENTER (rather than the default EXPAND) still claims the full remaining span
        # between `info` and the right-pinned buttons, but centers the text within it
        # instead of hugging its left edge.
        desc = panel_header.row()
        desc.alignment = "CENTER"
        desc.label(text=f"{action.label} · {result.object_name}")

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
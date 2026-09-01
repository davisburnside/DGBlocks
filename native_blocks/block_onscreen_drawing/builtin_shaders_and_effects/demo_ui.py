
import bpy

from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.generic_tools import force_redraw_ui
from ....addon_helpers.ui.helpers import draw_shared_uilist, ui_draw_subpanel
from ..helpers import _modal_events_block_available, _mouse_capture_available
from ..builtin_shaders_and_effects.demo_props import DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_TEXTBOX, DEMO_ID_STRIPE, DEMO_ID_REGION_BOUNDS, DEMO_ID_ANNOTATED, DEBUG_DRAW_REGION_TYPES, cb_rebuild_shaders, get_demo_row, demo_is_animatable

class DGBLOCKS_OT_Toggle_Demo_Animation(bpy.types.Operator):
    """
    Toggle a demo shader's infinite-loop animation (task 3). Flips the demo row's is_animating
    BoolProperty, whose update callback applies/cancels the animation on the RTC Shader_Instance.
    RTC-only — no Blender shader values are written, so this stays off the undo stack.
    """
    bl_idname = "dgblocks.toggle_demo_animation"
    bl_label = "Toggle Demo Animation"
    bl_options = {"INTERNAL"}

    demo_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_onscreen_drawing_props
        row = get_demo_row(props, self.demo_id)
        if row is None:
            self.report({"WARNING"}, f"Demo '{self.demo_id}' not found")
            return {"CANCELLED"}
        
        # Flipping is_animating fires its update callback (apply/cancel the animation).
        row.is_animating = not row.is_animating
        force_redraw_ui()
        return {"FINISHED"}


class DGBLOCKS_OT_Toggle_Textbox_Mouse_Capture(bpy.types.Operator):
    """
    Start/stop a lightweight, self-owned block_modal_events listener so the textbox demo's
    'At Mouse' spawn point can read a live cursor position. block_onscreen_drawing has no hard
    dependency on block_modal_events (see helpers._hook_get_modal_listener_definitions) — this
    operator is only clickable while that block is actually active (poll()).
    """
    bl_idname = "dgblocks.toggle_textbox_mouse_capture"
    bl_label = "Toggle Textbox Mouse Capture"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return _modal_events_block_available()

    def execute(self, context):
        debug_props = context.scene.dgblocks_onscreen_drawing_props.debug_props
        debug_props.textbox_mouse_capture_active = not debug_props.textbox_mouse_capture_active
        try:
            from ...block_modal_events.feature_modal_manager import Wrapper_Modal_Manager
            Wrapper_Modal_Manager.repoll(Enum_Sync_Events.PROPERTY_UPDATE)
        except ImportError:
            debug_props.textbox_mouse_capture_active = False
            self.report({"WARNING"}, "block_modal_events is not active")
            return {"CANCELLED"}
        force_redraw_ui()
        return {"FINISHED"}


class DGBLOCKS_OT_Textbox_Line_Add(bpy.types.Operator):
    """Add one new line to the Text Boxes demo."""
    bl_idname = "dgblocks.textbox_line_add"
    bl_label = "Add Text Line"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        props = context.scene.dgblocks_onscreen_drawing_props
        row = props.textbox_lines.add()
        row.text = f"Text Box #{len(props.textbox_lines)}"
        props.textbox_lines_selected_idx = len(props.textbox_lines) - 1
        cb_rebuild_shaders(self, context)
        return {"FINISHED"}


class DGBLOCKS_OT_Textbox_Line_Remove(bpy.types.Operator):
    """Remove one line from the Text Boxes demo (the selected row, unless `index` is given)."""
    bl_idname = "dgblocks.textbox_line_remove"
    bl_label = "Remove Text Line"
    bl_options = {"REGISTER", "INTERNAL"}

    index: bpy.props.IntProperty(default=-1)  # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_onscreen_drawing_props
        collection = props.textbox_lines
        idx = self.index if self.index >= 0 else props.textbox_lines_selected_idx
        if 0 <= idx < len(collection):
            collection.remove(idx)
            props.textbox_lines_selected_idx = min(idx, len(collection) - 1)
        cb_rebuild_shaders(self, context)
        return {"FINISHED"}


def _ui_draw_demo_header_eye(header_row, context, demo_id):
    """
    Draw the 'eye' existence toggle on a demo subpanel header (task 5). Bound to the demo's
    show_shader prop; toggling it fires cb_rebuild_shaders -> repoll, so a hidden demo is
    implicitly removed from the shader list.
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    row = get_demo_row(props, demo_id)
    if row is None:
        return
    eye_icon = "HIDE_OFF" if row.show_shader else "HIDE_ON"
    header_row.prop(row, "show_shader", text="", icon=eye_icon, emboss=False)


def _ui_draw_demo_grid(container, data, prop_names, columns=0):
    """Width-sensitive grid of props (task 6). columns=0 = auto-flow to available width."""
    grid = container.grid_flow(row_major=True, columns=columns, even_columns=True, align=True)
    for name in prop_names:
        grid.prop(data, name)
    return grid


def _ui_draw_demo_animation_controls(container, context, demo_id):
    """
    Shared 'Animate' toggle + FPS slider (tasks 3/4). Only shown for animatable demos. While
    animating, the demo's other props are drawn read-only (handled by the caller).
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    row_data = get_demo_row(props, demo_id)
    if row_data is None or not demo_is_animatable(demo_id):
        return
    anim_row = container.row(align=True)
    anim_row.prop(row_data, "animation_fps", slider=True)
    op = anim_row.operator(
        DGBLOCKS_OT_Toggle_Demo_Animation.bl_idname,
        text="Stop Animation" if row_data.is_animating else "Animate",
        icon="PAUSE" if row_data.is_animating else "PLAY",
        depress=row_data.is_animating,
    )
    op.demo_id = demo_id
    # FPS slider sits on the same row as the toggle and stays usable whether or not
    # the animation is currently running (it caps at 60 via the property definition).
    

_shader_billboard_attrs = [
        "billboard_count", "billboard_default_size", "billboard_size_spread",
        "billboard_location_spread", "billboard_color_spread",
    ]
def _ui_draw_billboard_body(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_BILLBOARD)
    animating = bool(row and row.is_animating)

    row = container.row()
    row.alert = debug_props.show_img_2Dbillboard is None
    row.prop(debug_props, "show_img_2Dbillboard")
    sub = container.column()
    # Read-only while animating or  no image is set.
    sub.enabled = (debug_props.show_img_2Dbillboard is not None) and not animating
    _ui_draw_demo_grid(sub, debug_props, _shader_billboard_attrs)
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_BILLBOARD)


def _ui_draw_dashed_body(context, container):
    
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_DASHED)
    animating = bool(row and row.is_animating)
    sub = container.column()
    sub.enabled = not animating
    _ui_draw_demo_grid(sub, debug_props, [
        "linedash_thickness", "linedash_dash_width", "linedash_dash_ratio",
        "linedash_color", "linedash_color2",
    ])
    if row is not None:
        attr_grid = sub.grid_flow(row_major=True, columns=0, even_columns=True, align=True)
        for attr in row.unique_attributes:
            value_field = "int_value" if attr.value_kind == "INT" else "float_value"
            attr_grid.prop(attr, value_field, text=attr.display_name)
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_DASHED)


def _ui_draw_textbox_spawn_point_row(context, container, debug_props):
    """
    One radio button per spawn-point enum item, expanded manually (rather than
    `prop(..., expand=True)`) so the 'At Mouse' entry alone can be disabled when no
    block_modal_event instance is available — Blender's built-in enum expansion has no
    per-item enabled control. A 'Start/Stop Mouse Capture' toggle sits alongside it, clickable
    only while block_modal_events is active (regardless of whether its router is running yet).
    """
    modal_events_available = _modal_events_block_available()

    row = container.row(align=True)
    enum_items = debug_props.bl_rna.properties["textbox_spawn_point"].enum_items
    for item in enum_items:
        sub = row.row(align=True)
        if item.identifier == "MOUSE":
            sub.enabled = modal_events_available
        sub.prop_enum(debug_props, "textbox_spawn_point", item.identifier)

    capture_row = container.row(align=True)
    capture_row.enabled = modal_events_available
    capturing = debug_props.textbox_mouse_capture_active
    capture_row.operator(
        DGBLOCKS_OT_Toggle_Textbox_Mouse_Capture.bl_idname,
        text="Stop Mouse Capture" if capturing else "Start Mouse Capture",
        icon="PAUSE" if capturing else "PLAY",
        depress=capturing,
    )

    if not modal_events_available:
        info = container.column()
        info.enabled = False
        info.label(text="'At Mouse' needs an active block_modal_event", icon="INFO")
        info.label(text="instance for mouse/key capture.")
    elif not _mouse_capture_available():
        info = container.column()
        info.enabled = False
        info.label(text="Mouse capture is off — click 'Start Mouse Capture' above", icon="INFO")


def _ui_draw_textbox_lines_uilist(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    toolbar = container.row(align=True)
    toolbar.operator(DGBLOCKS_OT_Textbox_Line_Add.bl_idname, text="Add Line", icon="ADD")
    remove = toolbar.row(align=True)
    remove.enabled = len(props.textbox_lines) > 0
    remove_op = remove.operator(DGBLOCKS_OT_Textbox_Line_Remove.bl_idname, text="Remove Selected", icon="REMOVE")
    remove_op.index = -1  # -1 = use textbox_lines_selected_idx

    if not props.textbox_lines:
        box = container.box()
        box.label(text="No text lines — click 'Add Line'", icon="INFO")
    else:
        draw_shared_uilist(context, container, "textbox_lines")


def _ui_draw_textbox_body(context, container):

    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props

    container.label(text="Spawn Point:")
    _ui_draw_textbox_spawn_point_row(context, container, debug_props)
    _ui_draw_demo_grid(container, debug_props, [
        "textbox_x_offset", "textbox_y_offset",
    ])

    bg_row = container.row(align=True)
    bg_row.prop(debug_props, "textbox_bg_enabled")
    bg_colors = bg_row.row(align=True)
    bg_colors.enabled = debug_props.textbox_bg_enabled
    bg_colors.prop(debug_props, "textbox_bg_color_top", text="")
    bg_colors.prop(debug_props, "textbox_bg_color_bottom", text="")

    container.separator()
    container.label(text="Lines:")
    _ui_draw_textbox_lines_uilist(context, container)


def _ui_draw_stripe_body(context, container):

    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_STRIPE)
    animating = bool(row and row.is_animating)
    sub = container.column()
    sub.enabled = not animating
    _ui_draw_demo_grid(sub, debug_props, [
        "stripe_angle", "stripe_width", "stripe_color1", "stripe_color2",
    ])
    if row is not None:
        attr_grid = sub.grid_flow(row_major=True, columns=0, even_columns=True, align=True)
        for attr in row.unique_attributes:
            value_field = "int_value" if attr.value_kind == "INT" else "float_value"
            attr_grid.prop(attr, value_field, text=attr.display_name)
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_STRIPE)


def _ui_draw_annotated_body(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_ANNOTATED)
    animating = bool(row and row.is_animating)
    sub = container.column()
    sub.enabled = not animating
    _ui_draw_demo_grid(sub, debug_props, [
        "annotated_line_thickness",
        "annotated_arrow_length_px",
        "annotated_arrow_angle",
        "annotated_z_boost",
    ])
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_ANNOTATED)


def _ui_draw_region_boundary_body(context, container):
    
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    region_box = container.column()
    region_box.label(text="Region Types:")
    grid = region_box.grid_flow(row_major=True, columns=0, even_columns=True, align=True)
    for rt in DEBUG_DRAW_REGION_TYPES:
        grid.prop(props.debug_props.region_boundary_toggles, f"region_{rt}")



# Maps each demo to (label, body-draw fn) so the panel iterates generically.
_DEMO_SUBPANELS = [
    (DEMO_ID_BILLBOARD, "2D Image Billboard", _ui_draw_billboard_body),
    (DEMO_ID_DASHED,    "Dashed Polyline",    _ui_draw_dashed_body),
    (DEMO_ID_TEXTBOX,   "Text Boxes",         _ui_draw_textbox_body),
    (DEMO_ID_STRIPE,    "Stripe Holdout",     _ui_draw_stripe_body),
    (DEMO_ID_ANNOTATED,   "Annotated Lines",     _ui_draw_annotated_body),
    (DEMO_ID_REGION_BOUNDS, "All Region Boundaries", _ui_draw_region_boundary_body),
]


def _ui_draw_shader_examples_subpanel(context, container):
    """
    Contents of the 'Shader Examples' subpanel: one nested sub-subpanel per demo shader (task 5),
    each with an eye existence toggle on its header, plus the viewport-debug sub-subpanel.
    Only enabled while drawing is on.
    """
    drawing_props = context.scene.dgblocks_onscreen_drawing_props

    col = container.column()
    col.enabled = drawing_props.enable_drawing

    col.prop(drawing_props.debug_props, "builtin_animation_easing")

    row = col.row()
    row.alignment = "CENTER"
    row.label(text = "Demonstrations of UI Shaders and Animations")

    for demo_id, label, body_fn in _DEMO_SUBPANELS:
        header, body = ui_draw_subpanel(
            context, col, f"onscreen_demo_{demo_id}", "", body_fn,
        )
        # Header: eye toggle + label.
        _ui_draw_demo_header_eye(header, context, demo_id)
        header.label(text=label)

    # (The "All Region Boundaries" sub-subpanel is now one of the demo rows above so it is
    # grouped with the other four shaders — it has no animatable properties.)


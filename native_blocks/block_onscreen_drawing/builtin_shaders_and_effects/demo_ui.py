
import bpy

from ....addon_helpers.generic_tools import force_redraw_ui
from ....addon_helpers.ui.helpers import ui_draw_subpanel
from ..helpers import _mouse_capture_available
from ..builtin_shaders_and_effects.demo_props import DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_TEXTBOX, DEMO_ID_STRIPE, DEBUG_DRAW_REGION_TYPES, get_demo_row, demo_is_animatable

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


def _ui_draw_textbox_body(context, container):
    
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    container.prop(debug_props, "show_textbox_count")
    container.label(text="Spawn Point:")
    container.prop(debug_props, "textbox_spawn_point", expand=True)
    _ui_draw_demo_grid(container, debug_props, [
        "textbox_x_offset", "textbox_y_offset",
    ])
    if not _mouse_capture_available():
        info = container.column()
        info.enabled = False
        info.label(text="'At Mouse' needs an active block_modal_event", icon="INFO")
        info.label(text="instance for mouse/key capture.")


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


def _ui_draw_region_boundary_body(context, container):
    
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    container.prop(debug_props, "show_region_boundaries", toggle=True)
    region_box = container.column()
    region_box.enabled = debug_props.show_region_boundaries
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
]


def _ui_draw_shader_examples_subpanel(context, container):
    """
    Contents of the 'Shader Examples' subpanel: one nested sub-subpanel per demo shader (task 5),
    each with an eye existence toggle on its header, plus the viewport-debug sub-subpanel.
    Only enabled while drawing is on.
    """
    drawing_props = context.scene.dgblocks_onscreen_drawing_props

    col = container.column()
    # col.enabled = drawing_props.enable_drawing
    
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

    # Viewport region debugging as its own sub-subpanel.
    ui_draw_subpanel(
        context, col, "onscreen_viewport_debug", "All Region Boundaries",
        _ui_draw_region_boundary_body,
    )


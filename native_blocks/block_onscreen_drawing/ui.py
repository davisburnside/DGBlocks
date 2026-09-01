
import bpy
from ...addon_helpers.data_structures import Enum_Sync_Events
from ...addon_helpers.generic_tools import force_redraw_ui
from ...addon_helpers.ui.helpers import format_timestamp_for_ui, ui_draw_generic_instance_data, ui_draw_static_list, ui_draw_subpanel
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager

# ==============================================================================================================================
# SHADER PANEL UI HELPERS

def _uilist_draw_uilist_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = RTC_item.shader_uid)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    drawhandler_info = f"{RTC_item.shader_type} / {RTC_item.draw_phase}"
    sub.label(text = drawhandler_info)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    animation_count = len(RTC_item._animations)
    sub.label(text = str(animation_count) if animation_count else "-")

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.label(text = str(RTC_item.batch_count_of_shader))

    sub = header.row()
    sub.ui_units_x = col_widths[4]
    sub.label(text = str(RTC_item.draw_count_of_batch))

    # is_enabled lives on the RTC instance, not BL. Draw an operator (no undo-stack entry)
    # that toggles it by uid. The eye icon reflects the live RTC state.
    sub = header.row()
    sub.ui_units_x = col_widths[5]
    eye_icon = "HIDE_OFF" if RTC_item.is_enabled else "HIDE_ON"
    op = sub.operator("dgblocks.toggle_shader", text = "", icon = eye_icon, emboss = False)
    op.shader_uid = RTC_item.shader_uid

def _ui_show_count(list_property):
    return len(list_property)

ui_structure_for_shader_instance = {
    "Creation Times": [
        ("Shader Creation Time", "shader_creation_timestamp", format_timestamp_for_ui),
        ("Batch Creation Time", "last_batch_creation_timestamp", format_timestamp_for_ui),
        ("Last Draw Time", "last_draw_timestamp", format_timestamp_for_ui)
    ],
    "Draw Statistics":[
        ("Draw Count, of Current Batch", "draw_count_of_batch"),
        ("Batch Count, of Current Shader", "batch_count_of_shader"),
        ("Batch Creation Duration", "last_batch_creation_duration")
    ],

}
ui_structure_for_custom_shader_instance = {
    "Shader info":[
        ("type", "builtin_shader_name"),
        ("Points Count", "_points", _ui_show_count),
        ("Tris Count", "_indices", _ui_show_count),
    ]
}

# ==============================================================================================================================
# ANIMATION SUBPANEL UI HELPERS

_ANIM_COL_WIDTHS = [4, 3, 2, 3, 2]


class DGBLOCKS_OT_Control_Animation(bpy.types.Operator):
    """
    Pause/resume or kill a single animation owned by a shader, from the Shader Details
    section of the Shader UIList. RTC-only (no undo-stack entry).
    """
    bl_idname = "dgblocks.control_shader_animation"
    bl_label = "Control Shader Animation"
    bl_options = {"INTERNAL"}

    shader_uid: bpy.props.StringProperty()  # type: ignore
    animation_uid: bpy.props.StringProperty()  # type: ignore
    action: bpy.props.EnumProperty(items=[  # type: ignore
        ("PAUSE", "Pause / Resume", ""),
        ("KILL", "Kill", ""),
    ])

    def execute(self, context):
        
        # Lazy imports: ui.py is imported early (from common_declarations) so Block_RTC_Members /
        # Wrapper_Timer_Manager must not be pulled in at module level (circular import guard).
        

        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list("SHADERS", "shader_uid", self.shader_uid)
        if shader is None:
            self.report({"WARNING"}, f"Shader '{self.shader_uid}' not found")
            return {"CANCELLED"}

        anim = shader.get_animation(self.animation_uid)
        if anim is None:
            self.report({"WARNING"}, f"Animation '{self.animation_uid}' not found")
            return {"CANCELLED"}

        if self.action == "PAUSE":
            shader.pause_animation(self.animation_uid)   # toggles is_paused
        elif self.action == "KILL":
            shader.cancel_animation(self.animation_uid, revert=False)

        # A kill may leave a timer with nothing left to drive — let block_timers reconcile.
        Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)
        force_redraw_ui(only_3Dviewport=False)
        return {"FINISHED"}


def _ui_draw_animations_box(context, container, RTC_item):
    """
    Compact per-shader animation summary: uid, what it drives (data_name), completion %,
    loop behaviour, and state — plus a pause/resume and a kill operator per animation.
    Drawn only when the shader actually owns animations.
    """
    animations = RTC_item._animations
    if not animations:
        return

    box = container.box()
    box.label(text=f"Animations ({len(animations)})")

    # Header row
    header = box.row()
    sub = header.row(); sub.ui_units_x = 4; sub.label(text="UID")
    sub = header.row(); sub.ui_units_x = 3; sub.label(text="Data")
    sub = header.row(); sub.ui_units_x = 2; sub.label(text="%")
    sub = header.row(); sub.ui_units_x = 3; sub.label(text="Loop")
    sub = header.row(); sub.ui_units_x = 3; sub.label(text="State")

    for anim in animations.values():
        if anim.is_paused:
            state = "Paused"
            pause_icon = "PLAY"              # press to resume
        elif anim._delay_remaining > 0.0:
            state = f"Delay {anim._delay_remaining:.1f}s"
            pause_icon = "PAUSE"
        elif not anim.is_enabled:
            state = "Disabled"
            pause_icon = "PAUSE"
        else:
            state = "Playing"
            pause_icon = "PAUSE"

        if anim.is_looping:
            loop_total = "inf" if anim.loop_count == 0 else str(anim.loop_count)
            loop_str = f"{anim.loop_mode} {anim.loops_completed}/{loop_total}"
        else:
            loop_str = anim.loop_mode

        row = box.row()
        sub = row.row(); sub.ui_units_x = 4
        sub.label(text=anim.animation_uid)
        sub = row.row(); sub.ui_units_x = 3
        sub.label(text=anim.data_name)
        sub = row.row(); sub.ui_units_x = 2
        sub.label(text=f"{anim.completion_factor * 100:.0f}%")
        sub = row.row(); sub.ui_units_x = 3
        sub.label(text=loop_str)
        sub = row.row(); sub.ui_units_x = 3
        sub.label(text=state)

        # Pause / resume + kill operators.
        ctrl = row.row(); ctrl.alignment = "RIGHT"
        ctrl.scale_x = 0.6
        pause_op = ctrl.operator(
            DGBLOCKS_OT_Control_Animation.bl_idname, text="", icon=pause_icon, emboss=False,
        )
        pause_op.shader_uid = RTC_item.shader_uid
        pause_op.animation_uid = anim.animation_uid
        pause_op.action = "PAUSE"
        kill_op = ctrl.operator(
            DGBLOCKS_OT_Control_Animation.bl_idname, text="", icon="CANCEL", emboss=False,
        )
        kill_op.shader_uid = RTC_item.shader_uid
        kill_op.animation_uid = anim.animation_uid
        kill_op.action = "KILL"


def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    if RTC_item is None:
        return

    def _body(context, cont):
        ui_draw_generic_instance_data(context, cont, RTC_item, ui_structure_for_shader_instance)
        ui_draw_generic_instance_data(context, cont, RTC_item, ui_structure_for_custom_shader_instance)
        _ui_draw_animations_box(context, cont, RTC_item)

    # The whole details section is a collapsible sub-subpanel (defaults closed). The idname is
    # intentionally shared across all shaders (not suffixed with shader_uid) so Blender's
    # panel open/closed state persists when the selected row changes.
    ui_draw_subpanel(
        context, container, "onscreen_shader_details",
        "Shader Details", _body,
    )

# ==============================================================================================================================
# TEXT BOXES DEMO — LINES UILIST HELPERS
# ==============================================================================================================================
# Pure-BL list (RTC_key=None): each row is one user-authored Textbox_Demo_Shader line, with no
# associated runtime instance of its own. Lives here (rather than demo_ui.py) so
# common_declarations.py can import these callbacks without a circular import — demo_ui.py
# already imports FROM common_declarations.

def _uilist_draw_textbox_line_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = BL_item.text if BL_item.text.strip() else "(empty)")

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = BL_item.alignment)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.label(text = str(BL_item.font_size))


_PADDING_MODE_FIELDS = {
    "SIMPLE": [("padding_simple", "All Sides")],
    "XY":     [("padding_horizontal", "Horizontal"), ("padding_vertical", "Vertical")],
    "ALL":    [("padding_top", "Top"), ("padding_right", "Right"),
               ("padding_bottom", "Bottom"), ("padding_left", "Left")],
}


def _ui_draw_textbox_line_padding_values(container, BL_item):
    """
    Vertical stack of sliders for whichever padding_mode is active, one row per value —
    label on the LEFT, slider on the RIGHT (matches every other prop() row in this panel).
    """
    stack = container.column(align=True)
    for prop_name, label in _PADDING_MODE_FIELDS[BL_item.padding_mode]:
        row = stack.row(align=True)
        row.label(text=label)
        row.prop(BL_item, prop_name, text="", slider=True)


def _uilist_draw_textbox_line_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    """
    Always-visible (no collapsible subpanel — the selected row's settings should never be
    hidden behind a click) detail section for the selected textbox_lines row.
    """
    if BL_item is None:
        return

    box = container.box()
    box.label(text="Text Line Details")

    box.prop(BL_item, "text")

    size_row = box.row(align=True)
    size_row.prop(BL_item, "font_size")
    size_row.prop(BL_item, "max_char_count")

    align_color_row = box.row(align=True)
    align_color_row.prop(BL_item, "alignment")
    align_color_row.label(text="Color:")
    align_color_row.prop(BL_item, "text_color", text="")

    box.prop(BL_item, "padding_mode")
    _ui_draw_textbox_line_padding_values(box, BL_item)

    outline_row = box.row(align=True)
    outline_row.prop(BL_item, "outline_enabled", text="Outline")
    outline_color = outline_row.row(align=True)
    outline_color.enabled = BL_item.outline_enabled
    outline_color.prop(BL_item, "outline_color", text="")

    outline_extra = box.row(align=True)
    outline_extra.enabled = BL_item.outline_enabled
    outline_extra.prop(BL_item, "outline_spread", text="")
    outline_extra.prop(BL_item, "outline_offset_x")
    outline_extra.prop(BL_item, "outline_offset_y")

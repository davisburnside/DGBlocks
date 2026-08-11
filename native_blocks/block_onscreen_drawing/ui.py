
from ...addon_helpers.ui.helpers import format_timestamp_for_ui, ui_draw_generic_instance_data, ui_draw_static_list, ui_draw_subpanel


def _uilist_draw_uilist_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()
    # header.separator(factor=0.5)  # Account for UIList left padding

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = RTC_item.shader_uid)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    drawhandler_info = f"{RTC_item.draw_phase}/{RTC_item.draw_region}/{RTC_item.draw_space}"
    sub.label(text = drawhandler_info)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    animation_count = len(RTC_item._animations)
    sub.label(text = str(animation_count) if animation_count else "-")

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "is_enabled", text = "")

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

_ANIM_COL_WIDTHS = [4, 3, 2, 3, 2]


def _ui_draw_animations_box(context, container, RTC_item):
    """
    Compact per-shader animation summary. Deliberately terser than a full
    subpanel — uid, what it drives, progress, loop behaviour, and state.
    Drawn only when the shader actually owns animations.
    """
    animations = RTC_item._animations
    if not animations:
        return

    box = container.box()
    box.label(text=f"Animations ({len(animations)})")

    data_rows = [["UID", "Data", "Progress", "Loop", "State"]]
    for anim in animations.values():
        if anim.is_paused:
            state = "Paused"
        elif anim._delay_remaining > 0.0:
            state = f"Delay {anim._delay_remaining:.1f}s"
        elif not anim.is_enabled:
            state = "Disabled"
        else:
            state = "Playing"

        if anim.is_looping:
            loop_total = "inf" if anim.loop_count == 0 else str(anim.loop_count)
            loop_str = f"{anim.loop_mode} {anim.loops_completed}/{loop_total}"
        else:
            loop_str = anim.loop_mode

        data_rows.append([
            anim.animation_uid,
            anim.data_name,
            f"{anim.completion_factor * 100:.0f}%",
            loop_str,
            state,
        ])

    ui_draw_static_list(box, data_rows, _ANIM_COL_WIDTHS)


def _uilist_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    box = container.box()
    ui_draw_generic_instance_data(context, box, RTC_item, ui_structure_for_shader_instance)
    ui_draw_generic_instance_data(context, box, RTC_item, ui_structure_for_custom_shader_instance)
    _ui_draw_animations_box(context, container, RTC_item)

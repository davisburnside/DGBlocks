
# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...addon_helpers.ui_drawing_helpers import create_ui_box_with_header
from .feature_timer_wrapper import Timer_Wrapper

# =============================================================================
# UI DRAWING
# =============================================================================

def uilayout_draw_timer_list_item(layout_type, context, layout, data, item, icon, active_data, active_propname, index):
    """Draw a single row in the timer UIList."""
    timer_item = item

    if layout_type in {'DEFAULT', 'COMPACT'}:
        row = layout.row(align=True)

        # Enable/disable toggle
        row.prop(timer_item, "is_enabled", text="", icon='CHECKBOX_HLT' if timer_item.is_enabled else 'CHECKBOX_DEHLT')

        # Timer name
        row.prop(timer_item, "timer_name", text="", emboss=False)

        # Frequency
        row.prop(timer_item, "frequency_ms", text="", emboss=False)

        # Subscriber hook count from Instance_Data
        instance = Timer_Wrapper.get_instance(timer_item.timer_name)
        hook_count = len(instance.subscriber_hook_func_names) if instance else 0
        row.label(text=f"Hooks: {hook_count}")

    elif layout_type == 'GRID':
        layout.alignment = 'CENTER'
        layout.label(text=timer_item.timer_name)


def uilayout_draw_timer_panel(context, container):
    """Draw the full timer management panel."""
    timer_props = context.scene.dgblocks_timer_props

    # Timer list
    box = create_ui_box_with_header(context, container, "Timer Definitions")

    row = box.row()
    row.template_list(
        "DGBLOCKS_UL_Timer_List",
        "",
        timer_props,
        "timers",
        timer_props,
        "uilist_selection_index_active_timer",
        rows=4
    )

    # Add/Remove buttons
    col = row.column(align=True)
    col.operator("dgblocks.timer_add", text="", icon='ADD')
    col.operator("dgblocks.timer_remove", text="", icon='REMOVE')

    # Show details of active timer
    if len(timer_props.timers) > 0 and timer_props.uilist_selection_index_active_timer < len(timer_props.timers):
        active_timer = timer_props.timers[timer_props.uilist_selection_index_active_timer]

        details_box = create_ui_box_with_header(context, container, "Timer Details")
        details_box.prop(active_timer, "timer_name")
        details_box.prop(active_timer, "frequency_ms")
        details_box.prop(active_timer, "is_enabled")

        # Show runtime info from Instance_Data
        instance = Timer_Wrapper.get_instance(active_timer.timer_name)
        if instance:
            info_box = create_ui_box_with_header(context, container, "Runtime Info")
            info_box.label(text=f"Last Fire: {instance.timestamp_ms_last_fire} ms")
            info_box.label(text=f"Fire Success: {instance.count_fire_success}")
            info_box.label(text=f"Fire Failures: {instance.count_fire_failure}")
            info_box.label(text=f"Subscriber Hooks: {len(instance.subscriber_hook_func_names)}")

# =============================================================================
# OPERATOR EXECUTION LOGIC
# =============================================================================

def op_timer_add(context):
    timer_props = context.scene.dgblocks_timer_props
    new_timer = timer_props.timers.add()
    new_timer.timer_name = f"Timer_{len(timer_props.timers)}"
    new_timer.frequency_ms = 1000
    new_timer.is_enabled = True

    timer_props.uilist_selection_index_active_timer = len(timer_props.timers) - 1

    # Sync to RTC — create_instance will be called inside sync_scene_to_rtc
    Timer_Wrapper.sync_scene_to_rtc(context.scene)

    return {'FINISHED'}


def op_timer_remove(context):
    timer_props = context.scene.dgblocks_timer_props

    if timer_props.uilist_selection_index_active_timer < len(timer_props.timers):
        timer_props.timers.remove(timer_props.uilist_selection_index_active_timer)

        # Adjust active index if needed
        if timer_props.uilist_selection_index_active_timer >= len(timer_props.timers):
            timer_props.uilist_selection_index_active_timer = max(0, len(timer_props.timers) - 1)

        # Sync to RTC — destroy_instance will be called inside sync_scene_to_rtc
        Timer_Wrapper.sync_scene_to_rtc(context.scene)

    return {'FINISHED'}

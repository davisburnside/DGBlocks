
# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .._block_core.core_helpers.helper_uilayouts import ui_box_with_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
# from .feature_modal_wrapper import Modal_Wrapper

# =============================================================================
# UI DRAWING
# =============================================================================

def uilayout_draw_modal_panel(context, container):
    """Draw the modal management panel."""
    modal_props = context.scene.dgblocks_modal_props

    # Modal enable/disable
    box = ui_box_with_header(context, container, "Modal Control")
    box.prop(modal_props, "is_enabled", text="Enable Stable Modal?")

    # Show runtime info from Instance_Data
    instance = Modal_Wrapper.get_instance()
    if instance:
        # info_box = ui_box_with_header(context, container, "Runtime Info")
        info_box = box
        
        # Status indicator
        status_icon = "CHECKMARK" if instance.is_running else "X"
        status_text = "Running" if instance.is_running else "Stopped"
        row = info_box.row()
        row.label(text=f"Status: {status_text}", icon=status_icon)
        
        # Stats
        info_box.label(text=f"Restart Count: {instance.count_restarts}")
        
        if instance.timestamp_ms_last_event > 0:
            info_box.label(text=f"Last Event: {instance.timestamp_ms_last_event} ms")

# =============================================================================
# OPERATOR EXECUTION LOGIC
# =============================================================================

def op_modal_toggle(context):
    """Toggle the modal on/off."""
    modal_props = context.scene.dgblocks_modal_props
    modal_props.is_enabled = not modal_props.is_enabled
    
    # Sync will happen automatically via property update callback
    return {'FINISHED'}


def op_modal_restart(context):
    """Force restart the modal."""
    instance = Modal_Wrapper.get_instance()
    if instance:
        Modal_Wrapper.stop_modal(context)
        instance.count_restarts += 1
        Modal_Wrapper.start_modal(context)
    
    return {'FINISHED'}

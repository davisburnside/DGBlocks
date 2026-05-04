
import bpy # type: ignore

# Your callback logic for bpy.context.mode switch events
def my_mode_switch_event_callback(context):
    
    mode = bpy.context.mode
    print(f"EVENT: Context Mode changed to {mode}")
    

# Your callback logic for bpy.context.mode switch events
def my_depsgraph_update_post_callback(context):
    
    print(f"deps")

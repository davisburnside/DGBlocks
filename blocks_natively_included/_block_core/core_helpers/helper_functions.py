
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .... import my_addon_config

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import  Core_Block_Loggers
from .helper_uilayouts import ui_box_with_header
from ..core_features.feature_logs import get_logger, _uilayout_draw_logger_settings
from ..core_features.feature_block_manager import _uilayout_draw_block_manager_settings
from ..core_features.feature_hooks  import _uilayout_draw_hooks_settings

#=================================================================================
# REGISTRATION HELPERS 
# These should only be called during registration, unregistration, and post-init callbacks
#=================================================================================

def register_hotkeys():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    
    # Add keymap entry
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        
        km = kc.keymaps.new(name='Window', space_type='EMPTY')
        
        # kmi1 = km.keymap_items.new(op_name, type='T', value='PRESS', ctrl=True, shift=True)
        # kmi1.active = True  
        
        for hotkey_data in my_addon_config.addon_hotkeys:
            name = hotkey_data["OP_NAME"]
            kmi2 = km.keymap_items.new(
                    name, 
                    type=hotkey_data["TYPE"], 
                    value='PRESS', # Keypress event
                    ctrl =hotkey_data["CTRL"],
                    alt = hotkey_data["ALT"],
                    shift = hotkey_data["SHIFT"],
                    head=True)
            kmi2.active = True    
            logger.info(f"Added hotkey {name}")
        
def unregister_hotkeys():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps['Window']
        for kmi in km.keymap_items:
            if kmi.idname in [k["OP_NAME"] for k in my_addon_config.addon_hotkeys]:
                logger.info(f"removing hotkey {kmi.idname}")
                km.keymap_items.remove(kmi)

#=================================================================================
# DATA MANAGEMENT
#=================================================================================

def uilayout_draw_core_block_settings(context:bpy.context, container:bpy.types.UILayout):
    
    core_scene_props = context.scene.dgblocks_core_props
    
    # General settings
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_general", default_closed=True)
    panel_header.label(text = "General")
    if panel_body is not None: 
        grid = panel_body.grid_flow(columns=2)
        grid.prop(core_scene_props, "addon_is_active")
        grid.prop(core_scene_props, "debug_mode_enabled")
        grid.prop(core_scene_props, "documentation_weblinks_enabled")
        op_rtc_clear = grid.operator("dgblocks.debug_force_reload_scipts", text = "Clear RTC")
        op_rtc_clear.target = "RTC"
        op_rtc_clear.action = "CLEAR"
        op_rtc_restore = grid.operator("dgblocks.debug_force_reload_scipts", text = "Restore RTC")
        op_rtc_restore.target = "RTC"
        op_rtc_restore.action = "RESTORE"
        
    
    # Draw management subpanels for blocks, hooks, & loggers
    _uilayout_draw_block_manager_settings(context, container)
    _uilayout_draw_hooks_settings(context, container)
    _uilayout_draw_logger_settings(context, container)

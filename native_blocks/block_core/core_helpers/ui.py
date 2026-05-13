
import textwrap
import math
from datetime import datetime
import textwrap
import bpy # type: ignore
import blf # type: ignore

from ..core_features.hooks.ui import _uilayout_draw_hooks_settings
from ..core_features.control_plane.ui import _uilayout_draw_block_manager_settings
from ..core_features.loggers.ui import _uilayout_draw_logger_settings

def uilayout_template_columns_for_propertygroup(
        context:bpy.context, 
        container:bpy.types.UILayout, 
        property_owners:list[bpy.types.PropertyGroup], 
        property_names:list[str],
        property_titles:list[str]):
    
    if len(property_owners) != len(property_names) or len(property_names) != len(property_titles): # one prop_name per prop_owner
        raise Exception(f"List lengths must match: property_owners={len(property_owners)} property_names={len(property_names)} property_titles={len(property_titles)}")
    
    col = container.column(align=True)
    for idx, prop_owner in enumerate(property_owners):
        
        prop_name = property_names[idx]
        
        # 1. Create a split. factor=0.4 means the left side takes 40% width.
        # align=True connects the boxes, creating that vertical 'seam' line.
        split = col.split(factor=0.6, align=True)
        
        # 2. Left side: The Label
        # Use a nested row with alignment='RIGHT' to keep text against the line.
        left_side = split.row(align=True)
        left_side.alignment = 'RIGHT'
        left_side.label(text=property_titles[idx])
        
        # 3. Right side: The Property
        split.prop(prop_owner, prop_name, text="")

# ==============================================================================================================================
# INTERNAL API - Only used inside this block
# ==============================================================================================================================

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
        grid.prop(core_scene_props, "debug_log_all_RTC_BL_sync_actions")
        grid.prop(core_scene_props, "documentation_weblinks_enabled")
        op_rtc_clear = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Clear RTC")
        op_rtc_clear.target = "RTC"
        op_rtc_clear.action = "CLEAR"
        op_rtc_restore = grid.operator("dgblocks.debug_clear_and_restore_caches", text = "Restore RTC")
        op_rtc_restore.target = "RTC"
        op_rtc_restore.action = "RESTORE"
        
    
    # Draw management subpanels for blocks, hooks, & loggers
    _uilayout_draw_block_manager_settings(context, container)
    _uilayout_draw_hooks_settings(context, container)
    _uilayout_draw_logger_settings(context, container)


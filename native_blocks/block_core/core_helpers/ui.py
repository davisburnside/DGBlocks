
import bpy

from ....addon_config.static_settings import Documentation_URLs, addon_title
from ....addon_helpers.ui import ui_draw_block_panel_header, get_shared_uilist_config

class DGBLOCKS_UL_Shared_Debug_List(bpy.types.UIList):
    """Generic UIList for debug panels"""
    
    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):
        config = get_shared_uilist_config(self.list_id)
        if not config:
            container.label(text=f"Missing config for {self.list_id}")
            return
            
        row = container.row(align=True)
        col_widths = config["col_widths"]
        columns_def = config["columns_def"]
        
        for i, col_def in enumerate(columns_def):
            sub = row.row()
            if i < len(col_widths):
                sub.ui_units_x = col_widths[i]
                
            col_type = col_def.get("type", "LABEL")
            field = col_def.get("field", "")
            
            if col_type == "LABEL":
                text = getattr(item, field, "")
                if isinstance(text, bool):
                    text = str(text)
                sub.label(text=text)
                
            elif col_type == "PROP":
                icon_only = col_def.get("icon_only", False)
                if icon_only:
                    val = getattr(item, field, False)
                    icon_str = col_def.get("icon_true", "CHECKBOX_HLT") if val else col_def.get("icon_false", "CHECKBOX_DEHLT")
                    sub.prop(item, field, text="", icon=icon_str)
                else:
                    sub.prop(item, field, text="")
                    
            elif col_type == "ICON":
                val = getattr(item, field, False)
                icon_str = col_def.get("icon_true", "CHECKMARK") if val else col_def.get("icon_false", "X")
                sub.label(text="", icon=icon_str)

from ..core_helpers.debugging import Debugging_Print_Options
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


class DGBLOCKS_PT_Core_Block_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"DGBLOCKS_PT_Core_Block_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, "Block-Core", Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "FILE_3D")

    def draw(self, context):
        
        layout = self.layout
        core_scene_props = context.scene.dgblocks_core_props
    
        # General settings
        box = layout.box()
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
        _uilayout_draw_block_manager_settings(context, layout)
        _uilayout_draw_hooks_settings(context, layout)
        _uilayout_draw_logger_settings(context, layout)

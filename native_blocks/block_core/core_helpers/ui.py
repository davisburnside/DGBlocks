
import bpy

from ....addon_config.static_settings import Documentation_URLs, addon_title
from ....addon_helpers.ui import draw_shared_uilist, ui_draw_block_panel_header
from ....addon_helpers.generic_tools import get_Wrapper_Runtime_Cache

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



def _uilist_hooks_draw_selection_details(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    
    func_name = BL_item.hook_func_name
    cached_hook_subs = get_Wrapper_Runtime_Cache().get_cache("REGISTRY_ALL_HOOK_SUBSCRIBERS")

    if func_name not in cached_hook_subs:
        container.label(text="No subscriptions found.")
        return

    subs = cached_hook_subs[func_name]
    box = container.box()
    box.label(text=f"Subscriptions ({len(subs)}):")
    for sub in subs:
        box.label(text=f"• {sub.subscriber_block_id}", icon='PLUGIN')


def _uilist_hooks_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):
    
    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = BL_item.hook_func_name)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = BL_item.src_block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.label(text = str(RTC_item.subscriber_count))

    sub = header.row()
    sub.ui_units_x = col_widths[3]
    sub.prop(BL_item, "is_hook_enabled", text = "")





def _uilist_loggers_draw_row(context, container, uillist_config_instance, BL_item, RTC_item, list_idx):

    col_widths = uillist_config_instance.col_widths
    header = container.row()

    sub = header.row()
    sub.ui_units_x = col_widths[0]
    sub.label(text = BL_item.logger_name)

    sub = header.row()
    sub.ui_units_x = col_widths[1]
    sub.label(text = BL_item.src_block_id)

    sub = header.row()
    sub.ui_units_x = col_widths[2]
    sub.prop(BL_item, "level_name", text = "")




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
        core_feature_drawing = [
            ("Loggers", core_scene_props.managed_loggers, "managed_loggers"),
            ("Hooks", core_scene_props.managed_hooks, "managed_hooks")
        ]
        for label_str, BL_colprop, colprop_name in core_feature_drawing:
            box = layout.box()
            panel_header, panel_body = box.panel(idname = f"_dummy_dgblocks_core_scene_{label_str}", default_closed=True)
            panel_header.label(text=f"All {label_str} ({len(BL_colprop)})")
            if panel_body is not None:
                draw_shared_uilist(context, panel_body, colprop_name)
                
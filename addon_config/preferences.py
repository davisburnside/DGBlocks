import os
import bpy
from .static_settings import addon_name

class DGBLOCKS_UP_Core_Preferences(bpy.types.AddonPreferences):
    bl_idname = addon_name 

    addon_saved_data_folder: bpy.props.StringProperty(
            default = os.path.expanduser(f"~/.blender_dgblocks_data/"),
            description="Root folder for addon-managed data and Python libraries",
            subtype='DIR_PATH') # type: ignore  
    
    def draw(self, context):
        
        layout = self.layout
        box = layout.box()
        box.label(text = "Data Home for Addon")
        box.prop(self, "addon_saved_data_folder", text="")

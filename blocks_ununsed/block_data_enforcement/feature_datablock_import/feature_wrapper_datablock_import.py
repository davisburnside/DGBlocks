import sys
import os
import site
import importlib
import subprocess
import threading
import queue
import time
from enum import Enum
import bpy
from ...addon_config import Documentation_URLs
from ...blocks_natively_included._block_core.core_helper_uilayouts import uilayout_draw_block_panel_header
from ...blocks_natively_included._block_core.core_feature_logs import get_logger
from ...blocks_natively_included._block_core.core_helper_functions import register_block_components, unregister_block_components
from ...addon_config import addon_name

#================================================================
# UI - Panel for Viewing installation status
#================================================================

class DGBLOCKS_PT_BLEND_DATA_INSTALLER_WRAPPER(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_BLEND_DATA_INSTALLER_WRAPPER"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_name
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        uilayout_draw_block_panel_header(context, self.layout, "Data Dependencies", Documentation_URLs.MY_PLACEHOLDER_URL_1)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="placeholder")

#================================================================
# Register & Unregister : Only called from the main __init__.py
#================================================================

_package_classes = [
    DGBLOCKS_PT_BLEND_DATA_INSTALLER_WRAPPER]

def register_blend_data_installer_wrapper():

    register_block_components(_package_classes)
    
def unregister_blend_data_installer_wrapper():

    unregister_block_components(_package_classes)
        

import os
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import get_self_block_module, clear_console
from ...my_addon_config import Documentation_URLs, addon_title, addon_name, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...native_blocks import block_core
from ...native_blocks.block_core.core_features.loggers import Core_Block_Loggers, get_logger
from ...native_blocks.block_core.core_features.hooks import Wrapper_Hooks
from ...native_blocks.block_core.core_features.control_plane import Wrapper_Block_Management
from ...native_blocks.block_core.core_features.runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .helper_unittests import run_operator_in_headless_blender, _sample_unittest, launch_headless_operator

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-unit-tests" 
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [block_core.core_block_id] 

class DGBLOCKS_OT_Run_Tests(bpy.types.Operator):
    bl_idname = "dgblocks.run_tests"
    bl_label = "Print Block Diagnostics Data to Console"
    bl_options = {"REGISTER"}

    is_subprocess: bpy.props.BoolProperty() # type: ignore 
    test_id: bpy.props.StringProperty() # type: ignore 
    
    # This operator can always be executed, even when add
    def execute(self, context):
    
        print("is subprocess? ", self.is_subprocess)
        if self.is_subprocess:
            result = _sample_unittest()

        else:

            blend_path = r"C:\Users\davis\Documents\test.blend"
            result = launch_headless_operator(
                addon_module_name = addon_name, 
                test_id = "func_t1",
                blend_file = blend_path,
            )

            print("\n\n----", result)
                    
        return {"FINISHED"}

# ==============================================================================================================================
# UI - Preferences Menu, General Settings, Logging & Debugging
# ==============================================================================================================================

class DGBLOCKS_PT_Unit_Test_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Unit_Test_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0
    
    # @classmethod
    # def poll(cls, context):
    #     return Wrapper_Block_Management.is_block_enabled(_BLOCK_ID)

    def draw_header(self, context):

        ui_draw_block_panel_header(context, self.layout, "Unit Tests", Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name = "TOOL_SETTINGS")

    def draw(self, context):
        
        layout = self.layout
        layout.operator("dgblocks.run_tests", text = "run 'em")

# ==============================================================================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
# ==============================================================================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
    DGBLOCKS_OT_Run_Tests,
    DGBLOCKS_PT_Unit_Test_Panel,
]

def register_block():

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
    )
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")

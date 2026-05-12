import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.generic_helpers import get_self_block_module
from ....my_addon_config import Documentation_URLs, addon_title, addon_bl_type_prefix
from ....addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...block_core.core_features.control_plane import Wrapper_Block_Management, RTC_Block_Instance
from ...block_core.core_features.loggers import Core_Block_Loggers, get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Hook_Sources, Block_Loggers, Block_RTC_Members

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-example-simple-2"
_BLOCK_VERSION = (1, 0, 0)
_BLOCK_DEPENDENCIES = ["block-core", "block-debug-console-print"]

# ==============================================================================================================================
# HOOK SUBSCRIPTIONS
# ==============================================================================================================================

def hook_core_event_undo():
    logger = get_logger(Block_Loggers.EXAMPLE_USECASE_01)
    logger.info("[hook] undo fired")

def hook_core_event_redo():
    logger = get_logger(Block_Loggers.EXAMPLE_USECASE_01)
    logger.info("[hook] redo fired")

def hook_block_registered(block_instances: list[RTC_Block_Instance]):
    block_names = [b.block_id for b in block_instances]
    logger = get_logger(Block_Loggers.EXAMPLE_USECASE_01)
    logger.info(f"[hook] registered: {', '.join(block_names)}")

def hook_block_unregistered(block_instances: list[RTC_Block_Instance]):
    block_names = [b.block_id for b in block_instances]
    logger = get_logger(Block_Loggers.EXAMPLE_USECASE_01)
    logger.info(f"[hook] unregistered: {', '.join(block_names)}")

def hook_debug_get_state_data_to_print():
    return {"message": "Hello from block-example-simple-2"}

def hook_debug_uilayout_draw_console_print_settings(ui_container: bpy.types.UILayout):
    ui_container.label(text="block-example-simple-2 has no extra print settings")

# ==============================================================================================================================
# BLENDER DATA FOR BLOCK
# ==============================================================================================================================

class DGBLOCKS_PG_Example_Simple_2_Props(bpy.types.PropertyGroup):
    demo_toggle: bpy.props.BoolProperty(default=False, name="Demo Toggle") # type: ignore

# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Example_Simple_2_Demo(bpy.types.Operator):
    bl_idname = "dgblocks.example_simple_2_demo"
    bl_label = "Run Demo Operator"
    bl_options = {"REGISTER"}

    def execute(self, context):
        logger = get_logger(Block_Loggers.EXAMPLE_USECASE_01)
        logger.info("Demo operator executed")
        return {"FINISHED"}

# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_PT_Example_Simple_2_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Example_Simple_2"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name="SHADING_RENDERED")

    def draw(self, context):
        layout = self.layout
        props = context.scene.dgblocks_example_simple_2_props
        layout.prop(props, "demo_toggle")
        layout.operator("dgblocks.example_simple_2_demo")

# ==============================================================================================================================
# REGISTRATION EVENTS
# ==============================================================================================================================

_block_classes_to_register = [
    DGBLOCKS_PG_Example_Simple_2_Props,
    DGBLOCKS_OT_Example_Simple_2_Demo,
    DGBLOCKS_PT_Example_Simple_2_Panel,
]

def register_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management)
    Wrapper_Block_Management.create_instance(
        event,
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_hook_source_enums = Block_Hook_Sources,
        block_RTC_member_enums = Block_RTC_Members,
        block_logger_enums = Block_Loggers,
    )

    bpy.types.Scene.dgblocks_example_simple_2_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Example_Simple_2_Props)

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(event, block_id = _BLOCK_ID)

    if hasattr(bpy.types.Scene, "dgblocks_example_simple_2_props"):
        del bpy.types.Scene.dgblocks_example_simple_2_props

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")

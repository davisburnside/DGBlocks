import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.generic_helpers import get_self_block_module
from ....addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header
from ....my_addon_config import Documentation_URLs, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...block_core.core_features.control_plane import Wrapper_Control_Plane
from ...block_core.core_features.loggers import Core_Block_Loggers, get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .feature_example_02B import DGBLOCKS_OT_Example_Mirror_02B_Edit, DGBLOCKS_PG_Example_02B_Instance, DGBLOCKS_UL_Example_Mirror_02B, Wrapper_Example_Mirror_02B, _uilayout_draw_usecase_02b_settings

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-usecase-mirror-02b"
_BLOCK_VERSION = (1, 0, 0)
_BLOCK_DEPENDENCIES = ["block-core", "block-debug-console-print"]

# ==============================================================================================================================
# BLOCK PROPERTIES
# ==============================================================================================================================

class DGBLOCKS_PG_Example_Usecase_02B_Props(bpy.types.PropertyGroup):
    """Scene-level PropertyGroup holding the mirrored collection."""

    mirror_items: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Example_02B_Instance) # type: ignore
    mirror_items_selected_idx: bpy.props.IntProperty() # type: ignore

# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_PT_Example_Mirror_02B_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Example_Mirror_02B"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        ui_draw_block_panel_header(context, self.layout, _BLOCK_ID, Documentation_URLs.MY_PLACEHOLDER_URL_2, icon_name="SHADING_RENDERED")

    def draw(self, context):
        layout = self.layout
        _uilayout_draw_usecase_02b_settings(context, layout)

# ==============================================================================================================================
# REGISTRATION EVENTS
# ==============================================================================================================================

_block_classes_to_register = [
    DGBLOCKS_PG_Example_Usecase_02B_Props,
    DGBLOCKS_PG_Example_02B_Instance,
    DGBLOCKS_OT_Example_Mirror_02B_Edit,
    DGBLOCKS_UL_Example_Mirror_02B,
    DGBLOCKS_PT_Example_Mirror_02B_Panel,
]

_feature_wrapper_classes_to_register = [
    Wrapper_Example_Mirror_02B,
]

def register_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    block_module = get_self_block_module(block_manager_wrapper=Wrapper_Control_Plane)
    Wrapper_Control_Plane.create_instance(
        event,
        block_module=block_module,
        block_bpy_types_classes=_block_classes_to_register,
        block_feature_wrapper_classes=_feature_wrapper_classes_to_register,
        block_hook_source_enums=Block_Hook_Sources,
        block_RTC_member_enums=Block_RTC_Members,
        block_logger_enums=Block_Loggers,
    )

    bpy.types.Scene.dgblocks_example_mirror_02b_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Example_Usecase_02B_Props)

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Control_Plane.destroy_instance(event, block_id=_BLOCK_ID)

    if hasattr(bpy.types.Scene, "dgblocks_example_mirror_02b_props"):
        del bpy.types.Scene.dgblocks_example_mirror_02b_props

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")

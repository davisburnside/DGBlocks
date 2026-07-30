import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    MET,
    Enum_Read_Source,
    Numpy_Mesh_Action_Declaration,
    Read_Step,
    Callback_Step,
    Group_Tag,
)
from .feature_mesh_extract import Wrapper_Mesh_Extract
from .ui import ui_draw_mesh_extract_instances


# ==============================================================================================================================
# BL PROPERTY GROUPS
#
# Debug/inspection state only. Mesh action results are numpy arrays and live exclusively
# in the RTC — there is nothing here to mirror.
# ==============================================================================================================================

class DGBLOCKS_PG_Mesh_Extract_Props(bpy.types.PropertyGroup):
    """Scene-level property group for block_mesh_extract."""

    debug_mode_enabled: bpy.props.BoolProperty(          # type: ignore
        name        = "Debug Mode",
        description = "Show stored mesh action instances and their per-op timings",
        default     = False,
    )

    debug_expanded_instance_key: bpy.props.StringProperty(  # type: ignore
        name    = "Expanded Instance",
        default = "",
    )

    debug_max_actions_shown: bpy.props.IntProperty(      # type: ignore
        name        = "Actions Shown",
        description = "How many of the most recent actions to display per instance",
        default     = 5,
        min         = 1,
        max         = 50,
    )

    debug_show_op_details: bpy.props.BoolProperty(       # type: ignore
        name        = "Op Details",
        description = "Show the per-read / per-callback / per-write breakdown of each action",
        default     = True,
    )


# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Mesh_Extract_Toggle_Instance(bpy.types.Operator):
    """Expand or collapse this mesh action instance"""
    bl_idname  = "dgblocks.mesh_extract_toggle_instance"
    bl_label   = "Toggle Mesh Extract Instance"
    bl_options = {"INTERNAL"}

    instance_key: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_mesh_extract_props
        props.debug_expanded_instance_key = (
            "" if props.debug_expanded_instance_key == self.instance_key else self.instance_key
        )
        return {"FINISHED"}


class DGBLOCKS_OT_Mesh_Extract_Clear(bpy.types.Operator):
    """Discard stored mesh action data. Leave the object name empty to clear everything"""
    bl_idname  = "dgblocks.mesh_extract_clear"
    bl_label   = "Clear Mesh Extract Data"
    bl_options = {"REGISTER"}

    object_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        removed = Wrapper_Mesh_Extract.clear_instances(self.object_name or None)
        self.report({"INFO"}, f"Cleared {removed} mesh extract instance(s).")
        return {"FINISHED"}


# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_PT_Mesh_Extract_Panel(bpy.types.Panel):
    bl_label       = ""
    bl_idname      = "VIEW3D_PT_Mesh_Extract_Panel"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = addon_title
    bl_options     = {"DEFAULT_CLOSED"}
    bl_order       = 20

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name = "MESH_DATA",
        )

    def draw(self, context):
        layout = self.layout
        props  = context.scene.dgblocks_mesh_extract_props

        instances = Wrapper_Mesh_Extract.get_all_instances()

        row = layout.row(align=True)
        row.prop(props, "debug_mode_enabled", text="Debug Mode", toggle=True)
        clear_all = row.operator("dgblocks.mesh_extract_clear", text="", icon="TRASH")
        clear_all.object_name = ""

        info = layout.row()
        info.enabled = False
        info.label(text=f"{len(instances)} stored instance(s)")

        if not props.debug_mode_enabled:
            return

        options = layout.row(align=True)
        options.prop(props, "debug_max_actions_shown", text="Actions")
        options.prop(props, "debug_show_op_details", text="Ops", toggle=True)
        layout.separator()

        ui_draw_mesh_extract_instances(context, layout, instances, props)


# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS
# ==============================================================================================================================

def register_block_props():
    bpy.types.Scene.dgblocks_mesh_extract_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_Mesh_Extract_Props
    )


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_mesh_extract_props"):
        del bpy.types.Scene.dgblocks_mesh_extract_props


# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                  = sys.modules[__name__],
    block_id                      = "block-mesh-extract",
    block_dependencies            = ["block-core"],
    block_bpy_classes             = [
        DGBLOCKS_PG_Mesh_Extract_Props,
        DGBLOCKS_OT_Mesh_Extract_Toggle_Instance,
        DGBLOCKS_OT_Mesh_Extract_Clear,
        DGBLOCKS_PT_Mesh_Extract_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Mesh_Extract],
    block_RTC_members             = Block_RTC_Members,
    block_loggers                 = Block_Loggers,
)
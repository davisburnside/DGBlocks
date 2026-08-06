import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.generic_tools import is_block_debug_mode_enabled
from ...addon_helpers.ui import ui_draw_block_panel_header

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (  # noqa: F401 — public re-exports for downstream blocks
    CET,
    MET,
    Callback_Step,
    Enum_Geometry_Target,
    Enum_Read_Source,
    Geometry_Actions_Declaration,
    Group_Tag,
    Read_Step,
)
from .feature_geometry_actions import Wrapper_Geometry_Actions
from .helpers_actions import get_all_stacks
from .ui import toggle_expanded_key, ui_draw_geometry_action_stacks


# ==============================================================================================================================
# BL PROPERTY GROUPS
#
# Debug/inspection state only. Action results are numpy arrays and live exclusively in the
# RTC — there is nothing here to mirror.
# ==============================================================================================================================

class DGBLOCKS_PG_Geometry_Actions_Props(bpy.types.PropertyGroup):
    """Scene-level property group for block_geometry_actions."""

    debug_expanded_keys: bpy.props.StringProperty(  # type: ignore
        name        = "Expanded Keys",
        description = "CSV of expanded panel keys — supports collapsing at every depth",
        default     = "",
    )

    debug_max_actions_shown: bpy.props.IntProperty(      # type: ignore
        name        = "Passes Shown",
        description = "How many of the most recent passes to display per stored result",
        default     = 5,
        min         = 1,
        max         = 50,
    )


# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Geometry_Actions_Toggle_Expanded(bpy.types.Operator):
    """Expand or collapse this section"""
    bl_idname  = "dgblocks.geometry_actions_toggle_expanded"
    bl_label   = "Toggle Geometry Actions Section"
    bl_options = {"INTERNAL"}

    expand_key: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        toggle_expanded_key(context.scene.dgblocks_geometry_actions_props, self.expand_key)
        return {"FINISHED"}


class DGBLOCKS_OT_Geometry_Actions_Clear(bpy.types.Operator):
    """Discard stored geometry action results. Leave both fields empty to clear everything"""
    bl_idname  = "dgblocks.geometry_actions_clear"
    bl_label   = "Clear Geometry Action Results"
    bl_options = {"REGISTER"}

    declaration_id: bpy.props.StringProperty()  # type: ignore
    object_name:    bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        removed = Wrapper_Geometry_Actions.clear_results(
            self.declaration_id or None,
            self.object_name or None,
        )
        self.report({"INFO"}, f"Cleared {removed} geometry action result stack(s).")
        return {"FINISHED"}


# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_PT_Geometry_Actions_Panel(bpy.types.Panel):
    """
    Debug helper panel. It only exists while this block's `debug_mode_enabled` flag is set
    (toggled in core's All Blocks UIList) — poll() hides the whole panel otherwise, rather
    than drawing an empty shell.
    """
    bl_label       = ""
    bl_idname      = "VIEW3D_PT_Geometry_Actions_Panel"
    bl_space_type  = "VIEW_3D"
    bl_region_type = "UI"
    bl_category    = addon_title
    bl_options     = {"DEFAULT_CLOSED"}
    bl_order       = 20

    @classmethod
    def poll(cls, context):
        return is_block_debug_mode_enabled(_BLOCK_DECLARATION.block_id)

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration = _BLOCK_DECLARATION,
        )

    def draw(self, context):
        layout = self.layout
        props  = context.scene.dgblocks_geometry_actions_props
        stacks = get_all_stacks()

        header = layout.row(align=True)
        header.prop(props, "debug_max_actions_shown", text="Passes")
        clear_all = header.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH"
        )
        clear_all.declaration_id = ""
        clear_all.object_name    = ""

        layout.separator()
        ui_draw_geometry_action_stacks(context, layout, stacks, props)


# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS
# ==============================================================================================================================

def register_block_props():
    bpy.types.Scene.dgblocks_geometry_actions_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_Geometry_Actions_Props
    )


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_geometry_actions_props"):
        del bpy.types.Scene.dgblocks_geometry_actions_props


# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                  = sys.modules[__name__],
    block_id                      = "block-geometry-actions",
    block_dependencies            = ["block-core"],
    block_bpy_classes             = [
        DGBLOCKS_PG_Geometry_Actions_Props,
        DGBLOCKS_OT_Geometry_Actions_Toggle_Expanded,
        DGBLOCKS_OT_Geometry_Actions_Clear,
        DGBLOCKS_PT_Geometry_Actions_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Geometry_Actions],
    block_RTC_members             = Block_RTC_Members,
    block_loggers                 = Block_Loggers,
    icon                          = "MESH_DATA",
    documentation_url             = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

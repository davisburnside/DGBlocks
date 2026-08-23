import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.generic_tools import is_block_debug_mode_enabled
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header

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
    Read_Step,
)
from .feature_geometry_actions import Wrapper_Geometry_Actions
from .helpers_actions import get_all_results, get_result_by_key, result_payload_to_string
from .ui import ui_draw_geometry_action_results

# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

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
        self.report({"INFO"}, f"Cleared {removed} geometry action result(s).")
        return {"FINISHED"}


class DGBLOCKS_OT_Geometry_Actions_Copy_Result(bpy.types.Operator):
    """Copy this geometry action's complete domain and derived payload"""
    bl_idname = "dgblocks.geometry_actions_copy_result"
    bl_label = "Copy Geometry Action Result"
    bl_options = {"INTERNAL"}

    result_key: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        result = get_result_by_key(self.result_key)
        if result is None:
            self.report({"ERROR"}, "Geometry action result no longer exists")
            return {"CANCELLED"}
        text = result_payload_to_string(result)
        context.window_manager.clipboard = text
        self.report({"INFO"}, f"Copied {len(text)} characters")
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
        results = get_all_results()

        header = layout.row(align=True)
        header.label(text=f"{len(results)} stored action(s)")
        clear_all = header.operator(
            "dgblocks.geometry_actions_clear", text="", icon="TRASH"
        )
        clear_all.declaration_id = ""
        clear_all.object_name    = ""

        layout.separator()
        ui_draw_geometry_action_results(context, layout, results)


# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                  = sys.modules[__name__],
    block_id                      = "block-geometry-actions",
    block_dependencies            = ["block-core"],
    block_bpy_classes             = [
        DGBLOCKS_OT_Geometry_Actions_Clear,
        DGBLOCKS_OT_Geometry_Actions_Copy_Result,
        DGBLOCKS_PT_Geometry_Actions_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Geometry_Actions],
    block_RTC_members             = Block_RTC_Members,
    block_loggers                 = Block_Loggers,
    icon                          = "MESH_DATA",
    documentation_url             = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

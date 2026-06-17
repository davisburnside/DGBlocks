
import sys
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui import draw_shared_uilist, ui_draw_block_panel_header

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_helpers.constants import Core_Runtime_Cache_Members

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import (
    Block_Data_Mirrors,
    Block_Hook_Sources,
    Block_Loggers,
    Block_RTC_Members,
    Block_UIList_Configs,
)
from .feature_mesh_extract import Wrapper_Mesh_Extract
from .data_structures import MET, Mesh_Extract_Target, Mesh_Extract_Callback
from .helpers import run_mesh_extract

cache_key_instances  = Block_RTC_Members.MESH_EXTRACT_INSTANCES
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

def _cb_run_mesh_extract_changed(self, context):
    """
    Fired when the user sets run_mesh_extract = True via the panel button or via Python.
    Auto-resets the property to False, then triggers a full extraction cycle.
    Guarded against re-entrant sync loops.
    """
    if not self.run_mesh_extract:
        return

    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key_instances):
        return

    # Immediately reset so the property acts as a momentary trigger
    self.run_mesh_extract = False

    try:
        run_mesh_extract()
    except Exception:
        from ..block_core.core_features.loggers.feature_wrapper import get_logger
        get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE).error(
            "_cb_run_mesh_extract_changed: run_mesh_extract() raised an exception",
            exc_info=True,
        )


# ==============================================================================================================================
# BL PROPERTY GROUPS
# ==============================================================================================================================

class DGBLOCKS_PG_Mesh_Extract_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per RTC_Mesh_Extract_Instance.
    Stores the object_name UID and the is_valid status flag.
    The heavy numpy data lives only in the RTC — not here.
    """
    object_name: bpy.props.StringProperty()        # type: ignore
    is_valid:    bpy.props.BoolProperty(           # type: ignore
        name    = "Valid",
        default = False,
    )


class DGBLOCKS_PG_Mesh_Extract_Props(bpy.types.PropertyGroup):
    """Scene-level property group for block_mesh_extract."""

    run_mesh_extract: bpy.props.BoolProperty(      # type: ignore
        name        = "Run Mesh Extract",
        description = (
            "Set True to trigger a full mesh extraction cycle. "
            "Automatically resets to False after triggering."
        ),
        default = False,
        update  = _cb_run_mesh_extract_changed,
    )

    extract_mirror: bpy.props.CollectionProperty(   # type: ignore
        type = DGBLOCKS_PG_Mesh_Extract_Mirror_Row,
    )

    extract_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

    debug_mode_enabled: bpy.props.BoolProperty(default=False)  # type: ignore


# ==============================================================================================================================
# OPERATORS
# ==============================================================================================================================

class DGBLOCKS_OT_Run_Mesh_Extract(bpy.types.Operator):
    """Trigger a full mesh extraction cycle for all registered objects."""
    bl_idname = "dgblocks.run_mesh_extract"
    bl_label  = "Run Mesh Extract"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            processed = Wrapper_Mesh_Extract.run_extract()
            self.report({"INFO"}, f"Mesh Extract complete — {len(processed)} object(s) processed.")
        except ValueError as e:
            self.report({"ERROR"}, f"Mesh Extract validation error: {e}")
        except Exception as e:
            self.report({"ERROR"}, f"Mesh Extract failed: {e}")
        return {"FINISHED"}


# ==============================================================================================================================
# UI
# ==============================================================================================================================

class DGBLOCKS_UL_Mesh_Extract_List(bpy.types.UIList):
    bl_idname = "DGBLOCKS_UL_Mesh_Extract_List"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        icon_name = "CHECKMARK" if item.is_valid else "ERROR"
        row.label(text="", icon=icon_name)
        row.label(text=item.object_name)


class DGBLOCKS_PT_Mesh_Extract_Panel(bpy.types.Panel):
    bl_label      = ""
    bl_idname     = "VIEW3D_PT_Mesh_Extract_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category   = addon_title
    bl_options    = {"DEFAULT_CLOSED"}
    bl_order      = 20

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

        # Trigger button
        row = layout.row()
        row.scale_y = 1.4
        row.operator("dgblocks.run_mesh_extract", icon="PLAY")

        layout.prop(props, "debug_mode_enabled", text="Debug Mode")
        layout.separator()

        instances = Wrapper_Mesh_Extract.get_all_instances()
        if not instances:
            layout.label(text="No extracted objects", icon="INFO")
            return

        draw_shared_uilist(context, layout, "extract_mirror")


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
        DGBLOCKS_PG_Mesh_Extract_Mirror_Row,
        DGBLOCKS_PG_Mesh_Extract_Props,
        DGBLOCKS_UL_Mesh_Extract_List,
        DGBLOCKS_PT_Mesh_Extract_Panel,
        DGBLOCKS_OT_Run_Mesh_Extract,
    ],
    block_feature_wrapper_classes = [Wrapper_Mesh_Extract],
    block_hook_sources            = Block_Hook_Sources,
    block_RTC_members             = Block_RTC_Members,
    block_data_mirrors            = Block_Data_Mirrors,
    block_loggers                 = Block_Loggers,
    block_uilist_configs          = Block_UIList_Configs,
)

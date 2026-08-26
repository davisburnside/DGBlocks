import sys

import bpy

from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.data_structures import Block_Declaration, Unit_Test_Suite_Declaration
from ...addon_helpers.generic_tools import is_block_debug_mode_enabled
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header
from .. import block_core  # noqa: F401 — block-core is the only dependency
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import (  # noqa: F401 — public API declarations/enums
    Library_Ensure_Result,
    Library_Source_Policy,
    Library_Status,
    Python_Library_Requirement_Declaration,
    RTC_Library_Info,
    RTC_Library_Requirement_Info,
)
from .feature_pip_library_manager import Wrapper_Pip_Library_Manager
from .ui import (
    DGBLOCKS_OT_Pip_Library_Cancel,
    DGBLOCKS_OT_Pip_Library_Confirm_Install,
    DGBLOCKS_OT_Pip_Library_Open_Path,
    DGBLOCKS_OT_Pip_Library_Progress,
    DGBLOCKS_OT_Pip_Library_Refresh,
    ui_draw_pip_library_manager,
)


def hook_post_startup():
    """Discover declarations and package metadata; never imports or installs packages."""
    Wrapper_Pip_Library_Manager.repoll()


def hook_get_unit_test_declarations():
    from .unit_tests.run_tests import build_suite
    return [Unit_Test_Suite_Declaration(
        suite_id = _BLOCK_DECLARATION.block_id,
        build_suite = build_suite,
        label = "Pip Library Manager",
    )]


class DGBLOCKS_PG_Pip_Library_Status_Row(bpy.types.PropertyGroup):
    distribution_name: bpy.props.StringProperty()  # type: ignore
    installed_version: bpy.props.StringProperty()  # type: ignore
    required_versions: bpy.props.StringProperty()  # type: ignore
    status: bpy.props.StringProperty()  # type: ignore
    requesting_blocks: bpy.props.StringProperty()  # type: ignore
    error_summary: bpy.props.StringProperty()  # type: ignore


class DGBLOCKS_PG_Pip_Library_Manager_Props(bpy.types.PropertyGroup):
    # Ephemeral display projection only. RTC/filesystem are authoritative.
    library_status_rows: bpy.props.CollectionProperty(
        type=DGBLOCKS_PG_Pip_Library_Status_Row
    )  # type: ignore


class DGBLOCKS_PT_Pip_Library_Manager(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_Pip_Library_Manager"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 28

    @classmethod
    def poll(cls, context):
        return is_block_debug_mode_enabled(_BLOCK_DECLARATION.block_id)

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context,
            self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration=_BLOCK_DECLARATION,
        )

    def draw(self, context):
        ui_draw_pip_library_manager(context, self.layout)


def register_block_props():
    bpy.types.Scene.dgblocks_pip_library_manager_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_Pip_Library_Manager_Props
    )


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_pip_library_manager_props"):
        del bpy.types.Scene.dgblocks_pip_library_manager_props


_BLOCK_DECLARATION = Block_Declaration(
    block_module=sys.modules[__name__],
    block_id="block-pip-library-manager",
    block_version=(1, 0, 0),
    block_dependencies=["block-core"],
    block_bpy_classes=[
        DGBLOCKS_PG_Pip_Library_Status_Row,
        DGBLOCKS_PG_Pip_Library_Manager_Props,
        DGBLOCKS_OT_Pip_Library_Confirm_Install,
        DGBLOCKS_OT_Pip_Library_Progress,
        DGBLOCKS_OT_Pip_Library_Cancel,
        DGBLOCKS_OT_Pip_Library_Refresh,
        DGBLOCKS_OT_Pip_Library_Open_Path,
        DGBLOCKS_PT_Pip_Library_Manager,
    ],
    block_feature_wrapper_classes=[Wrapper_Pip_Library_Manager],
    block_hook_sources=Block_Hook_Sources,
    block_RTC_members=Block_RTC_Members,
    block_loggers=Block_Loggers,
    icon="PACKAGE",
    documentation_url=Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

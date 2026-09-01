
import sys
import bpy

from ...addon_helpers.generic_tools import force_redraw_ui
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events, Unit_Test_Suite_Declaration
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist, ui_draw_subpanel
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .data_structures import DGBLOCKS_PG_Shader_Mirror_Row
from .feature_shader_manager import Wrapper_Shader_Manager
from .hook_subs import _hook_before_first_draw, _hook_get_shader_declarations, _hook_get_timer_definitions, _hook_post_startup
from .helpers import _clear_all_shaders, _rebuild_all_shaders, _hook_get_modal_listener_definitions
from .builtin_shaders_and_effects.demo_ui import DGBLOCKS_OT_Toggle_Demo_Animation, DGBLOCKS_OT_Toggle_Textbox_Mouse_Capture, DGBLOCKS_OT_Textbox_Line_Add, DGBLOCKS_OT_Textbox_Line_Remove, _ui_draw_shader_examples_subpanel
from .builtin_shaders_and_effects.demo_props import DGBLOCKS_PG_Debug_Shader_Example_Props, DGBLOCKS_PG_Demo_Shader_Attribute, DGBLOCKS_PG_Demo_Shader_Common, DGBLOCKS_PG_Debug_Shader_Region_Toggles, DGBLOCKS_PG_Textbox_Line_Row
from .ui import DGBLOCKS_OT_Control_Animation

# ==============================================================================================================================
# MAIN DEBUG PANEL

def _cb_enable_drawing_changed(self, context):
    """
    Fired when scene.enable_drawing property changes.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing("SHADERS"):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    if context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
        _rebuild_all_shaders(event)
    else:
        _clear_all_shaders()

class DGBLOCKS_PG_Onscreen_Drawing_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_onscreen_drawing.
    Stored on bpy.types.Scene.dgblocks_onscreen_drawing_props.
    """
    
    enable_drawing: bpy.props.BoolProperty(name="UI Shaders Enabled", default=False, update=_cb_enable_drawing_changed) # type: ignore
    debug_props: bpy.props.PointerProperty(type = DGBLOCKS_PG_Debug_Shader_Example_Props) # type: ignore
    debug_show_examples: bpy.props.BoolProperty(name="Show Shader Examples", default=False) # type: ignore
    
    # keyed by demo_id, each carrying show_shader / is_animating / animation_fps / scale 
    # Can also own CollectionProperty of shader-unique attributes. 
    # Seeded by ensure_demo_rows().
    demo_settings: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Demo_Shader_Common)  # type: ignore
    
    # Unlike most mirrors, this contains no actual BL -> RTC sync logic.
    # RTC is always SoT, and is repopulated every Wrapper_Shader_Manager.repoll()
    shader_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

    # Text Boxes demo: user-authored lines, pushed into Textbox_Demo_Shader via add_line()
    # from hook_before_first_draw. Pure BL data — no RTC mirror needed.
    textbox_lines: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Textbox_Line_Row)  # type: ignore
    textbox_lines_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

def hook_before_first_draw():
    return _hook_before_first_draw()


def hook_get_shader_declarations():
    return _hook_get_shader_declarations()


def hook_get_timer_definitions():
    return _hook_get_timer_definitions()


def hook_get_modal_listener_definitions():
    """
    Subscribed by function-name convention to block_modal_events' hook (see helpers.py for why
    this is safe without a declared block_dependency). Only ever contributes a listener while
    the textbox demo's mouse-capture toggle is on; a no-op otherwise, including when
    block_modal_events isn't active at all.
    """
    return _hook_get_modal_listener_definitions()


def hook_post_startup():
    return _hook_post_startup()


def hook_get_unit_test_declarations():
    from .unit_tests.run_tests import build_suite_geometry_math, build_suite_shader_creation, build_suite_shader_validation
    return [
        Unit_Test_Suite_Declaration(suite_id="shader-validation", build_suite=build_suite_shader_validation, label="Shader Validation", suite_group="Shader Validation"),
        Unit_Test_Suite_Declaration(suite_id="shader-creation", build_suite=build_suite_shader_creation, label="Shader Creation", suite_group="Shader Creation"),
        Unit_Test_Suite_Declaration(suite_id="geometry-math", build_suite=build_suite_geometry_math, label="Geometry Math", suite_group="Geometry Math"),
    ]

# ==============================================================================================================================
# UI

class DGBLOCKS_OT_Toggle_Shader(bpy.types.Operator):
    """Toggle a shader's visibility. is_enabled is RTC-only, so this must NOT enter the undo stack."""
    bl_idname = "dgblocks.toggle_shader"
    bl_label = "Toggle Shader"
    # INTERNAL hides it from search; omitting REGISTER/UNDO keeps it off the undo stack.
    bl_options = {"INTERNAL"}

    shader_uid: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        shader = Wrapper_Shader_Manager.get_shader(self.shader_uid)
        if shader is None:
            self.report({"WARNING"}, f"Shader '{self.shader_uid}' not found")
            return {"CANCELLED"}
        shader.is_enabled = not shader.is_enabled
        force_redraw_ui(only_3Dviewport = False)
        return {"FINISHED"}


class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    
    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration = _BLOCK_DECLARATION,
        )

    def draw(self, context):
        layout = self.layout
        drawing_props = context.scene.dgblocks_onscreen_drawing_props
        all_shaders = Wrapper_Shader_Manager.get_all_shaders()

        # Master enable / disable toggle
        row = layout.row()
        # row.enabled = len(all_shaders) > 0
        row.scale_y = 2
        row.prop(drawing_props, "enable_drawing", toggle = True)

        # Example / debug shaders grouped under a collapsible subpanel. Each demo is now its own
        # nested sub-subpanel with an eye toggle; per-demo animation toggles replace the old
        # "Sample Animations" button.
        ui_draw_subpanel(
            context, layout, "onscreen_shader_examples", "Shader Examples",
            _ui_draw_shader_examples_subpanel,
        )

        if not drawing_props.shader_mirror:
            box = layout.box()
            box.label(text="No active shaders", icon="INFO")
        else:
            draw_shared_uilist(context, layout, "shader_mirror")

# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS

def register_block_props():
    bpy.types.Scene.dgblocks_onscreen_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Onscreen_Drawing_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_onscreen_drawing_props"):
        del bpy.types.Scene.dgblocks_onscreen_drawing_props

# ==============================================================================================================================
# REQUIRED

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-onscreen-draw",
    block_dependencies = ["block-core", "block-timers"],
    block_bpy_classes = [
        # Nested PropertyGroups must register before the groups that point to them.
        DGBLOCKS_PG_Demo_Shader_Attribute,
        DGBLOCKS_PG_Demo_Shader_Common,
        DGBLOCKS_PG_Debug_Shader_Region_Toggles,
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Textbox_Line_Row,
        DGBLOCKS_PG_Debug_Shader_Example_Props,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_OT_Toggle_Shader,
        DGBLOCKS_OT_Toggle_Demo_Animation,
        DGBLOCKS_OT_Toggle_Textbox_Mouse_Capture,
        DGBLOCKS_OT_Textbox_Line_Add,
        DGBLOCKS_OT_Textbox_Line_Remove,
        DGBLOCKS_OT_Control_Animation,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Shader_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
    icon = "FILE_3D",
    documentation_url = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

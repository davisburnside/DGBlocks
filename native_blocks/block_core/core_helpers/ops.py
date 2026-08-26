import os

from ....addon_helpers.data_tools import simple_truncate_dict
from ....addon_helpers.ui.helpers import ui_draw_block_panel_header, measure_text_width_px, wrap_text_to_lines
from ....addon_config.static_settings import addon_name
import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helpers.generic_tools import force_reload_all_scripts, force_redraw_ui
from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.text_formatting_tools import make_pretty_json_string_from_data


# --------------------------------------------------------------
# Core block imports
# --------------------------------------------------------------
from ..core_helpers.constants import Core_Block_Loggers, Core_Block_Hook_Sources, Core_Runtime_Cache_Members
from ..core_features.loggers.feature_wrapper import  get_logger
from ..core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..core_features.control_plane.helpers import reload_flag_name
from ..core_features.unit_testing.feature_wrapper import Wrapper_Unit_Testing
from ..core_helpers.ui import RTC_COPY_ALL_KEY


# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_hook_subs = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS
cache_key_loggers = Core_Runtime_Cache_Members.REGISTRY_ALL_LOGGERS

class DGBLOCKS_OT_Open_Help_Page(bpy.types.Operator):
    bl_idname = "dgblocks.open_help_page"
    bl_label = "Learn more"
    bl_options = {"REGISTER"}
    
    web_documentation_url: bpy.props.StringProperty() # type: ignore 
    
    @classmethod
    def description(cls, context, properties):
        return properties.web_documentation_url

    def execute(self, context):
        
        import webbrowser
        webbrowser.open(self.web_documentation_url)
        return {"FINISHED"}


class DGBLOCKS_OT_Copy_To_Clipboard(bpy.types.Operator):
    bl_idname = "dgblocks.copy_to_clipboard"
    bl_label = "Copy"
    bl_description = "Copy to clipboard"

    # Literal text to copy. Used whenever 'rtc_key' is left empty
    text: bpy.props.StringProperty()  # type: ignore

    # Optional. RTC_COPY_ALL_KEY = whole cache, otherwise a single RTC member name.
    # When set, the string is generated at execute-time and 'text' is ignored
    rtc_key: bpy.props.StringProperty()  # type: ignore

    @classmethod
    def description(cls, context, properties):
        if properties.rtc_key == RTC_COPY_ALL_KEY:
            return "Copy a string snapshot of the entire Runtime Cache to the clipboard"
        if properties.rtc_key:
            return f"Copy a string snapshot of RTC member '{properties.rtc_key}' to the clipboard"
        return "Copy to clipboard"

    def execute(self, context):

        text_to_copy = self.text
        rtc_key = self.rtc_key
        if rtc_key:
            try:
                if rtc_key == RTC_COPY_ALL_KEY:
                    raw_data = Wrapper_Runtime_Cache.get_all_cache()
                    header = "# DGBlocks Runtime Cache — all members"
                else:
                    all_keys = Wrapper_Runtime_Cache.get_all_cache_keys()
                    if rtc_key not in all_keys:
                        raise KeyError(f"RTC member '{rtc_key}' does not exist")
                    raw_data = Wrapper_Runtime_Cache.get_cache(rtc_key)
                    header = f"# DGBlocks Runtime Cache — member '{rtc_key}'"
            
                formatted_body = simple_truncate_dict(raw_data, max_str=160, max_array_items=8, max_depth=7, _depth=0)
                # formatted_body = make_pretty_json_string_from_data(formatted_body)
                formatted_body = str(formatted_body)
                context.window_manager.clipboard = formatted_body
                return {'FINISHED'}
                                
                
            except Exception:
                logger = get_logger(Core_Block_Loggers.UI)
                logger.error(f"Unable to build RTC snapshot for '{self.rtc_key}'", exc_info = True)
                self.report({'ERROR'}, f"Unable to read RTC member '{self.rtc_key}'")
                return {'CANCELLED'}

        context.window_manager.clipboard = text_to_copy
        self.report({'INFO'}, f"Copied {len(text_to_copy)} characters to clipboard")
        return {'FINISHED'}


class DGBLOCKS_OT_Force_Reload_Scripts(bpy.types.Operator):
    bl_idname = "dgblocks.debug_force_reload_scripts"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    web_documentation_url: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):
        
        force_reload_all_scripts(context)
            
        return {"FINISHED"}

class DGBLOCKS_OT_Force_Reload_Refresh_UI(bpy.types.Operator):
    bl_idname = "dgblocks.debug_force_refresh_ui"
    bl_label = "Refresh UI"
    bl_options = {"REGISTER"}
    
    def execute(self, context):
        
        force_redraw_ui(context)
        return {"FINISHED"}
   
class DGBLOCKS_OT_Reload_All_Blocks(bpy.types.Operator):
    bl_idname = "dgblocks.reload_all_blocks"
    bl_label = "Reload All Blocks"
    bl_description = "Fire hook_before_blocks_reload, call bpy.ops.script.reload(), then fire hook_after_blocks_reload"
    bl_options = {"REGISTER"}

    def _reload(self):
        bpy.ops.script.reload()
        return None

    def execute(self, context):
        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.info("Reload-all: firing hook_before_blocks_reload")
        responses = Wrapper_Hooks.run_hooked_funcs(hook_func_name=Core_Block_Hook_Sources.hook_before_blocks_reload)
        wm = bpy.context.window_manager
        for block_id, block_response in responses.items():
            try:
                wm[block_id] = block_response
            except Exception as e:
                logger.error("Unable to store data before reload, likely invalid data type", exc_info = True)
        bpy.app.timers.register(self._reload, first_interval=0.1)
        return {"FINISHED"}


class DGBLOCKS_OT_Run_All_Unit_Tests(bpy.types.Operator):
    bl_idname = "dgblocks.run_all_unit_tests"
    bl_label = "Run All Unit Tests"
    bl_description = "Run every enabled block's unit tests"
    bl_options = {"REGISTER"}

    def execute(self, context):
        report = Wrapper_Unit_Testing.run_all()
        force_redraw_ui(context)
        self.report({'INFO'}, f"Unit tests: ran {len(report.block_ids_run)} block(s)")
        return {"FINISHED"}


class DGBLOCKS_OT_Run_Block_Unit_Tests(bpy.types.Operator):
    bl_idname = "dgblocks.run_block_unit_tests"
    bl_label = "Run Block Unit Tests"
    bl_description = "Run every test declared by one block, regardless of subgroup"
    bl_options = {"REGISTER"}

    block_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        Wrapper_Unit_Testing.run_block_unit_tests(self.block_id)
        force_redraw_ui(context)
        return {"FINISHED"}


class DGBLOCKS_OT_Run_Group_Unit_Tests(bpy.types.Operator):
    bl_idname = "dgblocks.run_group_unit_tests"
    bl_label = "Run Group Unit Tests"
    bl_description = "Run every test in one block's subgroup"
    bl_options = {"REGISTER"}

    block_id: bpy.props.StringProperty()     # type: ignore
    suite_group: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        Wrapper_Unit_Testing.run_group_unit_tests(self.block_id, self.suite_group)
        force_redraw_ui(context)
        return {"FINISHED"}


class DGBLOCKS_OT_Run_One_Unit_Test(bpy.types.Operator):
    bl_idname = "dgblocks.run_one_unit_test"
    bl_label = "Run Test"
    bl_description = "Run exactly one unit test"
    bl_options = {"REGISTER"}

    test_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        Wrapper_Unit_Testing.run_one_test(self.test_id)
        force_redraw_ui(context)
        return {"FINISHED"}


class DGBLOCKS_OT_Show_Unit_Test_Docstring(bpy.types.Operator):
    bl_idname = "dgblocks.show_unit_test_docstring"
    bl_label = "Test Description"
    bl_description = "Show this test's own docstring — the test documents itself"
    bl_options = {"INTERNAL"}

    test_id: bpy.props.StringProperty()  # type: ignore

    _MIN_WIDTH = 220
    _MAX_WIDTH = 520
    _HORIZONTAL_PADDING = 40  # icon + box margins invoke_popup reserves around layout content

    def invoke(self, context, event):
        case = Wrapper_Unit_Testing.get_test(self.test_id)
        docstring = (case.docstring if case else None) or "(no description)"

        # Snug-fit when it's short: measure the whole string unwrapped and size the popup to
        # exactly that (clamped) rather than always opening the same fixed width. Only text
        # that's actually too long to fit at _MAX_WIDTH gets wrapped into multiple lines —
        # UILayout.label() truncates with a middle ellipsis instead of wrapping on its own.
        natural_width = measure_text_width_px(docstring)
        popup_width = int(max(self._MIN_WIDTH, min(self._MAX_WIDTH, natural_width + self._HORIZONTAL_PADDING)))
        self._lines = wrap_text_to_lines(docstring, popup_width - self._HORIZONTAL_PADDING)

        return context.window_manager.invoke_popup(self, width = popup_width)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align = True)
        for line in getattr(self, "_lines", []):
            col.label(text = line if line else " ")  # label() collapses "" — force a blank line to render

    def execute(self, context):
        return {"FINISHED"}


class DGBLOCKS_OT_Refresh_Unit_Test_Catalog(bpy.types.Operator):
    bl_idname = "dgblocks.refresh_unit_test_catalog"
    bl_label = "Refresh Unit Test Catalog"
    bl_description = "Re-discover unit test declarations from all blocks without running any of them"
    bl_options = {"REGISTER"}

    def execute(self, context):
        Wrapper_Unit_Testing.collect_all()
        force_redraw_ui(context)
        return {"FINISHED"}


class DGBLOCKS_OT_Debug_Clear_And_Restore_Caches(bpy.types.Operator):
    bl_idname = "dgblocks.debug_clear_and_restore_caches"
    bl_label = "Reload scripts"
    bl_options = {"REGISTER"}
    
    action: bpy.props.StringProperty() # type: ignore 
    target: bpy.props.StringProperty() # type: ignore 

    def execute(self, context):

        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)

        # Clearing these would prevent restore-action
        rtc_members_to_skip = ["REGISTRY_ALL_BLOCKS", "REGISTRY_ALL_FWCS"]

        event = Enum_Sync_Events.PROPERTY_UPDATE
        
        # Clear or restore the RTC, Blender data is unaffected
        if self.target == "RTC":

            # Clearing data does not use _remove_instance function. It directly updates the RTC's _cache. This should not be done in a production setting
            if self.action == "CLEAR":
                for cache_key, cache_data in Wrapper_Runtime_Cache._cache.items():
                    if cache_key in rtc_members_to_skip:
                        continue
                    if isinstance(cache_data, list):
                        print(f"Clearing RTC list {cache_key}")
                        Wrapper_Runtime_Cache.set_cache(cache_key, [])
                    elif isinstance(cache_data, dict):
                        print(f"Clearing RTC dict {cache_key}")
                        Wrapper_Runtime_Cache.set_cache(cache_key, {})
                    else:
                        print(f"Ignoring RTC list {cache_key}")

            # Use Block-mgmt FWC's native restoration feature
            elif self.action == "RESTORE":
                Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = True, logger = logger) 

        # Clear or restore Blender data, RTC is unaffected
        if self.target == "BL":
            if self.action == "CLEAR":
                for cache_key, cache_data in Wrapper_Runtime_Cache._cache.items():
                    if cache_key in rtc_members_to_skip:
                        continue
                    if isinstance(cache_data, list):
                        print(f"Clearing RTC list {cache_key}")
                        Wrapper_Runtime_Cache.set_cache(cache_key, [])
            elif self.action == "RESTORE":
                Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source = False, logger = logger)

        return {"FINISHED"}


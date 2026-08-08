import os

from ....addon_helpers.data_tools import simple_truncate_dict
from ....addon_helpers.ui.helpers import ui_draw_block_panel_header
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


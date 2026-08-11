
from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Feature_Wrapper, Abstract_Shared_UIList_Draw, Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop
from ..block_core.core_features.loggers.feature_wrapper import get_logger

# Intra-block imports
from .common_declarations import  Block_Loggers, Block_RTC_Members
from .helpers import _clear_all_shaders, _rebuild_all_shaders
from .data_structures import Shader_Instance

class Wrapper_Shader_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def repoll(cls):
       bpy.context.scene.dgblocks_onscreen_drawing_props.enable_drawing = True


    @classmethod
    def disable_shaders(cls):
       bpy.context.scene.dgblocks_onscreen_drawing_props.enable_drawing = False


    @classmethod
    def get_shader(cls, uid: str) -> Optional[Shader_Instance]:
        """Return the live Shader_Instance for a given uid, or None if not found."""
        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
        return shader

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager init")

        # The initial pass only exists in the RTC. BL data is not overwritten yet
        event = Enum_Sync_Events.ADDON_INIT
        if bpy.context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
            _rebuild_all_shaders(event, sync_BL = False)
        else:
            _clear_all_shaders()
        return True


    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        logger.debug("Wrapper_Shader_Manager destroy — clearing all handlers")
        _clear_all_shaders()

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        if event == Enum_Sync_Events.ADDON_INIT:
            return
        if not drawing_props.enable_drawing:
            _clear_all_shaders()
            return
        
        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}]
        logger.debug(f"BL: {len(data_source)} items | RTC: {len(data_target)} items. | {len(filtered_actions)} Actions")

        # sync_BL = event != Enum_Sync_Events.ADDON_INIT
        if len(filtered_actions) > 0:
            sync_BL = event in {Enum_Sync_Events.PROPERTY_UPDATE_REDO, Enum_Sync_Events.PROPERTY_UPDATE_UNDO, Enum_Sync_Events.PROPERTY_UPDATE}
            _rebuild_all_shaders(event, sync_BL)

        # Toggle is_enabled for each row marked for edit. is_enabled is the only UI-editable property of shaders
        edit_actions = [a for a in actions if a.__class__ == data_sync_tools.Edit]
        for action in edit_actions:
            shader_instance = data_target[action.source_idx]
            shader_instance.is_enabled = not shader_instance.is_enabled
        

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        
        # This function assumes that _rebuild_all_shaders() has been already executed after the RTC update event
        logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
        drawing_props = bpy.context.scene.dgblocks_onscreen_drawing_props
        cached_shaders = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)

        key_fields = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.SHADERS)
        data_source = drawing_props.shader_mirror
        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}]
        if len(filtered_actions) > 0:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.SHADERS)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, True)
            try:

                # Clear & Repopulate CollectionProperty
                drawing_props.shader_mirror.clear()
                for shader_instance in cached_shaders:
                    space_name = shader_instance.draw_space.name
                    region_str = str(shader_instance.draw_region)
                    phase_str = str(shader_instance.draw_phase)
                    BL_shader = drawing_props.shader_mirror.add()
                    BL_shader.shader_uid = shader_instance.shader_uid
                    BL_shader.is_enabled = shader_instance.is_enabled
                    BL_shader.draw_space = space_name
                    BL_shader.draw_region = region_str
                    BL_shader.draw_phase = phase_str

            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.SHADERS, False)

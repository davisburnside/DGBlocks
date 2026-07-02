
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
from .common_declarations import Block_Loggers, Block_RTC_Members
from .helpers import _clear_all_timers, _rebuild_all_timers, _register_bpy_timer, _unregister_bpy_timer
from .data_structures import Timer_Instance

# Aliases
cache_key_timers = Block_RTC_Members.TIMERS


class Wrapper_Timer_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def enable_and_poll_for_timers(cls):
        """Set enable_timers = True, which triggers a full rebuild cycle."""
        bpy.context.scene.dgblocks_timers_props.enable_timers = True

    @classmethod
    def disable_timers(cls):
        """Set enable_timers = False, which tears down all live bpy timers."""
        bpy.context.scene.dgblocks_timers_props.enable_timers = False

    @classmethod
    def get_timer(cls, uid: str) -> Optional[Timer_Instance]:
        """Return the live Timer_Instance for a given uid, or None if not found."""
        _, timer, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.TIMERS, "timer_uid", uid
        )
        return timer

    @classmethod
    def request_timer_rebuild(cls, event) -> None:
        """
        Public API for dependent blocks to trigger a full timer rebuild.
        If timers are not currently enabled, enabling them fires the rebuild automatically
        via the scene property update callback.
        If already enabled, calls _rebuild_all_timers() directly.
        """
        logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
        timers_props = bpy.context.scene.dgblocks_timers_props
        if not timers_props.enable_timers:
            logger.debug("request_timer_rebuild: timers not enabled — enabling now (triggers rebuild)")
            timers_props.enable_timers = True
        else:
            logger.debug("request_timer_rebuild: timers already enabled — rebuilding directly")
            _rebuild_all_timers(event)

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
        logger.debug("Wrapper_Timer_Manager._init_wrapper")

        event = Enum_Sync_Events.ADDON_INIT
        if bpy.context.scene.dgblocks_timers_props.enable_timers:
            _rebuild_all_timers(event, sync_BL=False)
        else:
            _clear_all_timers()
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
        logger.debug("Wrapper_Timer_Manager._remove_wrapper — clearing all timers")
        _clear_all_timers()

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
        timers_props = bpy.context.scene.dgblocks_timers_props

        if event == Enum_Sync_Events.ADDON_INIT:
            return

        if not timers_props.enable_timers:
            _clear_all_timers()
            return

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS)
        data_source = timers_props.timer_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [a for a in actions if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}]
        logger.debug(
            f"BL: {len(data_source)} items | RTC: {len(data_target)} items | "
            f"{len(filtered_actions)} structural action(s)"
        )

        if len(filtered_actions) > 0:
            sync_BL = event in {
                Enum_Sync_Events.PROPERTY_UPDATE_REDO,
                Enum_Sync_Events.PROPERTY_UPDATE_UNDO,
                Enum_Sync_Events.PROPERTY_UPDATE,
            }
            _rebuild_all_timers(event, sync_BL)
            return

        # Edit-only path: toggle is_enabled on the affected RTC instances and
        # re-register / unregister the bpy timer accordingly.
        edit_actions = [a for a in actions if a.__class__ == data_sync_tools.Edit]
        for action in edit_actions:
            timer_instance = data_target[action.source_idx]
            new_enabled = not timer_instance.is_enabled
            timer_instance.is_enabled = new_enabled
            if new_enabled:
                _register_bpy_timer(timer_instance)
            else:
                _unregister_bpy_timer(timer_instance)

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.TIMER_LIFECYCLE)
        timers_props = bpy.context.scene.dgblocks_timers_props
        cached_timers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS)

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.TIMERS)
        data_source = timers_props.timer_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}
        ]

        if len(filtered_actions) > 0:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.TIMERS)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.TIMERS, True)
            try:
                # Clear & repopulate CollectionProperty
                timers_props.timer_mirror.clear()
                for timer_instance in cached_timers:
                    BL_timer = timers_props.timer_mirror.add()
                    BL_timer.timer_uid  = timer_instance.timer_uid
                    BL_timer.frequency  = timer_instance.frequency
                    BL_timer.is_enabled = timer_instance.is_enabled
            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.TIMERS, False)

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation

    @classmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        return shared_uilist_instance.scene_colprop_path


from typing import Optional
import bpy

# Addon-level imports
from ...addon_helpers.data_structures import (
    Abstract_BL_RTC_List_Syncronizer,
    Abstract_Feature_Wrapper,
    Abstract_Shared_UIList_Draw,
    Enum_Sync_Events,
)

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop
from ..block_core.core_features.loggers.feature_wrapper import get_logger

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .helpers import (
    _clear_all_listeners,
    _rebuild_all_listeners,
)

from .data_structures import RTC_Modal_Listener_Instance

# Aliases
cache_key_listeners = Block_RTC_Members.LISTENERS


class Wrapper_Modal_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def enable_and_poll_for_modal_listeners(cls):
        """Set enable_modal = True, which starts the router (it reads listeners live from RTC)."""
        bpy.context.scene.dgblocks_modal_events_props.enable_modal = True

    @classmethod
    def disable_modal(cls):
        """Set enable_modal = False; the router self-terminates on its next received event."""
        bpy.context.scene.dgblocks_modal_events_props.enable_modal = False

    @classmethod
    def get_listener(cls, src_block_id: str) -> Optional[RTC_Modal_Listener_Instance]:
        """Return the live RTC_Modal_Listener_Instance for a given block id, or None."""
        _, listener, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.LISTENERS, "src_block_id", src_block_id
        )
        return listener

    @classmethod
    def request_listener_rebuild(cls, event) -> None:
        """
        Public API for dependent blocks to trigger a re-poll of all modal listener definitions.
        Rebuilds the RTC listener registry (and BL mirror). Does not start/stop the router;
        the running router picks up the new listener set immediately on its next event.
        """
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        try:
            bpy.context.scene.dgblocks_modal_events_props
        except AttributeError:
            logger.warning("request_listener_rebuild: bpy.context.scene not available, skipping")
            return
        logger.debug("request_listener_rebuild: rebuilding listener registry")
        _rebuild_all_listeners(event)

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        logger.debug("Wrapper_Modal_Manager._init_wrapper")

        # A modal does not survive file load — the previous router (if any) is already dead.
        event = Enum_Sync_Events.ADDON_INIT

        # Always rebuild the listener registry so the UIList reflects subscribing blocks.
        _rebuild_all_listeners(event, sync_BL=False)

        # NOTE: the router operator is NOT started here. bpy.ops modal invocation needs a ready
        # window/area context, which is not guaranteed during init_post_bpy. The router is
        # (re)started from the hook_post_startup subscriber in __init__.py instead.
        return True


    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        logger.debug("Wrapper_Modal_Manager._remove_wrapper — clearing listeners")
        # The router (if running) self-terminates once enable_modal is gone / on unregister.
        _clear_all_listeners()

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        modal_props = bpy.context.scene.dgblocks_modal_events_props

        if event == Enum_Sync_Events.ADDON_INIT:
            return

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS)
        data_source = modal_props.listener_mirror

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
            _rebuild_all_listeners(event, sync_BL)
            return

        # Edit-only path: toggle is_enabled on the affected RTC instances. The running router
        # reads is_enabled live, so no restart is required.
        edit_actions = [a for a in actions if a.__class__ == data_sync_tools.Edit]
        for action in edit_actions:
            listener_instance = data_target[action.source_idx]
            listener_instance.is_enabled = not listener_instance.is_enabled

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):

        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        modal_props = bpy.context.scene.dgblocks_modal_events_props
        cached_listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS)

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS)
        data_source = modal_props.listener_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        filtered_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}
        ]

        if len(filtered_actions) > 0:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.LISTENERS)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.LISTENERS, True)
            try:
                # Clear & repopulate CollectionProperty
                modal_props.listener_mirror.clear()
                for listener_instance in cached_listeners:
                    BL_listener = modal_props.listener_mirror.add()
                    BL_listener.src_block_id = listener_instance.src_block_id
                    BL_listener.priority     = listener_instance.priority
                    BL_listener.is_enabled   = listener_instance.is_enabled
            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.LISTENERS, False)

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation

    @classmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        return shared_uilist_instance.scene_colprop_path

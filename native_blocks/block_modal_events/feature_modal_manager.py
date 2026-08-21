
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
    _rebuild_all_listeners,
    _sync_listener_mirror_from_RTC,
    end_all_listeners,
    start_router,
)

from .data_structures import Modal_Listener_End_Reason, RTC_Modal_Listener_Instance
from .workspace_tools import (
    activate_workspace_tool,
    get_registered_logical_tool_ids,
    refresh_workspace_tool_icons,
    unregister_all_workspace_tools,
)

# Aliases
cache_key_listeners = Block_RTC_Members.LISTENERS


class Wrapper_Modal_Manager(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def refresh_icons(cls) -> int:
        """Retry Image-backed workspace-tool icons and return the resolved count."""
        return refresh_workspace_tool_icons()

    @classmethod
    def activate_tool(cls, logical_tool_id: str, context=None) -> bool:
        """Activate a registered logical tool's placement for the current editor/mode."""
        context = context or bpy.context
        if activate_workspace_tool(logical_tool_id, context):
            return True

        # Calls reached from panels/timers may not carry a VIEW_3D WINDOW region. Reuse the
        # modal launcher's consistent override instead of duplicating context-search logic.
        from .helpers import _find_view3d_window_override
        override = _find_view3d_window_override()
        if override is None:
            return False
        with bpy.context.temp_override(**override):
            return activate_workspace_tool(logical_tool_id, bpy.context)

    @classmethod
    def get_listener(cls, src_block_id: str) -> Optional[RTC_Modal_Listener_Instance]:
        """Return the live RTC_Modal_Listener_Instance for a given block id, or None."""
        _, listener, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.LISTENERS, "src_block_id", src_block_id
        )
        return listener

    @classmethod
    def repoll(cls, event) -> None:
        """
        Public API for dependent blocks to trigger a re-poll of all modal listener definitions.
        Rebuilds the RTC listener registry. Tool-bound listeners use active-tool keymaps; the raw
        router starts only on a none -> some transition of unbound listeners.
        """
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        logger.debug("repoll: rebuilding listener registry")
        had_unbound_listeners, has_unbound_listeners = _rebuild_all_listeners(event)

        registered_tool_ids = get_registered_logical_tool_ids()
        for listener in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []:
            unknown_ids = set(listener.workspace_tool_ids) - registered_tool_ids
            if unknown_ids:
                listener.is_enabled = False
                listener.listener_error_str = (
                    "Unknown workspace tool id(s): " + ", ".join(sorted(unknown_ids))
                )
                logger.error(
                    f"Listener '{listener.src_block_id}' disabled: {listener.listener_error_str}"
                )
        _sync_listener_mirror_from_RTC()

        if has_unbound_listeners and not had_unbound_listeners:
            start_router()

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        logger.debug("Wrapper_Modal_Manager._init_wrapper")
        
        # Always rebuild the listener registry so the UIList reflects subscribing blocks.
        event = Enum_Sync_Events.ADDON_INIT
        _rebuild_all_listeners(event, sync_BL=False)
        return True


    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        logger.debug("Wrapper_Modal_Manager._remove_wrapper — clearing listeners")
        end_all_listeners(Modal_Listener_End_Reason.ADDON_SHUTDOWN)
        unregister_all_workspace_tools()

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

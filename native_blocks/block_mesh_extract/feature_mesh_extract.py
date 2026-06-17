
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
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.runtime_cache import data_sync_tools
from ..block_core.core_features.runtime_cache.data_sync_tools import plan_dataclasses_to_match_collectionprop

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import RTC_Mesh_Extract_Instance
from .helpers import run_mesh_extract


class Wrapper_Mesh_Extract(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Shared_UIList_Draw):
    """
    Feature Wrapper for block_mesh_extract.

    Manages the lifecycle of RTC_Mesh_Extract_Instance objects.
    Extraction is triggered by:
        - Calling Wrapper_Mesh_Extract.run_extract() from any downstream block.
        - Setting bpy.context.scene.dgblocks_mesh_extract_props.run_mesh_extract = True
          (auto-resets to False after triggering).

    After extraction completes, hook_mesh_extract_ready is fired with the list of
    processed object names.
    """

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def run_extract(cls) -> list[str]:
        """
        Trigger a full mesh extraction cycle from any downstream block.
        Returns the list of object names that were processed.
        Raises ValueError if MET validation fails.
        """
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Wrapper_Mesh_Extract.run_extract: triggered via public API")
        return run_mesh_extract()

    @classmethod
    def get_instance(cls, object_name: str) -> Optional[RTC_Mesh_Extract_Instance]:
        """
        Return the live RTC_Mesh_Extract_Instance for a given object name, or None.
        Only returns the instance if is_valid is True.
        To access invalid instances, use get_instance_raw().
        """
        _, instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.MESH_EXTRACT_INSTANCES, "object_name", object_name
        )
        if instance is not None and instance.is_valid:
            return instance
        return None

    @classmethod
    def get_instance_raw(cls, object_name: str) -> Optional[RTC_Mesh_Extract_Instance]:
        """
        Return the RTC_Mesh_Extract_Instance for a given object name regardless of is_valid.
        Returns None if not found.
        """
        _, instance, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            Block_RTC_Members.MESH_EXTRACT_INSTANCES, "object_name", object_name
        )
        return instance

    @classmethod
    def get_all_instances(cls) -> list[RTC_Mesh_Extract_Instance]:
        """Return all live RTC_Mesh_Extract_Instance objects (valid and invalid)."""
        return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Wrapper_Mesh_Extract._init_wrapper")
        # No active initialization needed — extraction is demand-driven.
        # RTC list starts empty; instances are created on first run_extract() call.
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
        logger.debug("Wrapper_Mesh_Extract._remove_wrapper — clearing all instances")
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, [])

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Called on undo/redo/reload. The extract_mirror CollectionProperty holds only
        object_name (key) and is_valid (data) — it does not store numpy arrays.
        On structural change (object added/removed from mirror), we simply clear the
        RTC list. The user must re-trigger extraction if they want fresh data.
        On edit-only changes (is_valid toggled — unusual but possible), no action needed.
        """
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)

        try:
            mesh_extract_props = bpy.context.scene.dgblocks_mesh_extract_props
        except AttributeError:
            logger.warning("_update_RTC_with_mirrored_BL_data: bpy.context.scene not available")
            return

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
        data_source = mesh_extract_props.extract_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        structural_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove}
        ]

        if structural_actions:
            logger.debug(
                f"_update_RTC_with_mirrored_BL_data: structural change detected "
                f"({len(structural_actions)} action(s)) — clearing RTC instances."
            )
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, [])

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        """
        Push current RTC instance list to the BL extract_mirror CollectionProperty.
        Called after run_mesh_extract() and on undo/redo.
        """
        logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)

        try:
            mesh_extract_props = bpy.context.scene.dgblocks_mesh_extract_props
        except AttributeError:
            logger.warning("_update_BL_with_mirrored_RTC_data: bpy.context.scene not available")
            return

        cached_instances = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)

        key_fields  = data_mirror_instance.mirrored_key_field_names
        data_fields = data_mirror_instance.mirrored_data_field_names
        data_target = cached_instances
        data_source = mesh_extract_props.extract_mirror

        actions = plan_dataclasses_to_match_collectionprop(data_source, data_target, key_fields, data_fields)
        structural_actions = [
            a for a in actions
            if a.__class__ in {data_sync_tools.Create, data_sync_tools.Remove, data_sync_tools.Move}
        ]

        if structural_actions:
            Wrapper_Runtime_Cache.assert_cache_is_not_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES, True)
            try:
                mesh_extract_props.extract_mirror.clear()
                for inst in cached_instances:
                    row = mesh_extract_props.extract_mirror.add()
                    row.object_name = inst.object_name
                    row.is_valid    = inst.is_valid
            finally:
                Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.MESH_EXTRACT_INSTANCES, False)

            logger.debug(
                f"_update_BL_with_mirrored_RTC_data: synced {len(cached_instances)} row(s)"
            )

    # ----------------------------------------------------------
    # Abstract_Shared_UIList_Draw implementation

    @classmethod
    def shared_uilist_get_data_path(cls, shared_uilist_instance) -> str:
        return shared_uilist_instance.scene_colprop_path

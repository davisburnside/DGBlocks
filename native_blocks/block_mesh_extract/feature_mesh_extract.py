
from typing import Optional

import bpy

from ...addon_helpers.data_structures import Abstract_Feature_Wrapper

from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import Numpy_Mesh_Action_Declaration, RTC_Mesh_Extract_Instance
from .helpers_actions import (
    clear_stored_instances,
    get_stored_instance,
    get_stored_instances,
    run_mesh_action,
)
from .helpers_diff import diff_instances as _diff_instances


class Wrapper_Mesh_Extract(Abstract_Feature_Wrapper):
    """
    Feature Wrapper for block_mesh_extract.

    Fully demand-driven — nothing runs unless a caller asks for it:

        instance = Wrapper_Mesh_Extract.run_mesh_action_for_object(object, declaration)

    Storage is decided per declaration via `should_cache_in_RTC`:
        True  → the instance is kept in the RTC under (object_name, slot) and shows up
                in the debug panel. Repeat calls accumulate data and action history.
        False → the instance is returned to the caller and never stored anywhere.

    Instances hold numpy arrays only and are never mirrored to Blender data.
    """

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def run_mesh_action_for_object(
        cls,
        object:            bpy.types.Object,
        declaration:       Numpy_Mesh_Action_Declaration,
        depsgraph:         Optional[bpy.types.Depsgraph] = None,
        existing_instance: Optional[RTC_Mesh_Extract_Instance] = None,
    ) -> RTC_Mesh_Extract_Instance:
        """
        Run one declaration (READ → CALLBACKS → WRITE) against one object.

        Always returns an instance — check `instance.last_action.is_valid` for the
        outcome of this call, or `instance.is_valid` for the most recent action.
        Never raises for mesh/attribute problems; failures land in the action record.

        Pass `existing_instance` to chain passes onto a caller-owned instance without
        going through RTC lookup (e.g. an ephemeral pass-1 → pass-2 sequence).
        """
        return run_mesh_action(object, declaration, depsgraph, existing_instance)

    @classmethod
    def get_instance(
        cls,
        object_name: str,
        slot:        str = "default",
        require_valid: bool = True,
    ) -> Optional[RTC_Mesh_Extract_Instance]:
        """Return the stored instance for (object_name, slot), or None."""
        instance = get_stored_instance(object_name, slot)
        if instance is None:
            return None
        if require_valid and not instance.is_valid:
            return None
        return instance

    @classmethod
    def get_all_instances(cls) -> list:
        """All stored instances (valid and invalid), newest action last."""
        return get_stored_instances()

    @classmethod
    def clear_instances(cls, object_name: Optional[str] = None) -> int:
        """Drop stored instances for one object, or all of them. Returns count removed."""
        return clear_stored_instances(object_name)

    @classmethod
    def diff_instances(cls, old, new) -> tuple[list, list, list]:
        """
        Compare two instances and return (added, removed, edited) key lists.
        Keys look like "vertex.co", "face.custom['planar_groups']", "derived['csr']".
        All three empty means the data is identical.

        NOTE: an RTC-cached declaration mutates its stored instance in place, so a
        before/after diff requires either should_cache_in_RTC=False or a caller-held
        snapshot of the previous instance.
        """
        return _diff_instances(old, new)

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE).debug(
            "Wrapper_Mesh_Extract._init_wrapper — demand-driven, nothing to initialize"
        )
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE).debug(
            "Wrapper_Mesh_Extract._remove_wrapper — clearing all instances"
        )
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, [])
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_ACTION_UID_COUNTER, 0)

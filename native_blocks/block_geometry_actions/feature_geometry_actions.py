
from typing import Optional

import bpy

from ...addon_helpers.data_structures import Abstract_Feature_Wrapper

from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Geometry_Actions_Declaration,
    Geometry_Actions_Result_Instance,
)
from .helpers_actions import (
    clear_results,
    get_all_stacks,
    get_result,
    get_stack,
    run_geometry_action,
)
from .helpers_diff import _diff_instances
from .helpers_serialize import (
    DERIVED_KEY_SERIALIZED,
    apply_serialized_geometry,
    deserialize_to_payload,
    serialize_geometry,
)


class Wrapper_Geometry_Actions(Abstract_Feature_Wrapper):
    """
    Feature Wrapper for block_geometry_actions.

    Fully demand-driven — nothing runs unless a caller asks for it:

        result = Wrapper_Geometry_Actions.run_geometry_action_for_object(object, declaration)

    Every run produces a NEW result instance, pushed onto the stack for
    (declaration.declaration_id, object.name). The stack depth is the declaration's
    `retention_count` (1 = latest only, 0 = don't store, N = keep N for diffs).

    Results hold numpy arrays only and are never mirrored to Blender data.
    """

    # ----------------------------------------------------------
    # Running actions

    @classmethod
    def run_geometry_action_for_object(
        cls,
        object:            bpy.types.Object,
        declaration:       Geometry_Actions_Declaration,
        depsgraph:         Optional[bpy.types.Depsgraph] = None,
        existing_instance: Optional[Geometry_Actions_Result_Instance] = None,
    ) -> Geometry_Actions_Result_Instance:
        """
        Run one declaration (reads → callbacks) against one object.

        Always returns a result — check `result.last_action.is_valid` for the outcome of
        this call, or `result.is_valid` for the most recent action. Never raises for
        geometry/attribute problems; failures land in the action record.

        Pass `existing_instance` to chain a second pass onto a caller-owned result rather
        than starting a fresh one.
        """
        return run_geometry_action(object, declaration, depsgraph, existing_instance)

    @classmethod
    def run_geometry_actions_for_object(
        cls,
        object:      bpy.types.Object,
        declarations,
        depsgraph:   Optional[bpy.types.Depsgraph] = None,
    ) -> Optional[Geometry_Actions_Result_Instance]:
        """
        Run several declarations in order against one chained result instance. Stops at the
        first failure and returns the result as it stands.
        """
        instance = None
        for declaration in declarations or ():
            instance = run_geometry_action(object, declaration, depsgraph, instance)
            if not instance.is_valid:
                break
        return instance

    # ----------------------------------------------------------
    # Reading stored results

    @classmethod
    def get_result(
        cls,
        declaration_id:     str,
        object_name:        str,
        offset_from_latest: int = 0,
        require_valid:      bool = True,
    ) -> Optional[Geometry_Actions_Result_Instance]:
        """
        Fetch a stored result. offset_from_latest=0 is the newest, 1 the previous one, etc.
        Returns None when absent (or invalid, when require_valid).
        """
        instance = get_result(declaration_id, object_name, offset_from_latest)
        if instance is None:
            return None
        if require_valid and not instance.is_valid:
            return None
        return instance

    @classmethod
    def get_result_stack(cls, declaration_id: str, object_name: str) -> list:
        """Every retained result for this (declaration_id, object_name), oldest first."""
        return get_stack(declaration_id, object_name)

    @classmethod
    def get_all_results(cls) -> list:
        """Flat list of every retained result across all stacks."""
        return [
            instance
            for stack in get_all_stacks().values()
            for instance in stack
        ]

    @classmethod
    def clear_results(
        cls,
        declaration_id: Optional[str] = None,
        object_name:    Optional[str] = None,
    ) -> int:
        """Drop stored results by declaration, by object, by both, or all. Returns count."""
        return clear_results(declaration_id, object_name)

    @classmethod
    def diff_results(cls, old, new) -> tuple[list, list, list]:
        """
        Compare two results and return (added, removed, edited) key lists.
        Keys look like "vertex.co", "face.custom['planar_groups']", "derived['csr']".
        All three empty means the data is identical.

        With `retention_count >= 2`, `get_result(id, name, 1)` and `get_result(id, name, 0)`
        are always a valid before/after pair.
        """
        return _diff_instances(old, new)

    # ----------------------------------------------------------
    # Serialization (socket transport helpers)

    @classmethod
    def serialize_object_geometry(cls, object: bpy.types.Object) -> str:
        """
        Serialize an object's own datablock to a transport string, outside the step-list
        flow. Raises for unsupported geometry or attribute types.
        """
        from .helpers_read import ensure_curves_datablock, CURVE_OBJECT_TYPES
        from .data_structures import Enum_Geometry_Type

        if object is None:
            raise RuntimeError("Object is None.")
        if object.type in CURVE_OBJECT_TYPES:
            data, error_str = ensure_curves_datablock(object)
            if error_str:
                raise RuntimeError(error_str)
            return serialize_geometry(data, Enum_Geometry_Type.CURVES)
        if object.type != "MESH":
            raise RuntimeError(f"Cannot serialize object type {object.type!r}.")
        return serialize_geometry(object.data, Enum_Geometry_Type.MESH)

    @classmethod
    def apply_serialized_geometry_to_object(
        cls, object: bpy.types.Object, serialized: str
    ) -> str:
        """
        Replace an object's geometry from a transport string, outside the step-list flow.
        Object Mode only. Raises for malformed / mismatched payloads.
        """
        from .helpers_read import ensure_curves_datablock, CURVE_OBJECT_TYPES
        from .data_structures import Enum_Geometry_Type

        if object is None:
            raise RuntimeError("Object is None.")
        if object.mode != "OBJECT":
            raise RuntimeError(f"Deserialization requires Object Mode (mode={object.mode}).")
        if object.type in CURVE_OBJECT_TYPES:
            data, error_str = ensure_curves_datablock(object)
            if error_str:
                raise RuntimeError(error_str)
            return apply_serialized_geometry(data, serialized, Enum_Geometry_Type.CURVES)
        if object.type != "MESH":
            raise RuntimeError(f"Cannot deserialize into object type {object.type!r}.")
        return apply_serialized_geometry(object.data, serialized, Enum_Geometry_Type.MESH)

    @classmethod
    def inspect_serialized_geometry(cls, serialized: str) -> dict:
        """Decode only the header of a transport string (counts, attribute inventory)."""
        header, _arrays = deserialize_to_payload(serialized)
        return header

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        get_logger(Block_Loggers.GEOMETRY_ACTIONS_LIFECYCLE).debug(
            "Wrapper_Geometry_Actions._init_wrapper — demand-driven, nothing to initialize"
        )
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        get_logger(Block_Loggers.GEOMETRY_ACTIONS_LIFECYCLE).debug(
            "Wrapper_Geometry_Actions._remove_wrapper — clearing all result stacks"
        )
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_STACKS, {})
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_UID_COUNTER, 0)

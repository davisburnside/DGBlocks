
from typing import Optional

import bpy

from ...addon_helpers.data_structures import Abstract_Feature_Wrapper

from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Enum_Geometry_Target,
    Enum_Read_Source,
    Geometry_Actions_Declaration,
    Geometry_Actions_Result_Instance,
)
from .helpers_actions import (
    clear_results,
    get_all_results,
    get_result,
    run_geometry_action,
)
from .helpers_diff import _diff_instances
from .helpers_read import Geometry_Handle, acquire_geometry_for_read, release_geometry_handle
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

    Every run produces a new result instance and replaces the stored latest result for
    (declaration.declaration_id, object). Optional grouping IDs pre-populate data from the
    latest grouped run on that same object.

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
        geometry_handle:   Optional[Geometry_Handle] = None,
    ) -> Geometry_Actions_Result_Instance:
        """
        Run one declaration (reads → callbacks) against one object.

        Always returns a result — check `result.last_action.is_valid` for the outcome of
        this call, or `result.is_valid` for the most recent action. Never raises for
        geometry/attribute problems; failures land in the action record.

        A declaration with a grouping ID inherits a deep copy of data from the latest run
        in that group on the same object. Its reads replace inherited attribute slots.

        geometry_handle: share an already-acquired handle (see acquire_geometry_handle)
        instead of letting this call do its own acquire/release. For EVALUATED reads that
        skips `to_mesh()` — use this when several declarations are known to run back-to-back
        against the same object at the same depsgraph state with nothing in between that
        could change the result, so they don't each pay for their own mesh snapshot.
        """
        return run_geometry_action(object, declaration, depsgraph, geometry_handle=geometry_handle)

    @classmethod
    def acquire_geometry_handle(
        cls,
        object:          bpy.types.Object,
        depsgraph:       Optional[bpy.types.Depsgraph] = None,
        read_source:     str = Enum_Read_Source.EVALUATED,
        geometry_target: str = Enum_Geometry_Target.AUTO,
    ) -> Geometry_Handle:
        """
        Acquire geometry once, to share across several run_geometry_action_for_object calls
        via their geometry_handle= parameter. Always release with release_geometry_handle(),
        even when handle.is_valid is False (release is a no-op for non-temporary handles, but
        the caller shouldn't have to know which case it acquired).
        """
        return acquire_geometry_for_read(object, depsgraph, str(read_source), str(geometry_target))

    @classmethod
    def release_geometry_handle(cls, handle: Geometry_Handle) -> None:
        """Release a handle acquired via acquire_geometry_handle()."""
        release_geometry_handle(handle)

    @classmethod
    def run_geometry_actions_for_object(
        cls,
        object:      bpy.types.Object,
        declarations,
        depsgraph:   Optional[bpy.types.Depsgraph] = None,
    ) -> Optional[Geometry_Actions_Result_Instance]:
        """
        Run several declarations in order. Grouped declarations share data through storage.
        Stops at the first failure and returns the latest result.
        """
        instance = None
        for declaration in declarations or ():
            instance = run_geometry_action(object, declaration, depsgraph)
            if not instance.is_valid:
                break
        return instance

    # ----------------------------------------------------------
    # Reading stored results

    @classmethod
    def get_result(
        cls,
        declaration_id: str,
        object_name:    str,
        require_valid:  bool = True,
    ) -> Optional[Geometry_Actions_Result_Instance]:
        """
        Fetch the latest stored result. Returns None when absent (or invalid, when required).
        """
        instance = get_result(declaration_id, object_name)
        if instance is None:
            return None
        if require_valid and not instance.is_valid:
            return None
        return instance

    @classmethod
    def get_all_results(cls) -> list:
        """Every latest stored result."""
        return list(get_all_results().values())

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

        Retain the earlier returned instance in caller-owned state for before/after diffs.
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
            "Wrapper_Geometry_Actions._remove_wrapper — clearing all results"
        )
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_RESULTS, {})
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_UID_COUNTER, 0)

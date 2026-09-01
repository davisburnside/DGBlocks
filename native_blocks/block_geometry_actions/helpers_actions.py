"""
helpers_actions.py — step-list orchestration + latest-result RTC storage.

One call = one Action_Record + one NEW result instance stored for (declaration_id, object).
Steps run in the order given. A failure records the action
as invalid and keeps whatever data the reads managed to gather before failing.

Geometry acquisition happens ONCE per action for the whole step list — minimizing depsgraph
evaluations and mesh creations. The Geometry_Context is bound to that one acquisition and
finalized after each Callback_Step.
"""

import time
from copy import deepcopy
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from pprint import pformat
from typing import Optional

import bpy
import numpy as np

from ...addon_helpers.generic_tools import get_exception_last_n_lines
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Action_Op_Record,
    Action_Record,
    Enum_Geometry_Type,
    Enum_Inherit_Mode,
    Enum_Op_Type,
    Enum_Step_Kind,
    Geometry_Actions_Declaration,
    Geometry_Actions_Result_Instance,
    get_step_kind,
)
from .helpers_read import (
    Geometry_Handle,
    acquire_geometry_for_read,
    all_domain_counts,
    read_attr,
    release_geometry_handle,
    resolve_attr,
)
from .helpers_write import Geometry_Context, warn_write_hazards

# ==============================================================================================================================
# RTC RESULTS
# ==============================================================================================================================

def result_key(declaration_id: str, object_session_uid: int) -> str:
    return f"{declaration_id}|{int(object_session_uid)}"


def get_all_results() -> dict:
    return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.GEOMETRY_ACTION_RESULTS) or {}


def _set_all_results(results: dict) -> None:
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_RESULTS, results)


def get_result(declaration_id: str, object_name: str):
    """Fetch the latest stored result for a declaration and displayed object name."""
    matches = [
        result for result in get_all_results().values()
        if result.declaration_id == declaration_id and result.object_name == object_name
    ]
    return max(matches, key=lambda result: result.timestamp_last_action) if matches else None


def get_result_by_key(storage_key: str):
    """Fetch one exact stored action/object result."""
    return get_all_results().get(storage_key)


def store_result(instance: Geometry_Actions_Result_Instance) -> None:
    """Store the latest run, replacing the same declaration/object identity."""
    results = get_all_results()
    results[instance.storage_key] = instance
    _set_all_results(results)


def _latest_group_result(grouping_id: Optional[str], object_session_uid: int, read_source: str):
    """The most recent stored result sharing (grouping_id, object, read_source).

    read_source is part of the identity, not just a filter of convenience: EVALUATED and
    ORIGINAL data live in different index spaces (see Enum_Read_Source), so inheriting
    across a read_source mismatch would hand one declaration data indexed for a completely
    different mesh snapshot. A result with no recorded action (nothing ever stored via
    store_result) cannot be compared and is skipped rather than crashing on `last_action`.
    """
    if not grouping_id:
        return None
    matches = [
        result for result in get_all_results().values()
        if result.grouping_id == grouping_id
        and result.object_session_uid == object_session_uid
        and result.last_action is not None
        and result.last_action.read_source == str(read_source)
    ]
    return max(matches, key=lambda result: result.timestamp_last_action) if matches else None


def _reference_clone(
    inherited: Geometry_Actions_Result_Instance,
    declaration_id: str,
    object_name: str,
    grouping_id: Optional[str],
    timestamp_start: float,
) -> Geometry_Actions_Result_Instance:
    """Cheap alternative to `deepcopy(inherited)` for Enum_Inherit_Mode.REFERENCE.

    Gives the new instance its own identity (declaration_id, actions, timestamps) and its
    own per-domain `.custom` dicts / `derived` dict, so this run's bookkeeping can never
    leak into the stored result it started from and vice versa. Everything INSIDE those
    containers -- arrays, entity objects -- is shared by reference, not copied: O(key
    count) instead of O(data size). Safe only if every caller that builds on inherited data
    replaces dict/array slots wholesale rather than mutating them in place (see
    Enum_Inherit_Mode.REFERENCE's docstring).
    """
    return replace(
        inherited,
        declaration_id=declaration_id,
        object_name=object_name,
        grouping_id=grouping_id,
        timestamp_start=timestamp_start,
        timestamp_end=0.0,
        actions=[],
        is_valid=False,
        error_str=None,
        vertex=replace(inherited.vertex, custom=dict(inherited.vertex.custom)),
        edge=replace(inherited.edge, custom=dict(inherited.edge.custom)),
        face=replace(inherited.face, custom=dict(inherited.face.custom)),
        corner=replace(inherited.corner, custom=dict(inherited.corner.custom)),
        point=replace(inherited.point, custom=dict(inherited.point.custom)),
        curve=replace(inherited.curve, custom=dict(inherited.curve.custom)),
        derived=dict(inherited.derived),
    )


def clear_results(declaration_id: Optional[str] = None, object_name: Optional[str] = None) -> int:
    """
    Drop stored results. Both args None clears everything. Returns results removed.
    """
    results = get_all_results()
    if declaration_id is None and object_name is None:
        removed = len(results)
        _set_all_results({})
        return removed

    def _matches(result) -> bool:
        if declaration_id is not None and result.declaration_id != declaration_id:
            return False
        if object_name is not None and result.object_name != object_name:
            return False
        return True

    keys = [key for key, result in results.items() if _matches(result)]
    for k in keys:
        del results[k]
    _set_all_results(results)
    return len(keys)


def next_action_uid() -> int:
    current = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.GEOMETRY_ACTION_UID_COUNTER) or 0
    nxt = int(current) + 1
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.GEOMETRY_ACTION_UID_COUNTER, nxt)
    return nxt


# ==============================================================================================================================
# HELPERS
# ==============================================================================================================================

def _shape_str(value) -> str:
    shape = getattr(value, "shape", None)
    if shape is not None:
        return str(tuple(shape))
    if isinstance(value, tuple) and value and hasattr(value[0], "shape"):
        return " + ".join(str(tuple(v.shape)) for v in value if hasattr(v, "shape"))
    if isinstance(value, (dict, list)):
        return f"len {len(value)}"
    if isinstance(value, str):
        return f"str {len(value)}"
    return "-"


def _read_data_type_str(attr) -> str:
    """Return a concise display type from resolved declaration metadata."""
    blender_type = str(attr.data_type) if attr.data_type else ""
    blender_type_labels = {
        "FLOAT": "FLOAT",
        "INT": "INT",
        "INT8": "INT",
        "BOOLEAN": "BOOL",
        "FLOAT_VECTOR": "VEC3",
        "FLOAT2": "VEC2",
        "FLOAT_COLOR": "COLOR4",
        "BYTE_COLOR": "COLOR4",
        "INT32_2D": "IVEC2",
        "QUATERNION": "QUATERNION",
    }
    if blender_type in blender_type_labels:
        return blender_type_labels[blender_type]

    dtype = str(attr.dtype or "").lower()
    components = int(attr.components or 1)
    if dtype.startswith("float"):
        return "FLOAT" if components == 1 else f"VEC{components}"
    if dtype.startswith("int") or dtype.startswith("uint"):
        return "INT" if components == 1 else f"IVEC{components}"
    if dtype in {"bool", "boolean"}:
        return "BOOL" if components == 1 else f"BVEC{components}"
    if dtype.startswith("str") or dtype.startswith("unicode"):
        return "STRING"
    return dtype.upper() or "-"


def _exception_location(exc: BaseException) -> tuple[Optional[str], Optional[int]]:
    """Return the filename and line where the exception was raised."""
    traceback_node = exc.__traceback__
    if traceback_node is None:
        return None, None
    while traceback_node.tb_next is not None:
        traceback_node = traceback_node.tb_next
    return Path(traceback_node.tb_frame.f_code.co_filename).name, traceback_node.tb_lineno


def _clipboard_value(value):
    """Convert nested result payload data into full, non-truncated Python containers."""
    if isinstance(value, np.ndarray):
        return {
            "dtype": str(value.dtype),
            "shape": tuple(value.shape),
            "values": value.tolist(),
        }
    if is_dataclass(value):
        return {field.name: _clipboard_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        converted = {}
        for key, item in value.items():
            converted_key = _clipboard_value(key)
            try:
                hash(converted_key)
            except TypeError:
                converted_key = pformat(converted_key, sort_dicts=False, width=120)
            converted[converted_key] = _clipboard_value(item)
        return converted
    if isinstance(value, (list, tuple, set)):
        return [_clipboard_value(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def result_payload_to_string(instance: Geometry_Actions_Result_Instance) -> str:
    """Return the complete geometry/derived staging payload as a readable Python string."""
    payload = {
        "declaration_id": instance.declaration_id,
        "grouping_id": instance.grouping_id,
        "object_name": instance.object_name,
        "object_session_uid": instance.object_session_uid,
        "geometry_type": instance.geometry_type,
        "vertex": _clipboard_value(instance.vertex),
        "edge": _clipboard_value(instance.edge),
        "face": _clipboard_value(instance.face),
        "corner": _clipboard_value(instance.corner),
        "point": _clipboard_value(instance.point),
        "curve": _clipboard_value(instance.curve),
        "derived": _clipboard_value(instance.derived),
    }
    return pformat(payload, sort_dicts=False, width=120)


def _apply_domain_counts(instance: Geometry_Actions_Result_Instance, counts: dict) -> None:
    for domain_name, count in counts.items():
        instance.domain(domain_name).count = count


def _invalidate_per_element_slots(instance: Geometry_Actions_Result_Instance) -> None:
    """Null out all per-element data after a topology change (index space is stale)."""
    for domain_name in instance.domain_names:
        domain_obj = getattr(instance, domain_name)
        for field_name in domain_obj.builtin_field_names():
            setattr(domain_obj, field_name, None)
        domain_obj.custom.clear()


# ==============================================================================================================================
# MAIN ENTRY POINT
# ==============================================================================================================================

def run_geometry_action(
    object:            bpy.types.Object,
    declaration:       Geometry_Actions_Declaration,
    depsgraph:         Optional[bpy.types.Depsgraph] = None,
    geometry_handle:   Optional[Geometry_Handle] = None,
) -> Geometry_Actions_Result_Instance:
    """
    Run one declaration's step list against one object. Always returns the result instance,
    valid or not; inspect instance.last_action for the outcome of this specific call.

    geometry_handle: pass an already-acquired handle (see acquire_geometry_for_read) to
    skip this call's own acquire/release entirely and read that handle's data instead.
    For an EVALUATED read this bypasses `to_mesh()` — the single most expensive call in the
    whole framework — so it exists for callers that already know several declarations will
    run back-to-back against the same object at the same depsgraph state with nothing in
    between that could change the result (e.g. a read-only canary step immediately followed
    by the compute step it gates). The caller owns the handle's lifetime in that case: this
    function will neither acquire nor release it.
    """
    logger = get_logger(Block_Loggers.GEOMETRY_ACTIONS_EVENTS)
    total_start = time.perf_counter()
    object_name = getattr(object, "name", "<None>")
    object_mode = getattr(object, "mode", "OBJECT")
    object_session_uid = getattr(object, "session_uid", 0)

    action = Action_Record(
        action_uid      = next_action_uid(),
        declaration_id  = declaration.declaration_id,
        label           = declaration.label,
        object_name     = object_name,
        timestamp_start = time.time(),
        grouping_id     = declaration.grouping_id,
        read_source     = str(declaration.read_source),
        geometry_target = str(declaration.geometry_target),
        object_mode     = str(object_mode),
    )

    inherited = _latest_group_result(
        declaration.grouping_id, object_session_uid, str(declaration.read_source),
    )
    if inherited is None:
        instance = Geometry_Actions_Result_Instance(
            declaration_id  = declaration.declaration_id,
            object_name     = object_name,
            grouping_id     = declaration.grouping_id,
            timestamp_start = action.timestamp_start,
        )
    elif str(declaration.inherit_mode) == Enum_Inherit_Mode.REFERENCE:
        instance = _reference_clone(
            inherited, declaration.declaration_id, object_name,
            declaration.grouping_id, action.timestamp_start,
        )
    else:
        instance = deepcopy(inherited)
        instance.declaration_id = declaration.declaration_id
        instance.object_name = object_name
        instance.grouping_id = declaration.grouping_id
        instance.timestamp_start = action.timestamp_start
        instance.timestamp_end = 0.0
        instance.actions.clear()
        instance.is_valid = False
        instance.error_str = None
    instance.object_session_uid = object_session_uid

    def _finish(error_str: Optional[str] = None) -> Geometry_Actions_Result_Instance:
        action.duration_ms = (time.perf_counter() - total_start) * 1000.0
        action.error_str   = error_str
        action.is_valid    = error_str is None and all(op.is_valid for op in action.ops)
        instance.timestamp_end = time.time()
        instance.append_action(action)
        store_result(instance)
        return instance

    # ---- Acquire the geometry ONCE for the whole step list -----------------------
    # (unless the caller already acquired one for us to share -- see geometry_handle above)
    owns_handle = geometry_handle is None
    handle = geometry_handle if geometry_handle is not None else acquire_geometry_for_read(
        object, depsgraph, str(declaration.read_source), str(declaration.geometry_target)
    )
    action.geometry_target = str(handle.geometry_target)
    action.geometry_type   = str(handle.geometry_type)
    instance.geometry_type = str(handle.geometry_type)
    if not handle.is_valid:
        action.ops.append(Action_Op_Record(
            op_type=Enum_Op_Type.SETUP, label="setup (inherit + acquire)", is_valid=False,
            duration_ms=(time.perf_counter() - total_start) * 1000.0,
            error_str=handle.error_str,
        ))
        return _finish(handle.error_str)

    data = handle.data
    geometry_type = str(handle.geometry_type)
    geometry_context: Optional[Geometry_Context] = None

    try:
        counts = all_domain_counts(data, geometry_type)
        action.domain_counts = counts
        _apply_domain_counts(instance, counts)

        # Surface non-fatal write hazards as a synthetic op (only if there are callbacks)
        if declaration.has_callbacks:
            for warning in warn_write_hazards(object):
                action.ops.append(Action_Op_Record(
                    op_type=Enum_Op_Type.CALLBACK, label="hazard", error_str=warning,
                ))

        # Everything above this point -- inherit lookup, clone/deepcopy, geometry acquire
        # (when this call owns it), domain counts, hazard scan -- has no per-item Action_Op
        # of its own, so it used to vanish into the gap between the header total and the
        # sum of listed rows. Recorded as one op, inserted first, so the panel actually
        # sums to the header duration and this cost is directly comparable across runs
        # (e.g. to confirm inherit_mode=REFERENCE actually cut it, not just guessed at).
        action.ops.insert(0, Action_Op_Record(
            op_type=Enum_Op_Type.SETUP, label="setup (inherit + acquire + counts)",
            duration_ms=(time.perf_counter() - total_start) * 1000.0,
        ))

        # ---- RUN THE STEP LIST ------------------------------------------------
        for step in declaration.steps or ():
            step_kind = get_step_kind(step)

            # ---- Read_Step ----------------------------------------------------
            if step_kind == Enum_Step_Kind.READ:
                t0 = time.perf_counter()
                attr = step.attr
                resolved, resolve_error = resolve_attr(data, attr, geometry_type)
                if resolve_error or resolved is None:
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.READ, label=attr.key, is_valid=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        error_str=resolve_error or f"could not resolve '{attr.key}'",
                    ))
                    continue
                try:
                    arr = read_attr(data, resolved, geometry_type)
                    if arr is not None:
                        instance.set_attr_value(resolved, arr)
                    action.ops.append(Action_Op_Record(
                        op_type     = Enum_Op_Type.READ,
                        label       = resolved.key,
                        duration_ms = (time.perf_counter() - t0) * 1000.0,
                        shape       = _shape_str(arr),
                        data_type   = _read_data_type_str(resolved),
                    ))
                except Exception as e:
                    error_file, error_line = _exception_location(e)
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.READ, label=attr.key, is_valid=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        error_str=get_exception_last_n_lines(3, e),
                        error_file=error_file, error_line=error_line,
                    ))
                continue

            # ---- Callback_Step ------------------------------------------------
            if step_kind == Enum_Step_Kind.CALLBACK:
                t0 = time.perf_counter()
                counts_before = all_domain_counts(data, geometry_type)

                if geometry_context is None:
                    geometry_context = Geometry_Context(
                        object, data, geometry_type, is_edit_mode=(object_mode == "EDIT"),
                    )

                try:
                    step.func(instance, action, geometry_context)
                except Exception as e:
                    error_file, error_line = _exception_location(e)
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=get_exception_last_n_lines(3, e),
                        error_file=error_file, error_line=error_line,
                    ))
                    logger.error(
                        f"callback '{step.resolved_label}' failed on '{object_name}'",
                        exc_info=True,
                    )
                    try:
                        geometry_context.finalize()
                    except Exception:
                        pass
                    return _finish(f"Callback '{step.resolved_label}' raised.")

                try:
                    geometry_context.finalize()
                except Exception as e:
                    error_file, error_line = _exception_location(e)
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=f"finalize failed: {get_exception_last_n_lines(3, e)}",
                        error_file=error_file, error_line=error_line,
                    ))
                    return _finish(f"Callback '{step.resolved_label}' finalize raised.")

                # Topology change is observed, not validated.
                counts_after = all_domain_counts(data, geometry_type)
                if counts_before != counts_after:
                    instance.topology_generation += 1
                    _invalidate_per_element_slots(instance)
                    _apply_domain_counts(instance, counts_after)
                    action.domain_counts = counts_after

                action.ops.append(Action_Op_Record(
                    op_type     = Enum_Op_Type.CALLBACK,
                    label       = step.resolved_label,
                    duration_ms = (time.perf_counter() - t0) * 1000.0,
                ))
                continue

            # ---- Unknown step type — fail gracefully ---------------------------
            action.ops.append(Action_Op_Record(
                op_type=Enum_Op_Type.CALLBACK, label=str(step), is_valid=False,
                error_str=f"Unknown step type: {type(step).__name__}",
            ))
            return _finish(f"Unknown step type: {type(step).__name__}")

    except Exception as e:
        logger.error(f"geometry action failed on '{object_name}'", exc_info=True)
        return _finish(get_exception_last_n_lines(3, e))
    finally:
        if geometry_context is not None:
            try:
                geometry_context.finalize()
            except Exception:
                pass
        if owns_handle:
            release_geometry_handle(handle)

    return _finish(None)

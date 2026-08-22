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
from typing import Optional

import bpy

from ...addon_helpers.generic_tools import get_exception_last_n_lines
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Action_Op_Record,
    Action_Record,
    Enum_Geometry_Type,
    Enum_Op_Type,
    Enum_Step_Kind,
    Geometry_Actions_Declaration,
    Geometry_Actions_Result_Instance,
    get_step_kind,
)
from .helpers_read import (
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


def store_result(instance: Geometry_Actions_Result_Instance) -> None:
    """Store the latest run, replacing the same declaration/object identity."""
    results = get_all_results()
    results[instance.storage_key] = instance
    _set_all_results(results)


def _latest_group_result(grouping_id: Optional[str], object_session_uid: int):
    if not grouping_id:
        return None
    matches = [
        result for result in get_all_results().values()
        if result.grouping_id == grouping_id
        and result.object_session_uid == object_session_uid
    ]
    return max(matches, key=lambda result: result.timestamp_last_action) if matches else None


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
) -> Geometry_Actions_Result_Instance:
    """
    Run one declaration's step list against one object. Always returns the result instance,
    valid or not; inspect instance.last_action for the outcome of this specific call.
    """
    logger      = get_logger(Block_Loggers.GEOMETRY_ACTIONS_EVENTS)
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

    inherited = _latest_group_result(declaration.grouping_id, object_session_uid)
    if inherited is None:
        instance = Geometry_Actions_Result_Instance(
            declaration_id  = declaration.declaration_id,
            object_name     = object_name,
            grouping_id     = declaration.grouping_id,
            timestamp_start = action.timestamp_start,
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
        logger.debug(
            f"action #{action.action_uid} '{action.declaration_id}' on '{object_name}' "
            f"valid={action.is_valid} {action.duration_ms:.2f}ms"
        )
        return instance

    # ---- Acquire the geometry ONCE for the whole step list ----------------------
    handle = acquire_geometry_for_read(
        object, depsgraph, str(declaration.read_source), str(declaration.geometry_target)
    )
    action.geometry_target = str(handle.geometry_target)
    action.geometry_type   = str(handle.geometry_type)
    instance.geometry_type = str(handle.geometry_type)
    if not handle.is_valid:
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
                    ))
                except Exception as e:
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.READ, label=attr.key, is_valid=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        error_str=get_exception_last_n_lines(3, e),
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
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=get_exception_last_n_lines(3, e),
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
                    action.ops.append(Action_Op_Record(
                        op_type=Enum_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=f"finalize failed: {get_exception_last_n_lines(3, e)}",
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
        release_geometry_handle(handle)

    return _finish(None)

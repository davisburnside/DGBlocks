"""
helpers_actions.py — step-list orchestration + RTC storage (with history).

One call = one Mesh_Action_Record, appended to the (object_name, slot) instance.
Steps run in the order given. A failure records the action as invalid and keeps
whatever data the reads managed to gather before failing.

Mesh acquisition happens ONCE per action for the whole step list — minimizing
depsgraph evaluations and mesh creations. The Mesh_Context is bound to that one
acquisition and finalized after each Callback_Step.
"""

import time
from collections import deque
from typing import Optional

import bpy
import numpy as np

from ...addon_helpers.generic_tools import get_exception_last_n_lines
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Callback_Step,
    Enum_Mesh_Op_Type,
    Enum_Read_Source,
    Group_Tag,
    Mesh_Action_Op_Record,
    Mesh_Action_Record,
    MET_Attr_Declaration,
    Numpy_Mesh_Action_Declaration,
    Read_Step,
    RTC_Mesh_Extract_Instance,
)
from .helpers_read import (
    acquire_mesh_for_read,
    all_domain_counts,
    domain_element_count,
    read_attr,
    release_mesh_handle,
    resolve_attr,
)
from .helpers_write import Mesh_Context, warn_write_hazards

MAX_STORED_INSTANCES = 64


# ==============================================================================================================================
# RTC STORAGE
# ==============================================================================================================================

def get_stored_instances() -> list:
    return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES) or []


def get_stored_instance(object_name: str, slot: str = "default") -> Optional[RTC_Mesh_Extract_Instance]:
    for instance in get_stored_instances():
        if instance.object_name == object_name and instance.slot == slot:
            return instance
    return None


def store_instance(instance: RTC_Mesh_Extract_Instance) -> None:
    instances = list(get_stored_instances())
    if instance not in instances:
        instances.append(instance)
    if len(instances) > MAX_STORED_INSTANCES:
        instances.sort(key=lambda i: i.timestamp_last_action)
        instances = instances[len(instances) - MAX_STORED_INSTANCES:]
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, instances)


def clear_stored_instances(object_name: Optional[str] = None) -> int:
    instances = get_stored_instances()
    keep = [] if object_name is None else [i for i in instances if i.object_name != object_name]
    removed = len(instances) - len(keep)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, keep)
    return removed


def next_action_uid() -> int:
    current = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_ACTION_UID_COUNTER) or 0
    nxt = int(current) + 1
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_ACTION_UID_COUNTER, nxt)
    return nxt


# ==============================================================================================================================
# HISTORY STORAGE
# ==============================================================================================================================

def _history_key(object_name: str, slot: str) -> str:
    return f"{object_name}|{slot}"


def get_history(object_name: str, slot: str = "default") -> deque:
    """Return the history deque for (object_name, slot). Empty if none stored."""
    history_map = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY) or {}
    return history_map.get(_history_key(object_name, slot), deque())


def push_history(instance: RTC_Mesh_Extract_Instance, depth: int) -> None:
    """Push a snapshot of the instance into its history deque (maxlen=depth)."""
    if depth <= 0:
        return
    history_map = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY) or {}
    key = _history_key(instance.object_name, instance.slot)
    dq = history_map.get(key)
    if dq is None:
        dq = deque(maxlen=depth)
        history_map[key] = dq
    elif dq.maxlen != depth:
        # depth changed — rebuild with new cap
        dq = deque(list(dq)[-depth:], maxlen=depth)
        history_map[key] = dq
    dq.append(instance)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY, history_map)


def clear_history(object_name: Optional[str] = None) -> int:
    """Clear history for one object, or all. Returns number of deques removed."""
    history_map = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY) or {}
    if object_name is None:
        removed = len(history_map)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY, {})
        return removed
    keys_to_remove = [k for k in history_map if k.startswith(f"{object_name}|")]
    for k in keys_to_remove:
        del history_map[k]
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_HISTORY, history_map)
    return len(keys_to_remove)


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
    return "-"


def _instance_content_keys(instance: RTC_Mesh_Extract_Instance) -> set:
    keys = set()
    for domain_name in ("vertex", "edge", "face", "corner"):
        domain_obj = getattr(instance, domain_name)
        for field_name in domain_obj.populated_field_names():
            keys.add(f"{domain_name}.{field_name}")
    for key in instance.derived:
        keys.add(f"derived['{key}']")
    return keys


def _domain_counts_snapshot(mesh) -> dict:
    return all_domain_counts(mesh)


def _topology_changed(before: dict, after: dict) -> bool:
    return before != after


def _invalidate_per_element_slots(instance: RTC_Mesh_Extract_Instance) -> None:
    """Null out all per-element data after a topology change (index space is stale)."""
    for domain_name in ("vertex", "edge", "face", "corner"):
        domain_obj = getattr(instance, domain_name)
        for field_name in domain_obj.builtin_field_names():
            if field_name == "count":
                continue
            setattr(domain_obj, field_name, None)
        domain_obj.custom.clear()


# ==============================================================================================================================
# MAIN ENTRY POINT
# ==============================================================================================================================

def run_mesh_action(
    object:            bpy.types.Object,
    declaration:       Numpy_Mesh_Action_Declaration,
    depsgraph:         Optional[bpy.types.Depsgraph] = None,
    existing_instance: Optional[RTC_Mesh_Extract_Instance] = None,
) -> RTC_Mesh_Extract_Instance:
    """
    Run one declaration's step list against one object. Always returns the instance,
    valid or not; inspect instance.last_action for the outcome of this specific call.
    """
    logger      = get_logger(Block_Loggers.MESH_EXTRACT_EVENTS)
    total_start = time.perf_counter()
    object_name = getattr(object, "name", "<None>")
    object_mode = getattr(object, "mode", "OBJECT")

    action = Mesh_Action_Record(
        action_uid      = next_action_uid(),
        label           = declaration.label,
        object_name     = object_name,
        timestamp_start = time.time(),
        read_source     = str(declaration.read_source),
        object_mode     = str(object_mode),
    )

    # Resolve / create the instance for this (object, slot).
    instance = existing_instance
    if instance is None and declaration.should_cache_in_RTC:
        instance = get_stored_instance(object_name, declaration.slot)
    if instance is None:
        instance = RTC_Mesh_Extract_Instance(object_name=object_name, slot=declaration.slot)
    instance.object_session_uid = getattr(object, "session_uid", 0)

    def _finish(error_str: Optional[str] = None) -> RTC_Mesh_Extract_Instance:
        action.duration_ms = (time.perf_counter() - total_start) * 1000.0
        action.error_str   = error_str
        action.is_valid    = error_str is None and all(op.is_valid for op in action.ops)
        instance.append_action(action, declaration.max_actions_retained)
        if declaration.should_cache_in_RTC:
            store_instance(instance)
        # Push to history regardless of caching — history is independent of RTC storage.
        push_history(instance, declaration.history_depth)
        logger.debug(
            f"mesh action #{action.action_uid} '{action.label}' on '{object_name}' "
            f"valid={action.is_valid} {action.duration_ms:.2f}ms"
        )
        return instance

    # ---- Acquire the mesh ONCE for the whole step list --------------------------
    handle = acquire_mesh_for_read(object, depsgraph, str(declaration.read_source))
    if not handle.is_valid:
        return _finish(handle.error_str)

    mesh = handle.mesh
    mesh_context: Optional[Mesh_Context] = None
    try:
        counts = all_domain_counts(mesh)
        action.domain_counts = counts
        instance.vertex.count = counts["VERTEX"]
        instance.edge.count   = counts["EDGE"]
        instance.face.count   = counts["FACE"]
        instance.corner.count = counts["CORNER"]

        # Surface non-fatal write hazards as a synthetic op (only if there are callbacks)
        if declaration.has_callbacks:
            for warning in warn_write_hazards(object):
                action.ops.append(Mesh_Action_Op_Record(
                    op_type=Enum_Mesh_Op_Type.CALLBACK, label="hazard", detail=warning,
                ))

        # ---- RUN THE STEP LIST ------------------------------------------------
        for step in declaration.steps or ():

            # ---- Group_Tag: no work, just a marker for logs/UI ----------------
            if isinstance(step, Group_Tag):
                action.ops.append(Mesh_Action_Op_Record(
                    op_type=Enum_Mesh_Op_Type.GROUP, label=step.label,
                ))
                continue

            # ---- Read_Step ----------------------------------------------------
            if isinstance(step, Read_Step):
                t0 = time.perf_counter()
                attr = step.attr
                resolved, resolve_error = resolve_attr(mesh, attr)
                if resolve_error or resolved is None:
                    action.ops.append(Mesh_Action_Op_Record(
                        op_type=Enum_Mesh_Op_Type.READ, label=attr.key, is_valid=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        error_str=resolve_error or f"could not resolve '{attr.key}'",
                    ))
                    continue

                try:
                    arr, detail = read_attr(mesh, resolved)
                    if arr is not None:
                        instance.set_attr_value(resolved, arr)
                    action.ops.append(Mesh_Action_Op_Record(
                        op_type     = Enum_Mesh_Op_Type.READ,
                        label       = resolved.key,
                        duration_ms = (time.perf_counter() - t0) * 1000.0,
                        shape       = _shape_str(arr),
                        is_valid    = True,
                        detail      = detail or f"→ {resolved.storage_path}",
                    ))
                except Exception as e:
                    action.ops.append(Mesh_Action_Op_Record(
                        op_type=Enum_Mesh_Op_Type.READ, label=attr.key, is_valid=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        error_str=get_exception_last_n_lines(3, e),
                    ))
                continue

            # ---- Callback_Step ------------------------------------------------
            if isinstance(step, Callback_Step):
                t0 = time.perf_counter()
                keys_before = _instance_content_keys(instance)
                counts_before = _domain_counts_snapshot(mesh)

                # Lazily create the Mesh_Context bound to this acquisition
                if mesh_context is None:
                    mesh_context = Mesh_Context(object, mesh, is_edit_mode=(object_mode == "EDIT"))

                try:
                    step.func(instance, action, mesh_context)
                except Exception as e:
                    action.ops.append(Mesh_Action_Op_Record(
                        op_type=Enum_Mesh_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=get_exception_last_n_lines(3, e),
                    ))
                    logger.error(
                        f"callback '{step.resolved_label}' failed on '{object_name}'",
                        exc_info=True,
                    )
                    # Finalize the bmesh even on failure, then bail
                    try:
                        mesh_context.finalize()
                    except Exception:
                        pass
                    return _finish(f"Callback '{step.resolved_label}' raised.")

                # Finalize any bmesh mutations from this callback
                try:
                    mesh_context.finalize()
                except Exception as e:
                    action.ops.append(Mesh_Action_Op_Record(
                        op_type=Enum_Mesh_Op_Type.CALLBACK, label=step.resolved_label,
                        duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                        error_str=f"bmesh finalize failed: {get_exception_last_n_lines(3, e)}",
                    ))
                    return _finish(f"Callback '{step.resolved_label}' finalize raised.")

                # Detect topology change — fail gracefully if counts mismatch
                # (no validation, just observation for the record)
                counts_after = _domain_counts_snapshot(mesh)
                if _topology_changed(counts_before, counts_after):
                    instance.topology_generation += 1
                    _invalidate_per_element_slots(instance)
                    # Update instance counts to the new reality
                    instance.vertex.count = counts_after["VERTEX"]
                    instance.edge.count   = counts_after["EDGE"]
                    instance.face.count   = counts_after["FACE"]
                    instance.corner.count = counts_after["CORNER"]
                    action.domain_counts = counts_after

                written = sorted(_instance_content_keys(instance) - keys_before)
                action.ops.append(Mesh_Action_Op_Record(
                    op_type     = Enum_Mesh_Op_Type.CALLBACK,
                    label       = step.resolved_label,
                    duration_ms = (time.perf_counter() - t0) * 1000.0,
                    detail      = ("→ " + ", ".join(written)) if written else "no new keys",
                ))
                continue

            # ---- Unknown step type — fail gracefully ---------------------------
            action.ops.append(Mesh_Action_Op_Record(
                op_type=Enum_Mesh_Op_Type.CALLBACK, label=str(step), is_valid=False,
                error_str=f"Unknown step type: {type(step).__name__}",
            ))
            return _finish(f"Unknown step type: {type(step).__name__}")

    except Exception as e:
        logger.error(f"mesh action failed on '{object_name}'", exc_info=True)
        return _finish(get_exception_last_n_lines(3, e))
    finally:
        # Finalize any lingering bmesh context
        if mesh_context is not None:
            try:
                mesh_context.finalize()
            except Exception:
                pass
        release_mesh_handle(handle)

    return _finish(None)

"""
helpers_actions.py — action orchestration + RTC storage.

One call = one Mesh_Action_Record, appended to the (object_name, slot) instance.
Phases run READ -> CALLBACKS -> WRITE. A failure records the action as invalid and
keeps whatever data the reads managed to gather before failing.
"""

import time
from typing import Optional

import bpy
import numpy as np

from ...addon_helpers.generic_tools import get_exception_last_n_lines
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

from .common_declarations import Block_Loggers, Block_RTC_Members
from .data_structures import (
    Callback_Op,
    Enum_Mesh_Op_Type,
    Enum_Read_Source,
    Mesh_Action_Op_Record,
    Mesh_Action_Record,
    MET_Attr_Declaration,
    Numpy_Mesh_Action_Declaration,
    RTC_Mesh_Extract_Instance,
    Write_Op,
)
from .helpers_read import (
    acquire_mesh_for_read,
    all_domain_counts,
    domain_element_count,
    read_attr,
    release_mesh_handle,
    resolve_attr,
)
from .helpers_write import (
    Mesh_Write_Error,
    check_edit_mode_write_allowed,
    validate_object_is_writable,
    validate_write_payload,
    warn_write_hazards,
    write_attr_edit_mode,
    write_attr_object_mode,
)

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


def _normalize_callbacks(callbacks) -> list:
    return [cb if isinstance(cb, Callback_Op) else Callback_Op(func=cb) for cb in (callbacks or ())]


def _normalize_write_ops(write_attributes) -> list:
    return [wo if isinstance(wo, Write_Op) else Write_Op(attr=wo) for wo in (write_attributes or ())]


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
    Run one declaration against one object. Always returns the instance, valid or not;
    inspect instance.last_action for the outcome of this specific call.
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
    # Only RTC-cached declarations adopt a previously stored instance; a non-cached
    # declaration always starts fresh unless the caller supplies existing_instance.
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
        logger.debug(
            f"mesh action #{action.action_uid} '{action.label}' on '{object_name}' "
            f"valid={action.is_valid} {action.duration_ms:.2f}ms"
        )
        return instance

    # ---- Guard: writing into evaluated index space is unsafe --------------------
    if declaration.has_writes and declaration.read_source == Enum_Read_Source.EVALUATED \
            and not declaration.allow_evaluated_index_space:
        return _finish(
            "Declaration combines write_attributes with read_source=EVALUATED. "
            "Modifier-evaluated indices may not match the original mesh, so writes could "
            "land on the wrong elements. Use read_source=ORIGINAL, or set "
            "allow_evaluated_index_space=True if the stack is known to preserve topology."
        )

    # ---- Acquire the mesh -------------------------------------------------------
    handle = acquire_mesh_for_read(object, depsgraph, str(declaration.read_source))
    if not handle.is_valid:
        return _finish(handle.error_str)

    mesh = handle.mesh
    try:
        counts = all_domain_counts(mesh)
        action.domain_counts = counts
        instance.vertex.count = counts["VERTEX"]
        instance.edge.count   = counts["EDGE"]
        instance.face.count   = counts["FACE"]
        instance.corner.count = counts["CORNER"]

        # ---- PHASE 1: READS ----------------------------------------------------
        resolved_reads: dict[str, MET_Attr_Declaration] = {}
        for attr in declaration.read_attributes or ():
            t0 = time.perf_counter()
            resolved, resolve_error = resolve_attr(mesh, attr)
            if resolve_error:
                action.ops.append(Mesh_Action_Op_Record(
                    op_type=Enum_Mesh_Op_Type.READ, label=attr.key, is_valid=False,
                    duration_ms=(time.perf_counter() - t0) * 1000.0, error_str=resolve_error,
                ))
                continue

            arr, detail = read_attr(mesh, resolved)
            if arr is not None:
                instance.set_attr_value(resolved, arr)
                resolved_reads[resolved.key] = resolved
            action.ops.append(Mesh_Action_Op_Record(
                op_type     = Enum_Mesh_Op_Type.READ,
                label       = resolved.key,
                duration_ms = (time.perf_counter() - t0) * 1000.0,
                shape       = _shape_str(arr),
                is_valid    = True,
                detail      = detail or f"→ {resolved.storage_path}",
            ))

        # ---- PHASE 2: CALLBACKS ------------------------------------------------
        for callback_op in _normalize_callbacks(declaration.callbacks):
            t0 = time.perf_counter()
            keys_before = _instance_content_keys(instance)
            try:
                callback_op.func(instance, action)
            except Exception as e:
                action.ops.append(Mesh_Action_Op_Record(
                    op_type=Enum_Mesh_Op_Type.CALLBACK, label=callback_op.resolved_label,
                    duration_ms=(time.perf_counter() - t0) * 1000.0, is_valid=False,
                    error_str=get_exception_last_n_lines(3, e),
                ))
                logger.error(
                    f"callback '{callback_op.resolved_label}' failed on '{object_name}'",
                    exc_info=True,
                )
                return _finish(f"Callback '{callback_op.resolved_label}' raised.")

            written = sorted(_instance_content_keys(instance) - keys_before)
            action.ops.append(Mesh_Action_Op_Record(
                op_type     = Enum_Mesh_Op_Type.CALLBACK,
                label       = callback_op.resolved_label,
                duration_ms = (time.perf_counter() - t0) * 1000.0,
                detail      = ("→ " + ", ".join(written)) if written else "no new keys",
            ))

        # ---- PHASE 3: WRITES ---------------------------------------------------
        if declaration.has_writes:
            error_str = _run_write_phase(object, declaration, instance, action, resolved_reads, logger)
            if error_str:
                return _finish(error_str)

    except Exception as e:
        logger.error(f"mesh action failed on '{object_name}'", exc_info=True)
        return _finish(get_exception_last_n_lines(3, e))
    finally:
        release_mesh_handle(handle)

    return _finish(None)


# ==============================================================================================================================
# WRITE PHASE
# ==============================================================================================================================

def _run_write_phase(
    object:         bpy.types.Object,
    declaration:    Numpy_Mesh_Action_Declaration,
    instance:       RTC_Mesh_Extract_Instance,
    action:         Mesh_Action_Record,
    resolved_reads: dict,
    logger,
) -> Optional[str]:
    """
    Validate every write op, then apply them all. Writes always target the ORIGINAL
    mesh (object.data) — never the evaluated copy. Returns an error string on failure.
    """
    import bmesh

    try:
        validate_object_is_writable(object)
        check_edit_mode_write_allowed(object, str(declaration.edit_mode_write_strategy))
    except Mesh_Write_Error as e:
        return str(e)

    is_edit_mode = object.mode == "EDIT"
    if is_edit_mode:
        # Make object.data element counts trustworthy without leaving Edit Mode.
        try:
            object.update_from_editmode()
        except Exception as e:
            return f"update_from_editmode() failed before write: {e}"

    target_mesh = object.data

    for warning in warn_write_hazards(object):
        action.ops.append(Mesh_Action_Op_Record(
            op_type=Enum_Mesh_Op_Type.WRITE, label="hazard", detail=warning,
        ))

    # ---- Validate all ops before applying any ----
    planned: list[tuple] = []   # (attr, flat_payload, previous_values)
    for write_op in _normalize_write_ops(declaration.write_attributes):
        attr = write_op.attr
        resolved, resolve_error = resolve_attr(target_mesh, attr)
        if resolve_error or resolved is None:
            return f"Write target '{attr.key}' could not be resolved: {resolve_error}"

        payload = write_op.payload
        if payload is None:
            payload = instance.get_attr_value(resolved)
        try:
            n_elements   = domain_element_count(target_mesh, resolved.domain)
            flat_payload = validate_write_payload(resolved, payload, n_elements)
        except Mesh_Write_Error as e:
            return str(e)

        previous = instance.get_attr_value(resolved) if resolved.key in resolved_reads else None
        planned.append((resolved, flat_payload, previous))

    # ---- Apply ----
    if declaration.should_push_undo:
        try:
            bpy.ops.ed.undo_push(message=f"Mesh Write: {declaration.label}")
        except Exception:
            pass

    bm = bmesh.from_edit_mesh(target_mesh) if is_edit_mode else None
    try:
        for attr, flat_payload, previous in planned:
            t0 = time.perf_counter()
            try:
                if is_edit_mode:
                    detail = write_attr_edit_mode(
                        object, bm, attr, flat_payload, previous,
                        declaration.diff_limited_writes,
                    )
                else:
                    detail = write_attr_object_mode(
                        target_mesh, attr, flat_payload, str(declaration.on_type_mismatch),
                    )
            except Mesh_Write_Error as e:
                action.ops.append(Mesh_Action_Op_Record(
                    op_type=Enum_Mesh_Op_Type.WRITE, label=attr.key, is_valid=False,
                    duration_ms=(time.perf_counter() - t0) * 1000.0, error_str=str(e),
                ))
                return str(e)

            action.ops.append(Mesh_Action_Op_Record(
                op_type     = Enum_Mesh_Op_Type.WRITE,
                label       = attr.key,
                duration_ms = (time.perf_counter() - t0) * 1000.0,
                shape       = _shape_str(flat_payload),
                detail      = detail,
            ))
    finally:
        if is_edit_mode:
            bmesh.update_edit_mesh(target_mesh, loop_triangles=True, destructive=False)
        else:
            target_mesh.update()

    return None

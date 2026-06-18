
import time
from typing import Optional

import bpy
import numpy as np

# Addon-level imports
from ...addon_helpers.data_structures import Enum_Sync_Events
from ...addon_helpers.generic_tools import get_exception_last_n_lines

# Inter-block imports
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import (
    MET,
    MET_Attr_Declaration,
    Mesh_Extract_Target,
    RTC_Mesh_Extract_Instance,
    met_attr_label,
)
from .helpers_computed import (
    build_face_face_neighbors_csr,
    build_vert_face_neighbors_csr,
    build_vert_vert_neighbors_csr,
    compute_edge_length,
    compute_face_center,
)

# ==============================================================================================================================
# OBJECT COMPATIBILITY CHECK
# ==============================================================================================================================

# Types that can produce a mesh via to_mesh()
# Blender 5.0: check ob.type directly — these types support evaluated mesh access
_MESH_CAPABLE_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD"}


def _object_has_mesh(obj: bpy.types.Object) -> bool:
    """Return True if this object type can produce a temporary mesh via to_mesh()."""
    return obj.type in _MESH_CAPABLE_TYPES


# ==============================================================================================================================
# VALIDATION
# ==============================================================================================================================

def validate_mesh_extract_targets(merged_targets: dict[str, Mesh_Extract_Target]) -> None:
    """
    Run all pre-extraction validation checks.
    Raises ValueError with a descriptive message if any check fails.
    All checks complete before any bpy or RTC state is mutated.

    Checks:
        1. For every Nth-level (computed) attribute requested, all first_level_deps
           are also in read_attributes.
        2. Callback required_attributes are all present in the merged read_attributes.
        3. Duplicate callback UIDs within a single object's merged MET.
    """
    for object_name, target in merged_targets.items():
        attr_set = set(target.read_attributes)

        # Check 1: computed attribute dependencies
        for attr in target.read_attributes:
            if attr.is_computed:
                missing_deps = [dep for dep in attr.first_level_deps if dep not in attr_set]
                if missing_deps:
                    missing_labels = [met_attr_label(d) for d in missing_deps]
                    raise ValueError(
                        f"Object '{object_name}': computed attribute '{met_attr_label(attr)}' "
                        f"requires the following attributes to also be in read_attributes, "
                        f"but they are missing: {missing_labels}. "
                        f"Add them to the Mesh_Extract_Target submitted for this object."
                    )

        # Check 2: callback required_attributes
        for cb in target.callbacks:
            missing_cb_attrs = [a for a in cb.required_attributes if a not in attr_set]
            if missing_cb_attrs:
                missing_labels = [met_attr_label(a) for a in missing_cb_attrs]
                raise ValueError(
                    f"Object '{object_name}': callback '{cb.uid}' requires attributes "
                    f"{missing_labels} but they are not in read_attributes for this object."
                )

        # Check 3: duplicate callback UIDs
        cb_uids = [cb.uid for cb in target.callbacks]
        seen_uids = set()
        for uid in cb_uids:
            if uid in seen_uids:
                raise ValueError(
                    f"Object '{object_name}': duplicate callback UID '{uid}'. "
                    f"Each Mesh_Extract_Callback uid must be unique within a merged target."
                )
            seen_uids.add(uid)


# ==============================================================================================================================
# MET MERGE LOGIC
# ==============================================================================================================================

def merge_mesh_extract_targets(
    targets_by_block: dict[str, list[Mesh_Extract_Target]]
) -> dict[str, Mesh_Extract_Target]:
    """
    Merge all Mesh_Extract_Target submissions from all blocks into one target per object.

    - read_attributes: union (order preserved, duplicates removed)
    - custom_attributes: union by (domain, name) key
    - callbacks: concatenated in block registration order (preserves deterministic ordering)

    Conflicts are resolved silently — no exceptions for duplicates in standard attrs.
    """
    merged: dict[str, Mesh_Extract_Target] = {}

    for block_id, target_list in targets_by_block.items():
        for target in target_list:
            name = target.object_name
            if name not in merged:
                merged[name] = Mesh_Extract_Target(
                    object_name       = name,
                    read_attributes   = [],
                    custom_attributes = [],
                    callbacks         = [],
                )

            existing = merged[name]

            # Union read_attributes (preserve insertion order)
            existing_attr_set = set(existing.read_attributes)
            for attr in target.read_attributes:
                if attr not in existing_attr_set:
                    existing.read_attributes.append(attr)
                    existing_attr_set.add(attr)

            # Union custom_attributes by (domain_class, name) key
            existing_custom_keys = {(d, n) for d, n in existing.custom_attributes}
            for domain_cls, attr_name in target.custom_attributes:
                key = (domain_cls, attr_name)
                if key not in existing_custom_keys:
                    existing.custom_attributes.append((domain_cls, attr_name))
                    existing_custom_keys.add(key)

            # Append callbacks in order (duplicate uid detection happens in validate)
            existing.callbacks.extend(target.callbacks)

    return merged


# ==============================================================================================================================
# SINGLE-ATTRIBUTE READ HELPERS
# ==============================================================================================================================

def _foreach_get_attr(
    mesh: bpy.types.Mesh,
    attr: MET_Attr_Declaration,
) -> np.ndarray:
    """
    Read a single first-level mesh attribute via foreach_get.
    Returns a numpy array shaped appropriately for the domain count × components.
    """
    domain_count_map = {
        "VERTEX": len(mesh.vertices),
        "EDGE":   len(mesh.edges),
        "FACE":   len(mesh.polygons),
        "CORNER": len(mesh.loops),
    }
    n = domain_count_map[attr.domain]
    total = n * attr.components
    buf = np.empty(total, dtype=attr.dtype)

    # CREASE and SHARP in Blender 5.0 are named mesh attributes, not direct properties
    if attr.blender_attr in ("crease_edge", "sharp_edge"):
        bl_attr = mesh.attributes.get(attr.blender_attr)
        if bl_attr is None:
            # Attribute doesn't exist on this mesh — return zeros/False
            return np.zeros(n, dtype=attr.dtype)
        bl_attr.data.foreach_get("value", buf)
    elif attr.domain == "VERTEX" and attr.blender_attr == "co":
        mesh.vertices.foreach_get("co", buf)
    elif attr.domain == "VERTEX" and attr.blender_attr == "normal":
        mesh.vertices.foreach_get("normal", buf)
    elif attr.domain == "EDGE" and attr.blender_attr == "vertices":
        mesh.edges.foreach_get("vertices", buf)
    elif attr.domain == "FACE" and attr.blender_attr == "normal":
        mesh.polygons.foreach_get("normal", buf)
    elif attr.domain == "FACE" and attr.blender_attr == "area":
        mesh.polygons.foreach_get("area", buf)
    elif attr.domain == "FACE" and attr.blender_attr == "loop_start":
        mesh.polygons.foreach_get("loop_start", buf)
    elif attr.domain == "FACE" and attr.blender_attr == "loop_total":
        mesh.polygons.foreach_get("loop_total", buf)
    elif attr.domain == "CORNER" and attr.blender_attr == "vertex_index":
        mesh.loops.foreach_get("vertex_index", buf)
    else:
        raise ValueError(
            f"_foreach_get_attr: unhandled attribute '{met_attr_label(attr)}'. "
            f"Add it to the dispatch block or mark it is_computed=True."
        )

    if attr.components > 1:
        return buf.reshape(n, attr.components)
    return buf


def _read_custom_attribute(
    mesh: bpy.types.Mesh,
    domain_cls,
    attr_name: str,
) -> Optional[np.ndarray]:
    """
    Read a named mesh attribute (bpy mesh.attributes) in the given domain.
    Returns None if the attribute does not exist on this mesh.
    """
    bl_attr = mesh.attributes.get(attr_name)
    if bl_attr is None:
        return None

    # Infer domain count
    domain_str = bl_attr.domain   # e.g. 'POINT', 'EDGE', 'FACE', 'CORNER'
    domain_count_map = {
        "POINT":  len(mesh.vertices),
        "EDGE":   len(mesh.edges),
        "FACE":   len(mesh.polygons),
        "CORNER": len(mesh.loops),
    }
    n = domain_count_map.get(domain_str, 0)
    if n == 0:
        return None

    # Determine value type and buffer size
    data_type = bl_attr.data_type  # e.g. 'FLOAT', 'INT', 'FLOAT_VECTOR', 'BOOLEAN'
    dtype_map = {
        "FLOAT":        ("float32", 1),
        "INT":          ("int32",   1),
        "FLOAT_VECTOR": ("float32", 3),
        "FLOAT_COLOR":  ("float32", 4),
        "BYTE_COLOR":   ("float32", 4),
        "BOOLEAN":      ("bool",    1),
        "FLOAT2":       ("float32", 2),
        "INT8":         ("int32",   1),
        "INT32_2D":     ("int32",   2),
        "QUATERNION":   ("float32", 4),
    }
    if data_type not in dtype_map:
        return None

    dtype, components = dtype_map[data_type]
    buf = np.empty(n * components, dtype=dtype)

    value_field = "vector" if components == 3 else ("color" if components == 4 else "value")
    if data_type == "FLOAT2":
        value_field = "vector"
    if data_type == "QUATERNION":
        value_field = "value"

    bl_attr.data.foreach_get(value_field, buf)

    if components > 1:
        return buf.reshape(n, components)
    return buf


# ==============================================================================================================================
# COMPUTED ATTRIBUTE DISPATCH
# ==============================================================================================================================

# Maps a computed MET_Attr_Declaration → the function and the instance field names
# to read its dependencies from.
# Each entry: (instance_field_name_for_result, compute_func, [dep_field_names...])

_COMPUTED_ATTR_MAP = {
    # Keyed by identity (the MET_Attr_Declaration object itself)
}


def _apply_computed_attr(
    attr: MET_Attr_Declaration,
    instance: RTC_Mesh_Extract_Instance,
    n_verts: int,
    n_faces: int,
) -> None:
    """
    Dispatch to the appropriate helpers_computed function, read deps from instance,
    and write result back to instance.
    """
    if attr is MET.EDGE.LENGTH:
        instance.edge_length = compute_edge_length(
            instance.vertex_co, instance.edge_vertices
        )

    elif attr is MET.FACE.CENTER:
        instance.face_center = compute_face_center(
            instance.vertex_co,
            instance.face_loop_start,
            instance.face_loop_total,
            instance.corner_vertex_index,
        )

    elif attr is MET.VERTEX.VERT_NEIGHBORS:
        idx, off = build_vert_vert_neighbors_csr(instance.edge_vertices, n_verts)
        instance.vert_vert_neighbor_indices = idx
        instance.vert_vert_neighbor_offsets = off

    elif attr is MET.VERTEX.FACE_NEIGHBORS:
        idx, off = build_vert_face_neighbors_csr(
            instance.face_loop_start,
            instance.face_loop_total,
            instance.corner_vertex_index,
            n_verts,
        )
        instance.vert_face_neighbor_indices = idx
        instance.vert_face_neighbor_offsets = off

    elif attr is MET.FACE.FACE_NEIGHBORS:
        idx, off = build_face_face_neighbors_csr(
            instance.edge_vertices,
            instance.face_loop_start,
            instance.face_loop_total,
            instance.corner_vertex_index,
            n_faces,
        )
        instance.face_face_neighbor_indices = idx
        instance.face_face_neighbor_offsets = off

    else:
        raise ValueError(
            f"_apply_computed_attr: no dispatch for computed attr '{met_attr_label(attr)}'. "
            f"Add it to _apply_computed_attr in helpers.py."
        )


# Map each first-level MET_Attr_Declaration to the RTC_Mesh_Extract_Instance field name
_FIRST_LEVEL_FIELD_MAP: dict[MET_Attr_Declaration, str] = {
    MET.VERTEX.CO:            "vertex_co",
    MET.VERTEX.NORMAL:        "vertex_normal",
    MET.EDGE.VERTICES:        "edge_vertices",
    MET.EDGE.CREASE:          "edge_crease",
    MET.EDGE.SHARP:           "edge_sharp",
    MET.FACE.NORMAL:          "face_normal",
    MET.FACE.AREA:            "face_area",
    MET.FACE.LOOP_START:      "face_loop_start",
    MET.FACE.LOOP_TOTAL:      "face_loop_total",
    MET.CORNER.VERTEX_INDEX:  "corner_vertex_index",
}


# ==============================================================================================================================
# PER-OBJECT EXTRACTION
# ==============================================================================================================================

def _extract_single_object(
    object_name: str,
    target: Mesh_Extract_Target,
    depsgraph: bpy.types.Depsgraph,
    existing_instance: Optional[RTC_Mesh_Extract_Instance],
) -> RTC_Mesh_Extract_Instance:
    """
    Extract all requested mesh data from a single evaluated object.
    Returns a fully populated RTC_Mesh_Extract_Instance.
    On failure, returns an instance with is_valid=False and error_str set.
    """
    logger = get_logger(Block_Loggers.MESH_EXTRACT_EVENTS)
    total_start = time.perf_counter()

    # Resolve or create instance
    instance = existing_instance or RTC_Mesh_Extract_Instance(object_name=object_name)

    # Carry forward read_count from previous run
    existing_total_meta = instance.extract_metadata.get("_total", {})
    previous_read_count = existing_total_meta.get("read_count", 0)

    # Reset state for this extraction pass
    instance.is_valid   = False
    instance.error_str  = None
    instance.extract_metadata = {}

    # --- Get evaluated object ---
    obj = depsgraph.scene.objects.get(object_name)
    if obj is None:
        instance.error_str = f"Object '{object_name}' not found in depsgraph scene."
        logger.warning(instance.error_str)
        _write_total_meta(instance, total_start, previous_read_count + 1)
        return instance

    if not _object_has_mesh(obj):
        instance.error_str = (
            f"Object '{object_name}' (type={obj.type!r}) cannot produce a mesh. "
            f"Only types {sorted(_MESH_CAPABLE_TYPES)} are supported."
        )
        logger.warning(instance.error_str)
        _write_total_meta(instance, total_start, previous_read_count + 1)
        return instance

    evaluated_obj = obj.evaluated_get(depsgraph)

    try:
        mesh = evaluated_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    except Exception as e:
        instance.error_str = f"to_mesh() failed: {get_exception_last_n_lines(2, e)}"
        logger.error(f"_extract_single_object: to_mesh() failed for '{object_name}'", exc_info=True)
        _write_total_meta(instance, total_start, previous_read_count + 1)
        return instance

    if mesh is None:
        instance.error_str = f"to_mesh() returned None for '{object_name}'."
        logger.warning(instance.error_str)
        _write_total_meta(instance, total_start, previous_read_count + 1)
        return instance

    try:
        n_verts   = len(mesh.vertices)
        n_edges   = len(mesh.edges)
        n_faces   = len(mesh.polygons)
        n_corners = len(mesh.loops)

        # ---- First-level reads ----
        first_level_attrs = [a for a in target.read_attributes if not a.is_computed]
        for attr in first_level_attrs:
            t0 = time.perf_counter()
            try:
                arr = _foreach_get_attr(mesh, attr)
                field_name = _FIRST_LEVEL_FIELD_MAP.get(attr)
                if field_name:
                    setattr(instance, field_name, arr)
                else:
                    logger.warning(f"No instance field for attr '{met_attr_label(attr)}' — skipping write.")
            except Exception as e:
                logger.error(f"foreach_get failed for '{met_attr_label(attr)}' on '{object_name}'", exc_info=True)
                raise
            _record_attr_meta(instance, arr.shape, met_attr_label(attr), t0,
                              instance.extract_metadata.get(met_attr_label(attr), {}).get("read_count", 0) + 1)

        # ---- Custom attribute reads ----
        for domain_cls, attr_name in target.custom_attributes:
            t0 = time.perf_counter()
            arr = _read_custom_attribute(mesh, domain_cls, attr_name)
            if arr is not None:
                instance.custom_attribute_arrays[attr_name] = arr
            else:
                logger.warning(f"Custom attribute '{attr_name}' not found on mesh '{object_name}' — skipping.")
            prev_count = instance.extract_metadata.get(f"custom:{attr_name}", {}).get("read_count", 0)
            _record_attr_meta(instance, arr.shape, f"custom:{attr_name}", t0, prev_count + 1)

        # ---- Computed attribute reads (in dependency-safe order) ----
        # Sort: first-level first, then computed (deps are guaranteed to be read already by validate)
        computed_attrs = [a for a in target.read_attributes if a.is_computed]
        for attr in computed_attrs:
            t0 = time.perf_counter()
            try:
                _apply_computed_attr(attr, instance, n_verts, n_faces)
            except Exception as e:
                logger.error(
                    f"Computed attr '{met_attr_label(attr)}' failed for '{object_name}'",
                    exc_info=True,
                )
                raise
            prev_count = instance.extract_metadata.get(met_attr_label(attr), {}).get("read_count", 0)
            _record_attr_meta(instance, None, met_attr_label(attr), t0, prev_count + 1)

        # ---- Callbacks ----
        for cb in target.callbacks:
            t0 = time.perf_counter()
            arr = None
            try:
                arr = cb.callback(instance, **cb.params)
            except Exception as e:
                logger.error(
                    f"Mesh_Extract_Callback '{cb.uid}' raised on '{object_name}'",
                    exc_info=True,
                )
                # Callbacks do not abort the extraction — log and continue
            prev_count = instance.extract_metadata.get(cb.uid, {}).get("read_count", 0)
            shape = arr.shape if arr is not None else None
            _record_attr_meta(instance, shape, cb.uid, t0, prev_count + 1)

        instance.is_valid = True

    except Exception as e:
        instance.is_valid  = False
        instance.error_str = get_exception_last_n_lines(3, e)

    finally:
        evaluated_obj.to_mesh_clear()

    _write_total_meta(instance, total_start, previous_read_count + 1)
    logger.debug(
        f"_extract_single_object: '{object_name}' valid={instance.is_valid} "
        f"total={instance.extract_metadata.get('_total', {}).get('duration_ms', 0.0):.2f}ms"
    )
    return instance


# ==============================================================================================================================
# METADATA HELPERS
# ==============================================================================================================================

def _record_attr_meta(
    instance: RTC_Mesh_Extract_Instance,
    shape,
    label: str,
    t0: float,
    read_count: int,
) -> None:
    """Write per-attribute timing into instance.extract_metadata."""
    duration_ms = (time.perf_counter() - t0) * 1000.0
    instance.extract_metadata[label] = {
        "duration_ms": duration_ms,
        "read_count":  read_count,
        "shape": shape if shape else ""
    }


def _write_total_meta(
    instance: RTC_Mesh_Extract_Instance,
    total_start: float,
    read_count: int,
) -> None:
    """Write object-level total timing into instance.extract_metadata['_total']."""
    total_ms = (time.perf_counter() - total_start) * 1000.0
    instance.extract_metadata["_total"] = {
        "duration_ms": total_ms,
        "read_count":  read_count,
    }


# ==============================================================================================================================
# FULL EXTRACTION CYCLE — called by Wrapper_Mesh_Extract and the scene property trigger
# ==============================================================================================================================

def run_mesh_extract() -> list[str]:
    """
    Full extraction cycle:
        1. Fire hook_get_mesh_extract_targets — collect Mesh_Extract_Target lists from all blocks.
        2. Merge targets by object_name (silent union).
        3. Validate merged targets — raise ValueError on any dependency/callback violation.
        4. Get the current depsgraph.
        5. For each object: call _extract_single_object, reusing or creating an RTC instance.
        6. Push updated list to RTC.
        7. Sync BL data mirror.
        8. Fire hook_mesh_extract_ready with the list of processed object names.

    Returns list of object names that were processed (regardless of is_valid).
    """
    logger = get_logger(Block_Loggers.MESH_EXTRACT_LIFECYCLE)
    logger.debug("run_mesh_extract: starting")

    # Step 1: Collect
    raw_results = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name         = Block_Hook_Sources.hook_get_mesh_extract_targets,
        should_halt_on_exception = False,
    )
    targets_by_block: dict[str, list[Mesh_Extract_Target]] = {}
    for block_id, result in raw_results.items():
        if isinstance(result, list):
            targets_by_block[block_id] = result
        else:
            logger.warning(
                f"run_mesh_extract: block '{block_id}' returned {type(result)!r} "
                f"from hook_get_mesh_extract_targets — expected list[Mesh_Extract_Target], skipping."
            )

    if not targets_by_block:
        logger.info("run_mesh_extract: no Mesh_Extract_Targets returned — returning early.")
        return []

    # Step 2: Merge
    merged_targets = merge_mesh_extract_targets(targets_by_block)
    logger.debug(f"run_mesh_extract: merged into {len(merged_targets)} object target(s)")

    # Step 3: Validate (raises on error — aborts the whole cycle cleanly)
    try:
        validate_mesh_extract_targets(merged_targets)
    except ValueError as e:
        logger.error(f"run_mesh_extract: validation failed — {e}", exc_info=True)
        raise

    # Step 4: Get depsgraph
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
    except Exception as e:
        logger.error("run_mesh_extract: could not get depsgraph", exc_info=True)
        raise

    # Step 5: Extract each object
    existing_instances: dict[str, RTC_Mesh_Extract_Instance] = {
        inst.object_name: inst
        for inst in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES)
    }

    new_instances: list[RTC_Mesh_Extract_Instance] = []
    processed_names: list[str] = []

    for object_name, target in merged_targets.items():
        existing = existing_instances.get(object_name)
        instance = _extract_single_object(object_name, target, depsgraph, existing)
        new_instances.append(instance)
        processed_names.append(object_name)

    # Step 6: Push to RTC
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MESH_EXTRACT_INSTANCES, new_instances)

    # Step 7: Sync BL mirror
    cache_key = Block_RTC_Members.MESH_EXTRACT_INSTANCES
    try:
        FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key)
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event                = Enum_Sync_Events.PROPERTY_UPDATE,
            BL_is_truth_source   = False,
            cache_key            = cache_key,
            FWC_instance         = FWC_instance,
            data_mirror_instance = data_mirror_instance,
            actions_denied       = set(),
            logger               = logger,
        )
    except Exception as e:
        logger.error("run_mesh_extract: BL mirror sync failed", exc_info=True)

    # Step 8: Fire ready hook
    Wrapper_Hooks.run_hooked_funcs(
        hook_func_name           = Block_Hook_Sources.hook_mesh_extract_ready,
        should_halt_on_exception = False,
        object_names             = processed_names,
    )

    logger.info(f"run_mesh_extract: complete — {len(processed_names)} object(s) processed.")
    return processed_names

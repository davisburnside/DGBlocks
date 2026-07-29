
"""
helpers_write.py — attribute writes.

foreach_set is only effective in OBJECT mode. In EDIT mode the Mesh datablock is a
stale snapshot (the BMesh owns the live data and overwrites the Mesh on flush), and
BMesh exposes no foreach_get/foreach_set — so Edit-Mode writes are a per-element
Python loop, narrowed to changed elements only when diff_limited_writes is on.
"""

from typing import Optional

import bpy
import numpy as np

from .data_structures import (
    BL_DATA_TYPE_MAP,
    BL_DOMAIN_FROM_MET,
    RESERVED_ATTR_NAMES,
    Enum_Attr_Accessor,
    Enum_Attr_Type_Mismatch,
    Enum_Edit_Mode_Write_Strategy,
    MET_Attr_Declaration,
)
from .helpers_read import domain_element_count


class Mesh_Write_Error(Exception):
    pass


# ==============================================================================================================================
# VALIDATION (all ops validated before any op is applied)
# ==============================================================================================================================

def validate_object_is_writable(object: bpy.types.Object) -> None:
    if object is None or object.type != "MESH":
        raise Mesh_Write_Error(f"Writes require a MESH object; got {getattr(object, 'type', None)!r}.")
    mesh = object.data
    if mesh.library is not None:
        raise Mesh_Write_Error(f"Mesh '{mesh.name}' is linked from an external file — read-only.")
    if getattr(mesh, "is_editmode", False) and object.mode != "EDIT":
        raise Mesh_Write_Error(f"Mesh '{mesh.name}' is in Edit Mode via another object.")


def validate_write_payload(
    attr:    MET_Attr_Declaration,
    payload,
    n_elements: int,
) -> np.ndarray:
    """Return a contiguous, correctly-typed, flattened buffer ready for foreach_set."""
    if not attr.is_writable:
        raise Mesh_Write_Error(
            f"'{attr.key}' is not writable — Blender derives it from topology."
        )
    if attr.is_custom and attr.name in RESERVED_ATTR_NAMES:
        raise Mesh_Write_Error(f"'{attr.name}' is a reserved Blender attribute name.")
    if attr.is_custom and attr.name.startswith("."):
        raise Mesh_Write_Error(f"'{attr.name}' is a Blender-internal attribute name.")
    if payload is None:
        raise Mesh_Write_Error(
            f"No payload staged for '{attr.key}' (expected at instance.{attr.storage_path})."
        )

    arr = np.ascontiguousarray(payload)
    expected = n_elements * attr.components
    if arr.size != expected:
        raise Mesh_Write_Error(
            f"'{attr.key}' payload has {arr.size} values; expected {expected} "
            f"({n_elements} elements x {attr.components})."
        )
    dtype = attr.dtype or "float32"
    return arr.reshape(-1).astype(dtype, copy=False)


def ensure_named_attribute(
    mesh:             bpy.types.Mesh,
    attr:             MET_Attr_Declaration,
    on_type_mismatch: str,
) -> bpy.types.Attribute:
    """Fetch (creating if needed) the named attribute this write targets."""
    bl_domain = BL_DOMAIN_FROM_MET[str(attr.domain)]
    existing  = mesh.attributes.get(attr.name)

    if existing is not None:
        matches = existing.domain == bl_domain and (
            attr.data_type is None or existing.data_type == attr.data_type
        )
        if matches:
            return existing
        if on_type_mismatch == Enum_Attr_Type_Mismatch.ERROR:
            raise Mesh_Write_Error(
                f"Attribute '{attr.name}' exists as {existing.domain}/{existing.data_type} "
                f"but the write declares {bl_domain}/{attr.data_type}. "
                f"Set on_type_mismatch=RECREATE to replace it."
            )
        mesh.attributes.remove(existing)

    if not attr.data_type:
        raise Mesh_Write_Error(
            f"Attribute '{attr.name}' does not exist and no data_type was declared — "
            f"use MET.{attr.domain}.CUSTOM_ATTRIBUTE('{attr.name}', data_type='FLOAT')."
        )
    return mesh.attributes.new(name=attr.name, type=attr.data_type, domain=bl_domain)


# ==============================================================================================================================
# OBJECT MODE — bulk foreach_set
# ==============================================================================================================================

def write_attr_object_mode(
    mesh:             bpy.types.Mesh,
    attr:             MET_Attr_Declaration,
    flat_payload:     np.ndarray,
    on_type_mismatch: str,
) -> str:
    if attr.accessor == Enum_Attr_Accessor.COLLECTION:
        collection = getattr(mesh, attr.collection_name)
        collection.foreach_set(attr.value_field, flat_payload)
        return f"foreach_set mesh.{attr.collection_name}.{attr.value_field}"

    bl_attr = ensure_named_attribute(mesh, attr, on_type_mismatch)
    bl_attr.data.foreach_set(attr.value_field, flat_payload)
    return f"foreach_set attributes['{attr.name}'].{attr.value_field}"


# ==============================================================================================================================
# EDIT MODE — bmesh, per-element loop
# ==============================================================================================================================

# BMesh layer collection name per Blender data_type
_BM_LAYER_KIND = {
    "FLOAT": "float", "INT": "int", "INT8": "int", "BOOLEAN": "bool",
    "FLOAT_VECTOR": "float_vector", "FLOAT2": "uv", "FLOAT_COLOR": "float_color",
    "BYTE_COLOR": "color",
}


def _bm_sequence(bm, met_domain: str):
    return {"VERTEX": bm.verts, "EDGE": bm.edges, "FACE": bm.faces, "CORNER": bm.loops}[str(met_domain)]


def _iter_bm_elements(bm, met_domain: str):
    """Yield elements in the same order as the Mesh datablock's index space."""
    if str(met_domain) == "CORNER":
        for face in bm.faces:
            for loop in face.loops:
                yield loop
    else:
        for element in _bm_sequence(bm, met_domain):
            yield element


def write_attr_edit_mode(
    object:            bpy.types.Object,
    bm,
    attr:              MET_Attr_Declaration,
    flat_payload:      np.ndarray,
    previous_values:   Optional[np.ndarray],
    diff_limited:      bool,
) -> str:
    """
    Write one attribute through bmesh. Returns a detail string for the op record.
    `previous_values` (the value read earlier this action) enables diff-limiting.
    """
    components = attr.components
    values     = flat_payload.reshape(-1, components) if components > 1 else flat_payload

    # Which element indices actually need touching?
    changed_idx = None
    if diff_limited and previous_values is not None:
        prev = np.ascontiguousarray(previous_values).reshape(values.shape)
        differs = values != prev
        if components > 1:
            differs = differs.any(axis=1)
        changed_idx = set(int(i) for i in np.flatnonzero(differs))
        if not changed_idx:
            return "no change — bmesh loop skipped"

    # --- Builtin fast paths (no custom layer involved) ---
    if attr.accessor == Enum_Attr_Accessor.COLLECTION or attr.name in ("seam_edge", "sharp_edge"):
        setter, seq_domain = _resolve_builtin_bmesh_setter(attr)
        if setter is None:
            raise Mesh_Write_Error(f"'{attr.key}' cannot be written in Edit Mode.")
        count = 0
        for idx, element in enumerate(_iter_bm_elements(bm, seq_domain)):
            if changed_idx is not None and idx not in changed_idx:
                continue
            setter(element, values[idx])
            count += 1
        return f"bmesh loop, {count} element(s)"

    # --- Named attribute → bmesh custom data layer ---
    layer_kind = _BM_LAYER_KIND.get(attr.data_type or "")
    if layer_kind is None:
        raise Mesh_Write_Error(
            f"data_type {attr.data_type!r} has no BMesh layer equivalent — "
            f"cannot write '{attr.name}' in Edit Mode."
        )

    sequence   = _bm_sequence(bm, attr.domain)
    collection = getattr(sequence.layers, layer_kind, None)
    if collection is None:
        raise Mesh_Write_Error(
            f"BMesh has no '{layer_kind}' layer collection on domain {attr.domain} "
            f"in this Blender version."
        )
    layer = collection.get(attr.name) or collection.new(attr.name)

    is_uv = attr.is_uv_map or layer_kind == "uv"
    count = 0
    for idx, element in enumerate(_iter_bm_elements(bm, attr.domain)):
        if changed_idx is not None and idx not in changed_idx:
            continue
        value = values[idx]
        if is_uv:
            element[layer].uv = (float(value[0]), float(value[1]))
        elif components > 1:
            element[layer] = tuple(float(v) for v in value)
        else:
            element[layer] = value.item()
        count += 1
    return f"bmesh loop, {count} element(s)"


def _resolve_builtin_bmesh_setter(attr: MET_Attr_Declaration):
    """Return (setter_func, domain) for builtin attributes writable via BMesh members."""
    key = attr.key
    if key == "VERTEX.co":
        return (lambda v, val: setattr(v, "co", (float(val[0]), float(val[1]), float(val[2])))), "VERTEX"
    if key == "EDGE.seam_edge":
        return (lambda e, val: setattr(e, "seam", bool(val))), "EDGE"
    if key == "EDGE.sharp_edge":
        # BMesh stores the inverse: smooth == not sharp
        return (lambda e, val: setattr(e, "smooth", not bool(val))), "EDGE"
    return None, str(attr.domain)


def check_edit_mode_write_allowed(object: bpy.types.Object, strategy: str) -> None:
    if object.mode == "EDIT" and strategy == Enum_Edit_Mode_Write_Strategy.REJECT:
        raise Mesh_Write_Error(
            f"'{object.name}' is in Edit Mode and edit_mode_write_strategy=REJECT."
        )


def warn_write_hazards(object: bpy.types.Object) -> list[str]:
    """Non-fatal conditions worth surfacing in the action record."""
    warnings: list[str] = []
    mesh = object.data
    if mesh.users > 1:
        warnings.append(f"mesh '{mesh.name}' has {mesh.users} users — write affects all of them")
    if getattr(mesh, "shape_keys", None):
        warnings.append("mesh has shape keys — position writes may fight the basis key")
    return warnings

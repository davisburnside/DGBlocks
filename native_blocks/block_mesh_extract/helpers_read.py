
"""
helpers_read.py — mesh acquisition + attribute reads.

MESH ACQUISITION MATRIX (no mode switching, ever)

                    | Object Mode                      | Edit Mode
    ----------------|----------------------------------|--------------------------------------
    EVALUATED       | evaluated_get(dg).to_mesh()      | evaluated_get(dg).to_mesh()
                    | post-modifier cage.              | Blender syncs BMesh -> evaluated,
                    | Indices may NOT match original.  | so this works unchanged.
    ----------------|----------------------------------|--------------------------------------
    ORIGINAL        | object.data                      | object.update_from_editmode() then
                    | Write-back safe indices.         | object.data. Bulk-fast, no mode switch.
                    |                                  | (object.data alone is STALE in Edit Mode)

Only EVALUATED acquires a temporary mesh that must be released with to_mesh_clear().
"""

from dataclasses import dataclass
from typing import Optional

import bpy
import numpy as np

from .data_structures import (
    BL_DATA_TYPE_MAP,
    MET_DOMAIN_FROM_BL,
    Enum_Attr_Accessor,
    Enum_Read_Source,
    MET_Attr_Declaration,
)

# Object types that can produce a mesh via to_mesh()
MESH_CAPABLE_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD"}

# Builtin attributes that are stored as named attributes and may legitimately be
# absent from a mesh — a missing one reads as zeros rather than an error.
_ZERO_FILL_IF_ABSENT = {
    "crease_vert", "bevel_weight_vert", "crease_edge", "sharp_edge", "seam_edge",
}


def object_has_mesh(obj: bpy.types.Object) -> bool:
    return obj is not None and obj.type in MESH_CAPABLE_TYPES


# ==============================================================================================================================
# MESH HANDLE
# ==============================================================================================================================

@dataclass
class Mesh_Handle:
    """A mesh acquired for reading. Always release with release_mesh_handle()."""
    mesh:           Optional[bpy.types.Mesh]
    read_source:    str
    object_mode:    str
    is_temporary:   bool                     = False
    evaluated_obj:  Optional[bpy.types.Object] = None
    error_str:      Optional[str]            = None

    @property
    def is_valid(self) -> bool:
        return self.mesh is not None and self.error_str is None


def acquire_mesh_for_read(
    object:      bpy.types.Object,
    depsgraph:   Optional[bpy.types.Depsgraph],
    read_source: str,
) -> Mesh_Handle:
    """Resolve the correct mesh for the object's current mode and the requested read source."""
    object_mode = getattr(object, "mode", "OBJECT") if object else "OBJECT"

    if object is None:
        return Mesh_Handle(None, read_source, object_mode, error_str="Object is None.")

    if not object_has_mesh(object):
        return Mesh_Handle(
            None, read_source, object_mode,
            error_str=(
                f"Object '{object.name}' (type={object.type!r}) cannot produce a mesh. "
                f"Supported: {sorted(MESH_CAPABLE_TYPES)}"
            ),
        )

    # ---- ORIGINAL ------------------------------------------------------------
    if read_source == Enum_Read_Source.ORIGINAL:
        if object.type != "MESH":
            return Mesh_Handle(
                None, read_source, object_mode,
                error_str=(
                    f"read_source=ORIGINAL requires a MESH object; '{object.name}' is {object.type!r}. "
                    f"Use read_source=EVALUATED for generated geometry."
                ),
            )
        if object_mode == "EDIT":
            # object.data is a stale snapshot in Edit Mode — sync BMesh -> Mesh first.
            # This is a bulk copy, NOT a mode switch, and leaves the BMesh untouched.
            try:
                object.update_from_editmode()
            except Exception as e:
                return Mesh_Handle(
                    None, read_source, object_mode,
                    error_str=f"update_from_editmode() failed: {e}",
                )
        return Mesh_Handle(object.data, read_source, object_mode, is_temporary=False)

    # ---- EVALUATED -----------------------------------------------------------
    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    evaluated_obj = object.evaluated_get(depsgraph)
    try:
        mesh = evaluated_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    except Exception as e:
        return Mesh_Handle(
            None, read_source, object_mode, evaluated_obj=evaluated_obj,
            error_str=f"to_mesh() failed: {e}",
        )

    if mesh is None:
        return Mesh_Handle(
            None, read_source, object_mode, evaluated_obj=evaluated_obj,
            error_str=f"to_mesh() returned None for '{object.name}'.",
        )

    return Mesh_Handle(mesh, read_source, object_mode, is_temporary=True, evaluated_obj=evaluated_obj)


def release_mesh_handle(handle: Mesh_Handle) -> None:
    if handle.is_temporary and handle.evaluated_obj is not None:
        try:
            handle.evaluated_obj.to_mesh_clear()
        except Exception:
            pass


# ==============================================================================================================================
# DOMAIN COUNTS
# ==============================================================================================================================

def domain_element_count(mesh: bpy.types.Mesh, met_domain: str) -> int:
    return {
        "VERTEX": len(mesh.vertices),
        "EDGE":   len(mesh.edges),
        "FACE":   len(mesh.polygons),
        "CORNER": len(mesh.loops),
    }[str(met_domain)]


def all_domain_counts(mesh: bpy.types.Mesh) -> dict[str, int]:
    return {
        "VERTEX": len(mesh.vertices),
        "EDGE":   len(mesh.edges),
        "FACE":   len(mesh.polygons),
        "CORNER": len(mesh.loops),
    }


# ==============================================================================================================================
# ATTRIBUTE RESOLUTION
# ==============================================================================================================================

def resolve_attr(
    mesh: bpy.types.Mesh,
    attr: MET_Attr_Declaration,
) -> tuple[Optional[MET_Attr_Declaration], Optional[str]]:
    """
    Fill in anything that can only be known at run time:
      - active UV map name  (MET.CORNER.UV_MAP() with name=None)
      - dtype / components / value_field for custom attributes declared without data_type

    Returns (resolved_attr, error_str). error_str set only for unrecoverable problems.
    """
    resolved = attr

    # Active UV map name
    if attr.is_uv_map and attr.resolve_active:
        uv_layers = getattr(mesh, "uv_layers", None)
        active = uv_layers.active if uv_layers else None
        if active is None:
            return None, "No active UV map on this mesh."
        resolved = resolved.resolved_copy(name=active.name, resolve_active=False)

    if resolved.accessor != Enum_Attr_Accessor.NAMED_ATTRIBUTE:
        return resolved, None

    bl_attr = mesh.attributes.get(resolved.name)
    if bl_attr is None:
        # Absent: builtin-backed names read as zeros; custom attrs are simply skipped.
        return resolved, None

    data_type = bl_attr.data_type
    if data_type not in BL_DATA_TYPE_MAP:
        return None, f"Unsupported attribute data_type {data_type!r} for '{resolved.name}'."

    dtype, components, value_field = BL_DATA_TYPE_MAP[data_type]
    bl_domain = MET_DOMAIN_FROM_BL.get(bl_attr.domain)
    if bl_domain is None:
        return None, f"Unsupported attribute domain {bl_attr.domain!r} for '{resolved.name}'."

    if resolved.is_custom and bl_domain != resolved.domain:
        return None, (
            f"Attribute '{resolved.name}' is on domain {bl_domain} but was declared as "
            f"{resolved.domain}."
        )

    return resolved.resolved_copy(
        dtype       = dtype,
        components  = components,
        value_field = value_field,
        data_type   = data_type,
    ), None


# ==============================================================================================================================
# READS
# ==============================================================================================================================

def read_attr(
    mesh: bpy.types.Mesh,
    attr: MET_Attr_Declaration,
) -> tuple[Optional[np.ndarray], str]:
    """
    Read one attribute into a numpy array.
    Returns (array_or_None, detail_str). None means "not present on this mesh".
    """
    n = domain_element_count(mesh, attr.domain)

    # ---- Collection-backed (mesh.vertices / edges / polygons / loops) --------
    if attr.accessor == Enum_Attr_Accessor.COLLECTION:
        collection = getattr(mesh, attr.collection_name, None)
        if collection is None:
            return None, f"mesh has no collection '{attr.collection_name}'"
        buf = np.empty(n * attr.components, dtype=attr.dtype)
        if n:
            collection.foreach_get(attr.value_field, buf)
        return (buf.reshape(n, attr.components) if attr.components > 1 else buf), ""

    # ---- Named attribute (mesh.attributes[...]) ------------------------------
    bl_attr = mesh.attributes.get(attr.name)
    if bl_attr is None:
        if attr.name in _ZERO_FILL_IF_ABSENT:
            zeros = np.zeros(
                (n, attr.components) if attr.components > 1 else n,
                dtype=attr.dtype or "float32",
            )
            return zeros, "absent -> zeros"
        return None, "absent"

    components = attr.components
    dtype      = attr.dtype or "float32"
    buf = np.empty(n * components, dtype=dtype)
    if n:
        bl_attr.data.foreach_get(attr.value_field, buf)
    return (buf.reshape(n, components) if components > 1 else buf), ""


def list_readable_custom_attribute_names(mesh: bpy.types.Mesh) -> list[str]:
    """
    Public helper: user-facing named attributes on a mesh.
    Skips Blender's dot-prefixed internals (.corner_vert, .select_vert, .uv_seam, ...).
    """
    return [a.name for a in mesh.attributes if not a.name.startswith(".")]

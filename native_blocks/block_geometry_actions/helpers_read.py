
"""
helpers_read.py — geometry acquisition + attribute reads (meshes AND curves).

GEOMETRY ACQUISITION MATRIX (no mode switching, ever)

  geometry_target = MESH_EVALUATED
    read_source EVALUATED : evaluated_get(dg).to_mesh()   (post-modifier cage; temporary)
    read_source ORIGINAL  : MESH objects only → object.data
                            (Edit Mode: object.update_from_editmode() first)

  geometry_target = NATIVE_DATA
    MESH object   : same as MESH_EVALUATED/ORIGINAL above for ORIGINAL;
                    EVALUATED uses the evaluated mesh.
    CURVES object : object.data (or evaluated_get(dg).data for EVALUATED)
    CURVE object  : legacy bpy.types.Curve has no `.attributes` — converted to CURVES
                    on demand (Blender 5.0 quirk), guarded by try/except so the
                    conversion only ever happens once per object.

Only to_mesh() results are temporary and must be released with release_geometry_handle().
"""

from dataclasses import dataclass
from typing import Optional

import bpy
import numpy as np

from .data_structures import (
    BL_DATA_TYPE_MAP,
    CURVE_DOMAINS,
    Enum_Attr_Accessor,
    Enum_Geometry_Target,
    Enum_Geometry_Type,
    Enum_Read_Source,
    Attr_Declaration,
    domain_from_bl_domain,
)

# Object types that can produce a mesh via to_mesh()
MESH_CAPABLE_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD"}

# Object types that carry (or can be converted to) native curve data
CURVE_OBJECT_TYPES = {"CURVES", "CURVE"}

# Builtin attributes that are stored as named attributes and may legitimately be
# absent — a missing one reads as zeros rather than an error.
_ZERO_FILL_IF_ABSENT = {
    "crease_vert", "bevel_weight_vert", "crease_edge", "sharp_edge", "seam_edge",
    "radius", "tilt", "resolution", "cyclic", "curve_type",
}


def object_has_geometry(obj: bpy.types.Object) -> bool:
    return obj is not None and obj.type in MESH_CAPABLE_TYPES


def resolve_geometry_target(obj: bpy.types.Object, geometry_target: str) -> str:
    """Turn AUTO into a concrete target for this object."""
    if str(geometry_target) != Enum_Geometry_Target.AUTO:
        return str(geometry_target)
    if obj is not None and obj.type in ("MESH", *CURVE_OBJECT_TYPES):
        return Enum_Geometry_Target.NATIVE_DATA
    return Enum_Geometry_Target.MESH_EVALUATED


# ==============================================================================================================================
# CURVE DATA — legacy conversion (Blender 5.0 quirk)
# ==============================================================================================================================

def _has_attributes_api(data) -> bool:
    """True when the datablock exposes the generic `.attributes` collection."""
    try:
        data.attributes
        return True
    except AttributeError:
        return False


def ensure_curves_datablock(obj: bpy.types.Object) -> tuple[Optional[object], Optional[str]]:
    """
    Return (curves_datablock, error_str) for a curve object.

    Legacy `bpy.types.Curve` has no `.attributes` collection, so named attributes are
    unreachable from Python. Blender 5.0 requires a one-time
    `bpy.ops.object.convert(target='CURVES')` to get a `bpy.types.Curves` datablock.

    The try/except on `.attributes` is what makes this idempotent: once converted, the
    object's type is already CURVES and no further conversion is attempted.
    """
    data = obj.data
    if _has_attributes_api(data):
        return data, None

    if obj.type != "CURVE":
        return None, (
            f"'{obj.name}' ({obj.type}) has no `.attributes` API and is not a legacy Curve."
        )

    if obj.mode != "OBJECT":
        return None, (
            f"'{obj.name}' is a legacy Curve and must be converted to CURVES before "
            f"attributes are reachable, but conversion requires Object Mode "
            f"(current mode: {obj.mode})."
        )

    try:
        with bpy.context.temp_override(
            object=obj,
            active_object=obj,
            selected_objects=[obj],
            selected_editable_objects=[obj],
        ):
            bpy.ops.object.convert(target="CURVES")
    except Exception as e:
        return None, f"Legacy Curve → CURVES conversion failed for '{obj.name}': {e}"

    # `obj` is the same Object datablock; only its data was swapped.
    data = obj.data
    if not _has_attributes_api(data):
        return None, (
            f"'{obj.name}' still has no `.attributes` API after conversion "
            f"(type={obj.type!r})."
        )
    return data, None


# ==============================================================================================================================
# GEOMETRY HANDLE
# ==============================================================================================================================

@dataclass
class Geometry_Handle:
    """Geometry acquired for reading. Always release with release_geometry_handle()."""
    data:            Optional[object]            # bpy.types.Mesh or bpy.types.Curves
    geometry_type:   str
    geometry_target: str
    read_source:     str
    object_mode:     str
    is_temporary:    bool                        = False
    evaluated_obj:   Optional[bpy.types.Object]  = None
    error_str:       Optional[str]               = None

    @property
    def is_valid(self) -> bool:
        return self.data is not None and self.error_str is None

    @property
    def is_curves(self) -> bool:
        return str(self.geometry_type) == Enum_Geometry_Type.CURVES


def acquire_geometry_for_read(
    object:          bpy.types.Object,
    depsgraph:       Optional[bpy.types.Depsgraph],
    read_source:     str,
    geometry_target: str,
) -> Geometry_Handle:
    """Resolve the correct datablock for the object's mode, read source and target."""
    object_mode = getattr(object, "mode", "OBJECT") if object else "OBJECT"
    target      = resolve_geometry_target(object, geometry_target)

    def _fail(msg: str) -> Geometry_Handle:
        return Geometry_Handle(
            None, Enum_Geometry_Type.UNKNOWN, target, read_source, object_mode, error_str=msg
        )

    if object is None:
        return _fail("Object is None.")
    if not object_has_geometry(object):
        return _fail(
            f"Object '{object.name}' (type={object.type!r}) carries no supported geometry. "
            f"Supported: {sorted(MESH_CAPABLE_TYPES)}"
        )

    # ---- NATIVE curve data ---------------------------------------------------
    if target == Enum_Geometry_Target.NATIVE_DATA and object.type in CURVE_OBJECT_TYPES:
        source_obj = object
        if str(read_source) == Enum_Read_Source.EVALUATED:
            if depsgraph is None:
                depsgraph = bpy.context.evaluated_depsgraph_get()
            source_obj = object.evaluated_get(depsgraph)
            if not _has_attributes_api(source_obj.data):
                return _fail(
                    f"Evaluated data for '{object.name}' has no `.attributes` API — "
                    f"use read_source=ORIGINAL, or geometry_target=MESH_EVALUATED."
                )
            return Geometry_Handle(
                source_obj.data, Enum_Geometry_Type.CURVES, target, read_source,
                object_mode, evaluated_obj=source_obj,
            )

        curves_data, error_str = ensure_curves_datablock(object)
        if error_str:
            return _fail(error_str)
        return Geometry_Handle(
            curves_data, Enum_Geometry_Type.CURVES, target, read_source, object_mode,
        )

    # ---- ORIGINAL mesh -------------------------------------------------------
    if str(read_source) == Enum_Read_Source.ORIGINAL:
        if object.type != "MESH":
            return _fail(
                f"read_source=ORIGINAL with a mesh target requires a MESH object; "
                f"'{object.name}' is {object.type!r}. Use read_source=EVALUATED, or "
                f"geometry_target=NATIVE_DATA for curves."
            )
        if object_mode == "EDIT":
            # object.data is a stale snapshot in Edit Mode — sync BMesh -> Mesh first.
            # This is a bulk copy, NOT a mode switch, and leaves the BMesh untouched.
            try:
                object.update_from_editmode()
            except Exception as e:
                return _fail(f"update_from_editmode() failed: {e}")
        return Geometry_Handle(
            object.data, Enum_Geometry_Type.MESH, target, read_source, object_mode,
        )

    # ---- EVALUATED mesh ------------------------------------------------------
    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    evaluated_obj = object.evaluated_get(depsgraph)
    try:
        mesh = evaluated_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    except Exception as e:
        return _fail(f"to_mesh() failed: {e}")
    if mesh is None:
        return _fail(f"to_mesh() returned None for '{object.name}'.")

    return Geometry_Handle(
        mesh, Enum_Geometry_Type.MESH, target, read_source, object_mode,
        is_temporary=True, evaluated_obj=evaluated_obj,
    )


def release_geometry_handle(handle: Geometry_Handle) -> None:
    if handle.is_temporary and handle.evaluated_obj is not None:
        try:
            handle.evaluated_obj.to_mesh_clear()
        except Exception:
            pass


# ==============================================================================================================================
# DOMAIN COUNTS
# ==============================================================================================================================

def all_domain_counts(data, geometry_type: str) -> dict[str, int]:
    if str(geometry_type) == Enum_Geometry_Type.CURVES:
        return {
            "POINT": len(data.points),
            "CURVE": len(data.curves),
        }
    return {
        "VERTEX": len(data.vertices),
        "EDGE":   len(data.edges),
        "FACE":   len(data.polygons),
        "CORNER": len(data.loops),
    }


def domain_element_count(data, domain: str, geometry_type: str) -> int:
    counts = all_domain_counts(data, geometry_type)
    if str(domain) not in counts:
        raise RuntimeError(
            f"Domain {domain!r} does not exist on {geometry_type} geometry "
            f"(available: {sorted(counts)})."
        )
    return counts[str(domain)]


# ==============================================================================================================================
# ATTRIBUTE RESOLUTION
# ==============================================================================================================================

def resolve_attr(
    data,
    attr: Attr_Declaration,
    geometry_type: str,
) -> tuple[Optional[Attr_Declaration], Optional[str]]:
    """
    Fill in anything that can only be known at run time:
      - active UV map name  (MET.CORNER.UV_MAP() with name=None)
      - dtype / components / value_field for custom attributes declared without data_type

    Returns (resolved_attr, error_str). error_str set only for unrecoverable problems.
    """
    is_curves = str(geometry_type) == Enum_Geometry_Type.CURVES

    # Guard against mixing vocabularies
    if is_curves and not attr.is_curve_domain:
        return None, (
            f"'{attr.key}' is a mesh attribute but the target is curve data — "
            f"use the CET namespace, or geometry_target=MESH_EVALUATED."
        )
    if not is_curves and attr.is_curve_domain:
        return None, (
            f"'{attr.key}' is a curve attribute but the target is mesh data — "
            f"use the MET namespace."
        )

    resolved = attr

    # Active UV map name
    if attr.is_uv_map and attr.resolve_active:
        uv_layers = getattr(data, "uv_layers", None)
        active = uv_layers.active if uv_layers else None
        if active is None:
            return None, "No active UV map on this mesh."
        resolved = resolved.resolved_copy(name=active.name, resolve_active=False)

    if resolved.accessor != Enum_Attr_Accessor.NAMED_ATTRIBUTE:
        return resolved, None

    bl_attr = data.attributes.get(resolved.name)
    if bl_attr is None:
        # Absent: builtin-backed names read as zeros; custom attrs are simply skipped.
        return resolved, None

    data_type = bl_attr.data_type
    if data_type not in BL_DATA_TYPE_MAP:
        return None, f"Unsupported attribute data_type {data_type!r} for '{resolved.name}'."

    dtype, components, value_field = BL_DATA_TYPE_MAP[data_type]
    actual_domain = domain_from_bl_domain(bl_attr.domain, geometry_type)
    if actual_domain is None:
        return None, f"Unsupported attribute domain {bl_attr.domain!r} for '{resolved.name}'."

    if actual_domain != str(resolved.domain):
        return None, (
            f"Attribute '{resolved.name}' is on domain {actual_domain} but was declared as "
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

def read_attr(data, attr: Attr_Declaration, geometry_type: str) -> Optional[np.ndarray]:
    """
    Read one attribute into a numpy array. None means "not present on this geometry".
    Raises for genuinely broken reads; the step runner records the failure.
    """
    n = domain_element_count(data, attr.domain, geometry_type)

    # ---- Collection-backed (mesh.vertices / edges / polygons / loops, curves.curves)
    if attr.accessor == Enum_Attr_Accessor.COLLECTION:
        collection = getattr(data, attr.collection_name, None)
        if collection is None:
            return None
        buf = np.empty(n * attr.components, dtype=attr.dtype)
        if n:
            collection.foreach_get(attr.value_field, buf)
        return buf.reshape(n, attr.components) if attr.components > 1 else buf

    # ---- Named attribute (data.attributes[...]) ------------------------------
    bl_attr = data.attributes.get(attr.name)
    if bl_attr is None:
        if attr.name in _ZERO_FILL_IF_ABSENT:
            return np.zeros(
                (n, attr.components) if attr.components > 1 else n,
                dtype=attr.dtype or "float32",
            )
        return None

    components = attr.components
    dtype      = attr.dtype or "float32"
    buf = np.empty(n * components, dtype=dtype)
    if n:
        bl_attr.data.foreach_get(attr.value_field, buf)
    return buf.reshape(n, components) if components > 1 else buf


def list_readable_custom_attribute_names(data) -> list[str]:
    """
    Public helper: user-facing named attributes on a mesh or curves datablock.
    Skips Blender's dot-prefixed internals (.corner_vert, .select_vert, .uv_seam, ...).
    """
    if not _has_attributes_api(data):
        return []
    return [a.name for a in data.attributes if not a.name.startswith(".")]

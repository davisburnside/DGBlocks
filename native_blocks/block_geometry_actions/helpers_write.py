"""
helpers_write.py — Geometry_Context: the callback's validation-free channel to the geometry.

Design philosophy: NO pre-flight validation. The callback attempts its write via
geometry_context.write_attr() / edit_bmesh(); if Blender raises, the exception propagates
to the step runner, which catches it and marks the op (and the action) invalid with the
error string. Fail gracefully, never crash the host.

foreach_set is only effective in OBJECT mode for meshes. In EDIT mode the Mesh datablock is
a stale snapshot (the BMesh owns the live data and overwrites the Mesh on flush), and BMesh
exposes no foreach_get/foreach_set — so Edit-Mode mesh writes are a per-element Python loop.

Curves (bpy.types.Curves) have no BMesh: writes always go through .attributes + foreach_set,
and Edit Mode on curves is rejected with a clear error.
"""

from typing import Optional

import bmesh
import bpy
import numpy as np

from ...addon_helpers.data_tools import guess_mesh_attribute_type_from_data

from .data_structures import (
    BL_DOMAIN_FROM_DOMAIN,
    Enum_Attr_Accessor,
    Enum_Geometry_Type,
    Attr_Declaration,
)


# ==============================================================================================================================
# GEOMETRY CONTEXT
# ==============================================================================================================================

class Geometry_Context:
    """
    Handed to every Callback_Step's func as the third argument.

    Provides:
        write_attr(attr_dec, arr)  — attempt a validation-free attribute write
        edit_bmesh()               — BMesh for mesh topology edits (mesh geometry only)
        resize_curves(...)         — rebuild curve point counts (curve geometry only)

    The context is bound to ONE geometry acquisition for the whole step list. It is NOT
    mode-switching: Object Mode uses object.data + round-trip bmeshes; Edit Mode uses the
    live edit BMesh. The framework finalizes after each Callback_Step that touched it.
    """

    def __init__(
        self,
        object:        bpy.types.Object,
        data,
        geometry_type: str,
        is_edit_mode:  bool,
    ):
        self.object        = object
        self.data          = data
        self.geometry_type = str(geometry_type)
        self.is_edit_mode  = is_edit_mode
        # Edit Mode: the live BMesh from bmesh.from_edit_mesh. Object Mode: None until
        # edit_bmesh() is called, then a round-trip bmesh.new()/from_mesh().
        self._bm: Optional["bmesh.types.BMesh"] = None
        self._bm_is_owned = False  # True when we created it via bmesh.new() (Object Mode)
        self._bm_touched  = False  # True if any callback mutated the bmesh

    @property
    def is_curves(self) -> bool:
        return self.geometry_type == Enum_Geometry_Type.CURVES

    # Backwards-friendly alias — most callbacks only ever touch `.data`
    @property
    def mesh(self):
        return self.data

    # ----------------------------------------------------------
    # Attribute writes — no validation, fail gracefully
    # ----------------------------------------------------------

    def write_attr(self, attr_dec: Attr_Declaration, arr) -> str:
        """
        Attempt to write `arr` to `attr_dec` on the geometry. Returns a short detail string
        (used only for logging). Raises on any failure; the step runner catches and records.
        """
        flat = np.ascontiguousarray(arr).reshape(-1)
        dtype = arr.dtype if isinstance(arr, np.ndarray) else (attr_dec.dtype or "float32")
        flat = flat.astype(dtype, copy=False)

        if self.is_curves:
            return self._write_attr_curves(attr_dec, flat)
        if self.is_edit_mode:
            return self._write_attr_mesh_edit_mode(attr_dec, flat)
        return self._write_attr_mesh_object_mode(attr_dec, flat)

    # ---- curves --------------------------------------------------------------

    def _write_attr_curves(self, attr_dec: Attr_Declaration, flat: np.ndarray) -> str:
        if self.is_edit_mode:
            raise RuntimeError(
                "Curve attribute writes are not supported in Edit Mode — the curve edit "
                "session owns the data. Switch to Object Mode."
            )
        if attr_dec.accessor == Enum_Attr_Accessor.COLLECTION:
            raise RuntimeError(
                f"'{attr_dec.key}' is derived curve topology data and cannot be written."
            )
        bl_attr = self._ensure_named_attribute(attr_dec, flat)
        bl_attr.data.foreach_set(attr_dec.value_field, flat)
        self.data.update()
        return f"foreach_set curves.attributes['{attr_dec.name}']"

    # ---- meshes --------------------------------------------------------------

    def _write_attr_mesh_object_mode(self, attr_dec: Attr_Declaration, flat: np.ndarray) -> str:
        if attr_dec.accessor == Enum_Attr_Accessor.COLLECTION:
            layer_col = getattr(self.data, attr_dec.collection_name)
            layer_col.foreach_set(attr_dec.value_field, flat)
            return f"foreach_set mesh.{attr_dec.collection_name}.{attr_dec.value_field}"

        bl_attr = self._ensure_named_attribute(attr_dec, flat)
        bl_attr.data.foreach_set(attr_dec.value_field, flat)
        return f"foreach_set attributes['{attr_dec.name}']"

    def _write_attr_mesh_edit_mode(self, attr_dec: Attr_Declaration, flat: np.ndarray) -> str:
        bm = self.edit_bmesh()
        components = attr_dec.components
        values = flat.reshape(-1, components) if components > 1 else flat

        # Builtin fast paths
        if (attr_dec.accessor == Enum_Attr_Accessor.COLLECTION
                or attr_dec.name in ("seam_edge", "sharp_edge")):
            setter, seq_domain = _resolve_builtin_bmesh_setter(attr_dec)
            if setter is None:
                raise RuntimeError(f"'{attr_dec.key}' cannot be written in Edit Mode.")
            count = 0
            for idx, element in enumerate(_iter_bm_elements(bm, seq_domain)):
                setter(element, values[idx])
                count += 1
            self._bm_touched = True
            return f"bmesh loop, {count} element(s)"

        # Named attribute → bmesh custom data layer
        data_type = attr_dec.data_type or guess_mesh_attribute_type_from_data(
            values, attr_dec.components
        )
        layer_kind = _BM_LAYER_KIND.get(data_type)
        if layer_kind is None:
            raise RuntimeError(
                f"data_type {data_type!r} has no BMesh layer equivalent — "
                f"cannot write '{attr_dec.name}' in Edit Mode."
            )

        sequence = _bm_sequence(bm, attr_dec.domain)
        layer_col = getattr(sequence.layers, layer_kind, None)
        if layer_col is None:
            raise RuntimeError(
                f"BMesh has no '{layer_kind}' layer collection on domain {attr_dec.domain}."
            )
        layer = layer_col.get(attr_dec.name) or layer_col.new(attr_dec.name)

        is_uv = attr_dec.is_uv_map or layer_kind == "uv"
        count = 0
        for idx, element in enumerate(_iter_bm_elements(bm, attr_dec.domain)):
            value = values[idx]
            if is_uv:
                element[layer].uv = (float(value[0]), float(value[1]))
            elif components > 1:
                element[layer] = tuple(float(v) for v in value)
            else:
                element[layer] = value.item()
            count += 1
        self._bm_touched = True
        return f"bmesh loop, {count} element(s)"

    def _ensure_named_attribute(self, attr_dec: Attr_Declaration, values=None):
        """Fetch (creating if needed) the named attribute this write targets. No validation."""
        bl_domain = BL_DOMAIN_FROM_DOMAIN[str(attr_dec.domain)]
        actual_attr = self.data.attributes.get(attr_dec.name)
        if actual_attr is not None:
            return actual_attr

        data_type = attr_dec.data_type
        if not data_type:
            if values is None:
                raise RuntimeError(
                    f"Attribute '{attr_dec.name}' does not exist, no data_type was declared, "
                    f"and no values were supplied to infer one."
                )
            try:
                data_type = guess_mesh_attribute_type_from_data(values, attr_dec.components)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"Attribute '{attr_dec.name}' does not exist and its data_type could not "
                    f"be inferred: {exc}"
                ) from exc

        return self.data.attributes.new(name=attr_dec.name, type=data_type, domain=bl_domain)

    # ----------------------------------------------------------
    # Topology edits
    # ----------------------------------------------------------

    def edit_bmesh(self):
        """
        Return a BMesh for mesh topology edits.

        Edit Mode  : the live BMesh from bmesh.from_edit_mesh(object.data).
        Object Mode: a round-trip bmesh.new()/from_mesh(). The framework writes it back
                     after the callback returns.
        """
        if self.is_curves:
            raise RuntimeError(
                "edit_bmesh() is mesh-only. Curve geometry has no BMesh — use "
                "resize_curves() plus write_attr()."
            )
        if self._bm is not None:
            return self._bm
        if self.is_edit_mode:
            self._bm = bmesh.from_edit_mesh(self.object.data)
        else:
            self._bm = bmesh.new()
            self._bm.from_mesh(self.data)
            self._bm_is_owned = True
        return self._bm

    def resize_curves(self, points_per_curve) -> str:
        """
        Rebuild the curve point layout: `points_per_curve` is a sequence of per-curve point
        counts. Existing point attribute data is NOT preserved — write it again afterwards.
        Curve geometry only.
        """
        if not self.is_curves:
            raise RuntimeError("resize_curves() is curve-only. Use edit_bmesh() for meshes.")
        if self.is_edit_mode:
            raise RuntimeError("resize_curves() requires Object Mode.")
        sizes = [int(n) for n in points_per_curve]
        if any(n < 1 for n in sizes):
            raise RuntimeError("Every curve must have at least 1 point.")
        self.data.remove_curves()
        self.data.add_curves(sizes)
        self.data.update()
        return f"resized to {len(sizes)} curve(s) / {sum(sizes)} point(s)"

    # ----------------------------------------------------------
    # Finalization — called by the step runner after each Callback_Step
    # ----------------------------------------------------------

    def finalize(self) -> None:
        """Flush any bmesh mutations back to the mesh. Called after each Callback_Step."""
        if self.is_curves:
            if not self.is_edit_mode:
                self.data.update()
            return
        if self._bm is None:
            if not self.is_edit_mode:
                self.data.update()
            return
        if self._bm_touched:
            if self.is_edit_mode:
                bmesh.update_edit_mesh(self.object.data, loop_triangles=True, destructive=True)
            else:
                self._bm.to_mesh(self.data)
                self.data.update()
        if self._bm_is_owned:
            self._bm.free()
        self._bm = None
        self._bm_touched = False
        self._bm_is_owned = False


# ==============================================================================================================================
# BMesh helpers (Edit-Mode mesh write path)
# ==============================================================================================================================

_BM_LAYER_KIND = {
    "FLOAT": "float", "INT": "int", "INT8": "int", "BOOLEAN": "bool",
    "FLOAT_VECTOR": "float_vector", "FLOAT2": "uv", "FLOAT_COLOR": "float_color",
    "BYTE_COLOR": "color",
}


def _bm_sequence(bm, domain: str):
    try:
        return {
            "VERTEX": bm.verts, "EDGE": bm.edges, "FACE": bm.faces, "CORNER": bm.loops,
        }[str(domain)]
    except KeyError:
        raise RuntimeError(f"Domain {domain!r} has no BMesh sequence.")


def _iter_bm_elements(bm, domain: str):
    """Yield elements in the same order as the Mesh datablock's index space."""
    if str(domain) == "CORNER":
        for face in bm.faces:
            for loop in face.loops:
                yield loop
    else:
        for element in _bm_sequence(bm, domain):
            yield element


def _resolve_builtin_bmesh_setter(attr_dec: Attr_Declaration):
    """Return (setter_func, domain) for builtin attributes writable via BMesh members."""
    key = attr_dec.key
    if key == "VERTEX.co":
        return (lambda v, val: setattr(v, "co", (float(val[0]), float(val[1]), float(val[2])))), "VERTEX"
    if key == "EDGE.seam_edge":
        return (lambda e, val: setattr(e, "seam", bool(val))), "EDGE"
    if key == "EDGE.sharp_edge":
        # BMesh stores the inverse: smooth == not sharp
        return (lambda e, val: setattr(e, "smooth", not bool(val))), "EDGE"
    return None, str(attr_dec.domain)


# ==============================================================================================================================
# HAZARD WARNINGS (non-fatal, surfaced in the action record)
# ==============================================================================================================================

def warn_write_hazards(object: bpy.types.Object) -> list[str]:
    """Non-fatal conditions worth surfacing in the action record."""
    warnings: list[str] = []
    data = getattr(object, "data", None)
    if data is None:
        return warnings
    if getattr(data, "users", 1) > 1:
        warnings.append(f"'{data.name}' has {data.users} users — a write affects all of them")
    if getattr(data, "shape_keys", None):
        warnings.append("geometry has shape keys — position writes may fight the basis key")
    if getattr(data, "library", None) is not None:
        warnings.append("geometry is linked from another .blend — writes will likely fail")
    return warnings

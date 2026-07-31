"""
helpers_write.py — Mesh_Context: the callback's validated-free channel to the mesh.

Design philosophy: NO pre-flight validation. The callback attempts its write via
mesh_context.write_attr() or mesh_context.edit_bmesh(); if Blender raises, the
exception propagates to the step runner, which catches it and marks the op (and
the action) invalid with the error string. Fail gracefully, never crash the host.

foreach_set is only effective in OBJECT mode. In EDIT mode the Mesh datablock is a
stale snapshot (the BMesh owns the live data and overwrites the Mesh on flush), and
BMesh exposes no foreach_get/foreach_set — so Edit-Mode writes are a per-element
Python loop.
"""

from typing import Optional
import numpy as np
import bmesh
import bpy


from ...addon_helpers.data_tools import guess_mesh_attribute_type_from_data

from .data_structures import (
    BL_DOMAIN_FROM_MET,
    Enum_Attr_Accessor,
    MET_Attr_Declaration,
)
from .helpers_read import domain_element_count


# ==============================================================================================================================
# MESH CONTEXT
# ==============================================================================================================================

class Mesh_Context:
    """
    Handed to every Callback_Step's func as the third argument.

    Provides:
        write_attr(attr_dec, arr)  — attempt a validated-free attribute write (both modes)
        edit_bmesh()           — get a BMesh for topology edits (both modes)

    The context is bound to ONE mesh acquisition for the whole step list. It is
    NOT mode-switching: Object Mode uses object.data + round-trip bmeshes; Edit
    Mode uses the live edit BMesh. The framework finalizes the bmesh (to_mesh /
    update_edit_mesh) after each Callback_Step that touched it.
    """

    def __init__(self, object: bpy.types.Object, mesh: bpy.types.Mesh, is_edit_mode: bool):
        self.object        = object
        self.mesh          = mesh
        self.is_edit_mode  = is_edit_mode
        # Edit Mode: the live BMesh from bmesh.from_edit_mesh. Object Mode: None until
        # edit_bmesh() is called, then a round-trip bmesh.new()/from_mesh().
        self._bm: Optional["bmesh.types.BMesh"] = None
        self._bm_is_owned = False  # True when we created it via bmesh.new() (Object Mode)
        self._bm_touched  = False  # True if any callback mutated the bmesh

    # ----------------------------------------------------------
    # Attribute writes — no validation, fail gracefully
    # ----------------------------------------------------------

    def write_attr(self, attr_dec: MET_Attr_Declaration, arr) -> str:
        """
        Attempt to write `arr` to `attr_dec` on the mesh. Returns a detail string.
        Raises on any failure; the caller (step runner) catches and records it.

        Object Mode: foreach_set (bulk, fast).
        Edit Mode:   per-element bmesh loop (slow, correct).
        """
        flat = np.ascontiguousarray(arr).reshape(-1)
        dtype = attr_dec.dtype or "float32"
        flat = flat.astype(dtype, copy=False)

        if self.is_edit_mode:
            return self._write_attr_edit_mode(attr_dec, flat)
        return self._write_attr_object_mode(attr_dec, flat)

    def _write_attr_object_mode(self, attr_dec: MET_Attr_Declaration, flat: np.ndarray) -> str:
        if attr_dec.accessor == Enum_Attr_Accessor.COLLECTION:
            collection = getattr(self.mesh, attr_dec.collection_name)
            collection.foreach_set(attr_dec.value_field, flat)
            return f"foreach_set mesh.{attr_dec.collection_name}.{attr_dec.value_field}"

        bl_attr = self._ensure_named_attribute(attr_dec, flat)
        bl_attr.data.foreach_set(attr_dec.value_field, flat)
        return f"foreach_set attributes['{attr_dec.name}'].{attr_dec.value_field}"

    def _write_attr_edit_mode(self, attr_dec: MET_Attr_Declaration, flat: np.ndarray) -> str:
        
        bm = self.edit_bmesh()
        components = attr_dec.components
        values = flat.reshape(-1, components) if components > 1 else flat

        # Builtin fast paths
        if attr_dec.accessor == Enum_Attr_Accessor.COLLECTION or attr_dec.name in ("seam_edge", "sharp_edge"):
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
        data_type = attr_dec.data_type or guess_mesh_attribute_type_from_data(values, attr_dec.components)
        layer_kind = _BM_LAYER_KIND.get(data_type)
        if layer_kind is None:
            raise RuntimeError(
                f"data_type {attr_dec.data_type!r} has no BMesh layer equivalent — "
                f"cannot write '{attr_dec.name}' in Edit Mode."
            )

        sequence = _bm_sequence(bm, attr_dec.domain)
        collection = getattr(sequence.layers, layer_kind, None)
        if collection is None:
            raise RuntimeError(
                f"BMesh has no '{layer_kind}' layer collection on domain {attr_dec.domain}."
            )
        layer = collection.get(attr_dec.name) or collection.new(attr_dec.name)

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

    def _ensure_named_attribute(self, attr_dec: MET_Attr_Declaration, values = None):
        """Fetch (creating if needed) the named attribute this write targets. No validation."""
        bl_domain = BL_DOMAIN_FROM_MET[str(attr_dec.domain)]
        actual_attr = self.mesh.attributes.get(attr_dec.name)
        if actual_attr is not None:
            return actual_attr

        data_type = attr_dec.data_type
        if not data_type:
            if values is None:
                raise RuntimeError(
                    f"Attribute '{attr_dec.name}' does not exist, no data_type was declared, and no "
                    f"values were supplied to infer one — use "
                    f"MET.{attr_dec.domain}.CUSTOM_ATTRIBUTE('{attr_dec.name}', data_type='FLOAT')."
                )
            try:
                data_type = guess_mesh_attribute_type_from_data(values, attr_dec.components)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"Attribute '{attr_dec.name}' does not exist and its data_type could not be "
                    f"inferred: {exc}"
                ) from exc
            
        return self.mesh.attributes.new(name=attr_dec.name, type=data_type, domain=bl_domain)

    # ----------------------------------------------------------
    # Topology edits via bmesh
    # ----------------------------------------------------------

    def edit_bmesh(self):
        """
        Return a BMesh for topology edits.

        Edit Mode  : the live BMesh from bmesh.from_edit_mesh(object.data).
        Object Mode: a round-trip bmesh.new()/from_mesh(object.data). The framework
                     writes it back to the mesh after the callback returns.
        """
        if self._bm is not None:
            return self._bm
        if self.is_edit_mode:
            self._bm = bmesh.from_edit_mesh(self.object.data)
        else:
            self._bm = bmesh.new()
            self._bm.from_mesh(self.mesh)
            self._bm_is_owned = True
        return self._bm

    # ----------------------------------------------------------
    # Finalization — called by the step runner after each Callback_Step
    # ----------------------------------------------------------

    def finalize(self) -> None:
        """Flush any bmesh mutations back to the mesh. Called after each Callback_Step."""
        if self._bm is None:
            if not self.is_edit_mode:
                self.mesh.update()
            return
        if self._bm_touched:
            if self.is_edit_mode:
                bmesh.update_edit_mesh(self.object.data, loop_triangles=True, destructive=True)
            else:
                self._bm.to_mesh(self.mesh)
                self.mesh.update()
        if self._bm_is_owned:
            self._bm.free()
        self._bm = None
        self._bm_touched = False
        self._bm_is_owned = False


# ==============================================================================================================================
# BMesh helpers (Edit-Mode write path)
# ==============================================================================================================================

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


def _resolve_builtin_bmesh_setter(attr_dec: MET_Attr_Declaration):
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
    mesh = object.data
    if mesh.users > 1:
        warnings.append(f"mesh '{mesh.name}' has {mesh.users} users — write affects all of them")
    if getattr(mesh, "shape_keys", None):
        warnings.append("mesh has shape keys — position writes may fight the basis key")
    return warnings
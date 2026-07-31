
from enum import Enum, EnumMeta
import inspect
import os
from copy import deepcopy
import logging
from types import ModuleType
from dataclasses import is_dataclass, replace, asdict
from typing import Any, Callable, Collection, List, Optional
import numpy as np
import dataclasses
import json
import bpy  # type: ignore
import mathutils # type: ignore
from mathutils import Vector, Matrix, Quaternion, Color, Euler # type: ignore

# ==============================================================================================================================
# PYTHON DATA TOOLS
# ==============================================================================================================================

def is_py_listy(obj):
    return isinstance(obj, set) or isinstance(obj, list) or isinstance(obj, tuple)

def create_dict_from_nested_enum_classes(enum_cls):
    return {
        member.name: (
            create_dict_from_nested_enum_classes(member.value) if isinstance(member.value, EnumMeta)
            else deepcopy(member.value)
        )
        for member in enum_cls
    }

def fast_deepcopy_with_fallback(obj: Collection, logger:logging.Logger = None) -> Any:
    """
    Fast deepcopy for arbitrary structures.
    Copyable types: primitives, collections, tuples, Loggers, @dataclasses
    """
    
    # Tuples can't be natively copied, they require deepcopy
    if isinstance(obj, tuple):
        return tuple(deepcopy(item) for item in obj)
    
    # Collection-types
    elif isinstance(obj, dict):
        return {k: fast_deepcopy_with_fallback(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fast_deepcopy_with_fallback(item) for item in obj]
    
    # Raw values
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj

    # Enums classes (potentially nested) as values, like for 'Global_Addon_State'
    elif isinstance(obj, EnumMeta):
        return create_dict_from_nested_enum_classes(obj)

    # Return references as-is (don't copy modules, or callables)
    # elif isinstance(obj, (ModuleType, Callable)):
    #     return obj

    # Use replace() for dataclass instances.
    elif is_dataclass(obj) and not isinstance(obj, type):
        return replace(obj)
    
    elif isinstance(obj, logging.Logger):
        return obj

    try:
        # attempt python-native copy()
        if hasattr(obj, 'copy') and callable(obj.copy):
            return obj.copy()
        return obj.__class__(obj) if hasattr(obj, '__class__') else obj
    except Exception as e:
        print(f"Failed to copy object of type {type(obj)}. Returning original. Error: {e}", logger)
        return obj

def create_simplified_list_from_csv_string(input_str):
    
    list_return = input_str.split(",") # Make str list from str
    list_return = [k.strip() for k in list_return] # strip whitespace from start & end of each str
    list_return = [k for k in list_return if len(k) > 0] # remove empties
    return list_return

def get_actual_id(input):
    # Exracts the name of an enum. Prevent the dev from adding ".name" for every Enum usage, like in run_hooked_funcs

    if isinstance(input, Enum):
        return input.name
    elif isinstance(input, str):
        return input
    else:
        raise Exception("Expecting 'Enum' or 'str'")

def simple_truncate_dict(d, max_str=160, max_array_items=8, max_depth=7, _depth=0):
    # Handles Dataclasses too
    if _depth >= max_depth:
        return "..."
    if dataclasses.is_dataclass(d) and not isinstance(d, type):
        return {
            f"@{type(d).__name__}": {
                k: simple_truncate_dict(v, max_str, max_array_items, max_depth, _depth + 1)
                for k, v in dataclasses.asdict(d).items()
            }
        }
    if isinstance(d, dict):
        return {k: simple_truncate_dict(v, max_str, max_array_items, max_depth, _depth + 1) for k, v in d.items()}
    if isinstance(d, np.ndarray):
        flat = d.flat[:max_array_items].tolist()
        return f"ndarray{d.shape} dtype={d.dtype} [{', '.join(f'{x:.4g}' for x in flat)}, ...]"
    if isinstance(d, str) and len(d) > max_str:
        return d[:max_str] + "..."
    if isinstance(d, (list, tuple)):
        truncated = [simple_truncate_dict(x, max_str, max_array_items, max_depth, _depth + 1) for x in d[:max_array_items]]
        if len(d) > max_array_items:
            truncated.append(f"... ({len(d)} total)")
        return truncated
    return d

# ==============================================================================================================================
# COLOR TOOLS
# ==============================================================================================================================

def generate_n_distinct_colors(n: int, alpha: float = 1.0) -> list[tuple[float, float, float, float]]:
    """
    Generate N visually distinct RGBA colors using the golden-angle HSV method.

    Distributes hues evenly using the golden ratio conjugate (≈0.618), which
    maximises perceptual separation between adjacent hues. Saturation and value
    are fixed at levels that read well in a 3D viewport.

    Returns a list of (r, g, b, a) tuples in float [0..1] range.
    """
    if n <= 0:
        return []

    GOLDEN_RATIO_CONJUGATE = 0.6180339887498949
    colors = []
    hue = 0.0
    saturation = 0.82
    value = 0.92

    for _ in range(n):
        r, g, b = hsv_to_rgb(hue, saturation, value)
        colors.append((r, g, b, alpha))
        hue = (hue + GOLDEN_RATIO_CONJUGATE) % 1.0

    return colors


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    """Convert HSV (all in [0..1]) to RGB (all in [0..1])."""
    if s == 0.0:
        return (v, v, v)
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6
    if i == 0: return (v, t, p)
    if i == 1: return (q, v, p)
    if i == 2: return (p, v, t)
    if i == 3: return (p, q, v)
    if i == 4: return (t, p, v)
    return (v, p, q)


def lighten_color(color, factor: float = 0.3):
    r, g, b, a = color[0], color[1], color[2], color[3]
    return (r + (1.0 - r) * factor, g + (1.0 - g) * factor, b + (1.0 - b) * factor, 0.3)




# ==============================================================================================================================
# BLENDER DATA TOOLS
# ==============================================================================================================================

def is_mesh_writable(obj, mesh) -> bool:
    """True if `mesh` is real, local geometry we're allowed to write to."""
    return (
        obj.type == 'MESH'
        and mesh.library is None            # not linked from another .blend
        and mesh.override_library is None   # not a library override
        and mesh.is_editable                # catches linked-but-editable assets, missing links
        and not mesh.is_evaluated           # not a depsgraph copy (GN / modifier output)
        and not mesh.is_runtime_data        # exists in Main, will be saved
        and obj.asset_data is None          # not marked as an asset
        and mesh.asset_data is None
        and len(mesh.vertices) > 0          # has actual geometry
    )

def guess_mesh_attribute_type_from_data(values, components: Optional[int] = None) -> str:
    """
    Blender data_type inference from an input array.
    
    COVERED:
      shape (N,)            + float dtype   -> 'FLOAT'
      shape (N,)            + int dtype     -> 'INT'
      shape (N,)            + bool dtype    -> 'BOOLEAN'
      shape (N,)            + int8 dtype    -> 'INT8'   (only if dtype is explicitly int8)
      shape (N, 2)          + float         -> 'FLOAT2'   (UV-like)
      shape (N, 2)          + int           -> 'INT32_2D'
      shape (N, 3)          + float         -> 'FLOAT_VECTOR'
      shape (N, 4)          + float         -> 'FLOAT_COLOR'   (see AMBIGUOUS below)
      shape (N, 4, 4)       + float         -> 'FLOAT4X4'
      flat arrays of length N*C when `components` is declared on the attr
      sequences of mathutils.Vector / Color / Quaternion / Matrix (len() of element 0 used)
      plain nested python lists/tuples (converted via np.asarray first)
    
    AMBIGUOUS / NOT COVERED (must pass data_type explicitly):
      (N, 4) float -> could be FLOAT_COLOR or a quaternion; we always guess FLOAT_COLOR.
        mathutils.Quaternion elements are detected by type and mapped to 'QUATERNION'.
      (N, 4) float meant as BYTE_COLOR -> we always pick FLOAT_COLOR; byte color is never guessed.
      (N, 3) float meant as a color -> guessed as FLOAT_VECTOR, not color.
      (N, 2) int meant as two separate scalars -> guessed as INT32_2D.
      Flat arrays with no declared `components` and length not divisible in an obvious way ->
        treated as scalar (N,). A flat (3N,) vector array will be mis-guessed as FLOAT.
      Object/string dtypes, ragged nested sequences, empty arrays -> raise.
      FLOAT4X4 only detected from an explicit (N,4,4) shape or mathutils.Matrix elements;
        a flat (16N,) array is not recognised."""
        
    _MATHUTILS_TYPE_MAP = {
        Quaternion: "QUATERNION",
        Matrix:     "FLOAT4X4",
        Color:      "FLOAT_COLOR",
    }

    # --- mathutils element detection (before numpy conversion loses the type) ---
    if isinstance(values, (list, tuple)) and len(values):
        first = values[0]
        for mu_type, dt in _MATHUTILS_TYPE_MAP.items():
            if mu_type and isinstance(first, mu_type):
                return dt
        if Vector and isinstance(first, (Vector, Euler)):
            n = len(first)
            if n == 2:
                return "FLOAT2"
            if n == 3:
                return "FLOAT_VECTOR"
            if n == 4:
                return "FLOAT_COLOR"

    arr = np.asarray(values)

    if arr.dtype == object:
        raise RuntimeError(
            "Cannot guess data_type from an object-dtype / ragged array — pass data_type explicitly."
        )
    if arr.size == 0:
        raise RuntimeError("Cannot guess data_type from an empty array — pass data_type explicitly.")

    kind = arr.dtype.kind

    # --- reshape flat input using the declared component count ---
    if arr.ndim == 1 and components and components > 1:
        if arr.size % components:
            raise RuntimeError(
                f"Flat array of length {arr.size} is not divisible by declared components={components}."
            )
        arr = arr.reshape(-1, components)

    # --- matrices ---
    if arr.ndim == 3:
        if arr.shape[1:] == (4, 4):
            return "FLOAT4X4"
        raise RuntimeError(f"Unsupported array shape {arr.shape} — pass data_type explicitly.")

    # --- vectors / colors ---
    if arr.ndim == 2:
        width = arr.shape[1]
        if kind == "f":
            if width == 2:
                return "FLOAT2"
            if width == 3:
                return "FLOAT_VECTOR"
            if width == 4:
                return "FLOAT_COLOR"   # ambiguous: could be QUATERNION / BYTE_COLOR
        elif kind in "iu":
            if width == 2:
                return "INT32_2D"
            if width == 3:
                return "FLOAT_VECTOR"  # ints promoted; Blender has no INT vector3
        raise RuntimeError(
            f"Cannot guess data_type for shape {arr.shape} dtype {arr.dtype} — pass data_type explicitly."
        )

    # --- scalars ---
    if arr.ndim == 1:
        if kind == "b":
            return "BOOLEAN"
        if kind == "f":
            return "FLOAT"
        if kind in "iu":
            return "INT8" if arr.dtype in (np.int8, np.uint8) else "INT"

    raise RuntimeError(
        f"Cannot guess data_type for shape {arr.shape} dtype {arr.dtype} — pass data_type explicitly."
    )

# --------------------------------------------------------------
# Recursively walk down a nested PropertyGroup to print/reset its contents.
# the primary use is during debugging
# --------------------------------------------------------------

_prop_ids_to_skip = frozenset({'rna_type', 'name'})
def _walk_propertygroup(prop_group, visitor, prefix=None, _path=None):
    """Generic recursive walker for PropertyGroup trees.

    Calls visitor(prop, value, group, path) for every property encountered.
    The visitor receives:
        prop   — the bl_rna property descriptor
        value  — the result of getattr(group, prop.identifier)
        group  — the owning PropertyGroup instance
        path   — dotted string path like 'Root.nested.field'

    The visitor should return a value. How that value is used depends on
    the caller (collect into dict, ignore, etc).

    For POINTER props pointing to nested PropertyGroups, the walker recurses
    automatically. For COLLECTION props, it recurses into each item.
    The visitor is still called for both — before recursion — so it can
    act on the container itself (e.g. logging, clearing).
    """
    root = _path or prop_group.__class__.__name__

    results = {}
    for prop in prop_group.bl_rna.properties:
        prop_id = prop.identifier
        if prop_id in _prop_ids_to_skip:
            continue
        if _path is None and prefix and not prop_id.lower().startswith(prefix.lower()):
            continue

        child_path = f"{root}.{prop_id}"
        val = getattr(prop_group, prop_id)

        if prop.type == 'POINTER' and val is not None and isinstance(val, bpy.types.PropertyGroup):
            visitor(prop, val, prop_group, child_path)
            results[prop_id] = _walk_propertygroup(val, visitor, _path=child_path)

        elif prop.type == 'COLLECTION':
            visitor(prop, val, prop_group, child_path)
            items = []
            for item in val:
                if hasattr(item, "bl_rna"):
                    items.append(_walk_propertygroup(item, visitor, _path=f"{child_path}[]"))
            results[prop_id] = items

        else:
            results[prop_id] = visitor(prop, val, prop_group, child_path)

    return results

# Helpers to read BL data

def _represent(prop, val, group, path):
    """Visitor that returns a serializable representation of each property."""
    t = prop.type

    if t == 'POINTER':
        if val is None:
            return None
        name = getattr(val, "name", "???")
        return (val.bl_rna.identifier, name)

    if t == 'COLLECTION':
        return None  # walker handles recursion, this is just the pre-visit hook

    if t == 'ENUM':
        return list(val) if prop.is_enum_flag else val

    if t in ('INT', 'FLOAT', 'BOOLEAN') and prop.is_array:
        return list(val)

    if isinstance(val, mathutils.Matrix):
        return ("Matrix", val.row_size, val.col_size)

    if isinstance(val, (mathutils.Vector, mathutils.Color)):
        return ("Vector", len(val), val.magnitude)

    if isinstance(val, mathutils.Euler):
        return ("Euler", list(val), val.order)

    if isinstance(val, mathutils.Quaternion):
        return ("Quaternion", list(val), val.magnitude)

    return val

def get_propertygroup_values(prop_group, prefix=None):
    """Read all values from a PropertyGroup tree as a nested dict."""
    return _walk_propertygroup(prop_group, _represent, prefix=prefix)

# Helpers to reset BL data

def _make_reset_visitor(clear_collections=True, reset_defaults=True, logger=None):
    """Factory that builds a reset visitor with the given settings.

    Uses closure state to track per-group reset counts and report
    them when the walker moves on.
    """
    counts = {}  # path -> int

    def _default_for_prop(prop):
        t = prop.type
        if t == 'BOOLEAN':
            return tuple(prop.default_array) if prop.is_array else prop.default
        if t == 'INT':
            return tuple(prop.default_array) if prop.is_array else prop.default
        if t == 'FLOAT':
            return tuple(prop.default_array) if prop.is_array else prop.default
        if t == 'STRING':
            return prop.default
        if t == 'ENUM':
            return set(prop.default_flag) if prop.is_enum_flag else prop.default
        if t == 'POINTER':
            return None
        return None

    def visitor(prop, val, group, path):
        # Figure out the parent path for counting
        parent_path = path.rsplit(".", 1)[0] if "." in path else path

        if prop.type == 'POINTER':
            # Datablock pointer (not a nested PropertyGroup, those are recursed by walker)
            if reset_defaults:
                try:
                    setattr(group, prop.identifier, None)
                    counts[parent_path] = counts.get(parent_path, 0) + 1
                except (AttributeError, TypeError, RuntimeError):
                    pass
            return None

        if prop.type == 'COLLECTION':
            if clear_collections:
                coll = val
                count = len(coll)
                try:
                    coll.clear()
                except Exception:
                    pass
                if logger and count > 0:
                    logger.log(logger.level, f"Cleared collection '{path}': removed {count} item(s)")
            return None

        # Simple values
        if reset_defaults:
            default = _default_for_prop(prop)
            if default is not None:
                try:
                    setattr(group, prop.identifier, default)
                    counts[parent_path] = counts.get(parent_path, 0) + 1
                except (AttributeError, TypeError, RuntimeError):
                    pass

        return None

    def flush_logs():
        """Call after walk completes to emit per-group reset counts."""
        if logger:
            for group_path, count in counts.items():
                if count > 0:
                    logger.log(logger.level, f"Reset {count} value(s) in '{group_path}'")

    return visitor, flush_logs

def reset_propertygroup(prop_group, clear_collections=True, reset_defaults=True, prefix:str=None, logger:logging.Logger=None):
    """Reset a PropertyGroup tree to default values."""
    visitor, flush_logs = _make_reset_visitor(clear_collections, reset_defaults, logger)
    _walk_propertygroup(prop_group, visitor, prefix=prefix)
    flush_logs()

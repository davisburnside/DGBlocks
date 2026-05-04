
from enum import Enum, EnumMeta
import inspect
import os
from copy import deepcopy
import logging
from types import ModuleType
from dataclasses import is_dataclass, replace, asdict
from typing import Any, Callable, Collection, List, Optional
import numpy as np
import bpy  # type: ignore
import mathutils # type: ignore


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

# ==============================================================================================================================
# BLENDER DATA TOOLS
# ==============================================================================================================================

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
                    logger(f"Cleared collection '{path}': removed {count} item(s)")
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
                    logger(f"Reset {count} value(s) in '{group_path}'")

    return visitor, flush_logs

def reset_propertygroup(prop_group, clear_collections=True, reset_defaults=True,
                        prefix=None, logger=None):
    """Reset a PropertyGroup tree to default values."""
    visitor, flush_logs = _make_reset_visitor(clear_collections, reset_defaults, logger)
    _walk_propertygroup(prop_group, visitor, prefix=prefix)
    flush_logs()

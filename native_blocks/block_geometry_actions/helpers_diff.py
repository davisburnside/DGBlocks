
"""
helpers_diff.py — structural/value comparison between two Geometry_Actions_Result_Instances.

Used by callers that want to skip expensive downstream work when nothing relevant
about the mesh changed since the previous read.

Keys are the same strings the panel and op records use:

    "vertex.co"
    "face.custom['fltyps_f_plane_id']"
    "derived['face_face_neighbors']"

Comparison strategy:
    different shapes            → changed (no element scan)
    same-shape numpy arrays     → np.any(a != b)
    tuples of arrays (CSR)      → element-wise per component
    dicts                       → key sets + recursive value compare
    anything else               → a != b, exceptions treated as changed
"""

import numpy as np

_DOMAIN_NAMES = ("vertex", "edge", "face", "corner", "point", "curve")


# ==============================================================================================================================
# VALUE COMPARISON
# ==============================================================================================================================

def _arrays_differ(a: np.ndarray, b: np.ndarray) -> bool:
    if a.shape != b.shape or a.dtype.kind != b.dtype.kind:
        return True
    return bool(np.any(a != b))


def values_differ(a, b) -> bool:
    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        return _arrays_differ(a, b)

    if isinstance(a, tuple) and isinstance(b, tuple):
        if len(a) != len(b):
            return True
        return any(values_differ(x, y) for x, y in zip(a, b))

    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return True
        return any(values_differ(a[k], b[k]) for k in a)

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return True
        return any(values_differ(x, y) for x, y in zip(a, b))

    try:
        return bool(a != b)
    except Exception:
        return True


# ==============================================================================================================================
# INSTANCE FLATTENING
# ==============================================================================================================================

def flatten_instance_values(instance) -> dict:
    """dict[key_str → value] for every populated array / derived entry on the instance."""
    flat: dict = {}
    if instance is None:
        return flat

    for domain_name in _DOMAIN_NAMES:
        domain_obj = getattr(instance, domain_name)
        for field_name in domain_obj.builtin_field_names():
            value = getattr(domain_obj, field_name, None)
            if value is not None:
                flat[f"{domain_name}.{field_name}"] = value
        for key, value in (domain_obj.custom or {}).items():
            flat[f"{domain_name}.custom['{key}']"] = value

    for key, value in (instance.derived or {}).items():
        flat[f"derived['{key}']"] = value

    return flat


# ==============================================================================================================================
# PUBLIC DIFF
# ==============================================================================================================================

def _diff_instances(old, new) -> tuple[list[str], list[str], list[str]]:
    """
    Classify every key across two instances:

        added   — present in `new` only
        removed — present in `old` only
        edited  — present in both with differing data

    All three empty means the two instances carry identical data.
    """
    old_flat = flatten_instance_values(old)
    new_flat = flatten_instance_values(new)

    added   = sorted(new_flat.keys() - old_flat.keys())
    removed = sorted(old_flat.keys() - new_flat.keys())
    edited  = sorted(
        key for key in (old_flat.keys() & new_flat.keys())
        if values_differ(old_flat[key], new_flat[key])
    )
    return added, removed, edited

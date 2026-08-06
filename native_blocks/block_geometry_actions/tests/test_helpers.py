"""
test_helpers.py — tiny geometry factory + teardown used by the tests.

Everything created here is tagged with a shared name prefix so cleanup is a single
sweep, safe to run in a normal user session without touching the user's own objects.
"""

import bpy

TEST_PREFIX = "DGB_TEST_"


# ==============================================================================================================================
# CREATION
# ==============================================================================================================================

def create_test_mesh_object(name: str = "mesh") -> bpy.types.Object:
    """A 1-face quad: 4 verts, 4 edges, 1 face, 4 corners."""
    mesh = bpy.data.meshes.new(f"{TEST_PREFIX}{name}")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(f"{TEST_PREFIX}{name}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def create_test_curve_object(name: str = "curve") -> bpy.types.Object:
    """
    A Curves object (bpy.types.Curves) with one 3-point poly curve.
    Returns None when the running Blender has no Curves-object support.
    """
    curves_data = getattr(bpy.data, "hair_curves", None)
    if curves_data is None:
        return None
    curves = curves_data.new(f"{TEST_PREFIX}{name}")
    curves.add_curves([3])
    for index, point in enumerate(curves.points):
        point.position = (float(index), 0.0, 0.0)
    obj = bpy.data.objects.new(f"{TEST_PREFIX}{name}", curves)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_named_attribute(obj, name: str, domain: str, data_type: str, values) -> None:
    """Create a named attribute on the object's datablock and fill it."""
    attribute = obj.data.attributes.new(name=name, type=data_type, domain=domain)
    for index, value in enumerate(values):
        attribute.data[index].value = value


# ==============================================================================================================================
# TEARDOWN
# ==============================================================================================================================

def cleanup_test_data() -> int:
    """Remove every datablock this module created. Returns the number removed."""
    removed = 0
    for collection in (
        bpy.data.objects,
        bpy.data.meshes,
        getattr(bpy.data, "hair_curves", None),
        bpy.data.curves,
    ):
        if collection is None:
            continue
        for datablock in [d for d in collection if d.name.startswith(TEST_PREFIX)]:
            collection.remove(datablock)
            removed += 1
    return removed

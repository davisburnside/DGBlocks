
import unittest
import bpy  # type: ignore

# addon_helpers must never import from a block — this file only touches bpy.data directly,
# never RTC/loggers/etc, so it stays addon-wide rather than block-owned.

TEST_NAME_PREFIX = "DGB_TEST_"


def sweep_test_datablocks(extra_collections: tuple = ()) -> int:
    """
    Remove every bpy.data.* datablock (in the default collections plus any passed in
    extra_collections) whose name starts with TEST_NAME_PREFIX. Returns the count removed.
    Safe to call repeatedly in a live user session — only ever touches tagged test data.
    """
    removed = 0
    collections = (bpy.data.objects, bpy.data.meshes, bpy.data.curves, *extra_collections)
    for collection in collections:
        if collection is None:
            continue
        for datablock in [d for d in collection if d.name.startswith(TEST_NAME_PREFIX)]:
            collection.remove(datablock)
            removed += 1
    return removed


class Idempotent_BPY_TestCase(unittest.TestCase):
    """
    Base class for any test that creates real bpy.data datablocks: sweeps tagged datablocks
    before AND after every test, and fails loudly if a test leaves any behind (catches a
    forgotten cleanup before it reaches a real user session instead of silently accumulating
    orphaned data.

    Subclasses set extra_collections to include any bpy.data.* collection beyond
    objects/meshes/curves that their tests tag (e.g. bpy.data.images, bpy.data.actions).
    """
    extra_collections: tuple = ()

    def setUp(self):
        sweep_test_datablocks(self.extra_collections)

    def tearDown(self):
        leaked = sweep_test_datablocks(self.extra_collections)
        if leaked:
            self.fail(f"Test leaked {leaked} untracked datablock(s) — clean up in the test body, not tearDown")

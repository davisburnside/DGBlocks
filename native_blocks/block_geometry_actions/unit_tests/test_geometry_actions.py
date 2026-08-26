"""
test_geometry_actions.py — unittest suite covering the block's major features.

Run from the Blender Text Editor / Python Console:

    from DGBlocks.native_blocks.block_geometry_actions.unit_tests import run_tests
    run_tests.run()

Or headless:

    blender --background --python <addon>/native_blocks/block_geometry_actions/unit_tests/run_tests.py

Every test creates its own geometry and tears it down in tearDown, so the suite is safe
to run repeatedly inside a live user session.
"""

import unittest

import numpy as np

from .. import builtin_custom_callbacks as CB
from ..data_structures import (
    CET,
    MET,
    Callback_Step,
    Enum_Geometry_Target,
    Enum_Geometry_Type,
    Enum_Read_Source,
    Geometry_Actions_Declaration,
    Read_Step,
)
from ..feature_geometry_actions import Wrapper_Geometry_Actions as W
from ..helpers_serialize import DERIVED_KEY_SERIALIZED
from .test_helpers import (
    add_named_attribute,
    cleanup_test_data,
    create_test_curve_object,
    create_test_mesh_object,
)


class _Base(unittest.TestCase):
    def setUp(self):
        cleanup_test_data()
        W.clear_results()

    def tearDown(self):
        W.clear_results()
        cleanup_test_data()


# ==============================================================================================================================
# READS
# ==============================================================================================================================

class Test_Mesh_Reads(_Base):

    def test_builtin_and_custom_reads(self):
        """A declaration mixing builtin mesh reads and a custom face attribute read must produce a valid result."""
        obj = create_test_mesh_object()
        add_named_attribute(obj, "test_f", "FACE", "INT", [7])

        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.reads",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (
                Read_Step(MET.VERTEX.CO),
                Read_Step(MET.EDGE.VERTICES),
                Read_Step(MET.FACE.LOOP_START),
                Read_Step(MET.FACE.LOOP_TOTAL),
                Read_Step(MET.CORNER.VERTEX_INDEX),
                Read_Step(MET.FACE.CUSTOM_ATTRIBUTE("test_f")),
            ),
        )

        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertTrue(result.is_valid, result.error_str)
        self.assertEqual(result.geometry_type, Enum_Geometry_Type.MESH)
        self.assertEqual(result.vertex.count, 4)
        self.assertEqual(result.face.count, 1)
        self.assertEqual(result.corner.count, 4)
        self.assertEqual(result.vertex.co.shape, (4, 3))
        self.assertEqual(int(result.face.custom["test_f"][0]), 7)
        self.assertGreater(result.timestamp_start, 0.0)
        op_types = {op.label: op.data_type for op in result.last_action.ops}
        self.assertEqual(op_types["VERTEX.co"], "VEC3")
        self.assertEqual(op_types["FACE.test_f"], "INT")

    def test_missing_attribute_fails_only_that_op(self):
        """Reading a non-existent custom attribute must fail only that one op, not the whole action."""
        obj = create_test_mesh_object()
        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.missing",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (
                Read_Step(MET.VERTEX.CO),
                Read_Step(MET.FACE.CUSTOM_ATTRIBUTE("does_not_exist")),
            ),
        )
        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertIsNotNone(result.vertex.co)           # earlier read survived
        self.assertIsNone(result.face.get("does_not_exist"))


# ==============================================================================================================================
# CALLBACKS + WRITES
# ==============================================================================================================================

class Test_Callbacks_And_Writes(_Base):

    def test_computed_callback_and_write_back(self):
        """A callback computing a derived value and writing it back must persist as a real mesh attribute."""
        obj = create_test_mesh_object()
        attr = MET.FACE.CUSTOM_ATTRIBUTE("face_center", data_type="FLOAT_VECTOR")

        def _write_it(instance, action, context):
            context.write_attr(attr, instance.face.custom["face_center"])

        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.write",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (
                Read_Step(MET.VERTEX.CO),
                Read_Step(MET.FACE.LOOP_START),
                Read_Step(MET.FACE.LOOP_TOTAL),
                Read_Step(MET.CORNER.VERTEX_INDEX),
                Callback_Step(CB.cb_face_center),
                Callback_Step(_write_it, label="write face_center"),
            ),
        )

        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertTrue(result.is_valid, result.error_str)
        self.assertIn("face_center", obj.data.attributes)
        np.testing.assert_allclose(
            result.face.custom["face_center"][0], (0.5, 0.5, 0.0), atol=1e-6
        )

    def test_raising_callback_is_recorded_not_raised(self):
        """A callback that raises must be caught, logged, and recorded as a failed op — never propagated."""
        obj = create_test_mesh_object()

        def _boom(instance, action, context):
            raise ValueError("intentional")

        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.boom",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (Read_Step(MET.VERTEX.CO), Callback_Step(_boom)),
        )
        # The callback intentionally raises; the framework is expected to catch it, log it at
        # ERROR, and keep going rather than propagate. assertLogs both suppresses that expected
        # ERROR line from the real console handler (so a passing run doesn't print what looks
        # like a crash) and asserts the failure was actually logged, not just swallowed.
        with self.assertLogs("GEOMETRY_ACTIONS_EVENTS", level="ERROR"):
            result = W.run_geometry_action_for_object(obj, declaration)
        self.assertFalse(result.is_valid)
        self.assertIsNotNone(result.error_str)
        self.assertIsNotNone(result.vertex.co)          # pre-failure data retained
        failed_op = result.last_action.failed_ops[-1]
        self.assertEqual(failed_op.error_file, "test_geometry_actions.py")
        self.assertIsInstance(failed_op.error_line, int)


# ==============================================================================================================================
# STORAGE / GROUPING
# ==============================================================================================================================

class Test_Storage_And_Grouping(_Base):

    def test_same_id_replaces_previous_run_and_keeps_new_run_number(self):
        """Re-running the same declaration_id must replace the stored result, not add a second one."""
        obj = create_test_mesh_object()
        declaration = Geometry_Actions_Declaration(
            declaration_id="test.replace",
            read_source=Enum_Read_Source.ORIGINAL,
            steps=(Read_Step(MET.VERTEX.CO),),
        )
        first = W.run_geometry_action_for_object(obj, declaration)
        second = W.run_geometry_action_for_object(obj, declaration)
        self.assertEqual(len(W.get_all_results()), 1)
        self.assertIs(W.get_result("test.replace", obj.name), second)
        self.assertGreater(second.last_action.action_uid, first.last_action.action_uid)

    def test_different_ids_are_all_stored(self):
        """Two distinct declaration_ids on the same object must both be stored, in call order."""
        obj = create_test_mesh_object()
        for declaration_id in ("test.one", "test.two"):
            W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
                declaration_id=declaration_id,
                read_source=Enum_Read_Source.ORIGINAL,
            ))
        self.assertEqual(len(W.get_all_results()), 2)
        self.assertEqual(
            [result.declaration_id for result in W.get_all_results()],
            ["test.one", "test.two"],
        )

    def test_replacing_result_does_not_change_first_call_order(self):
        """Re-running an existing declaration_id must not move its position in the stored results order."""
        obj = create_test_mesh_object()
        first = Geometry_Actions_Declaration(
            declaration_id="test.order.first", read_source=Enum_Read_Source.ORIGINAL,
        )
        second = Geometry_Actions_Declaration(
            declaration_id="test.order.second", read_source=Enum_Read_Source.ORIGINAL,
        )
        W.run_geometry_action_for_object(obj, first)
        W.run_geometry_action_for_object(obj, second)
        W.run_geometry_action_for_object(obj, first)
        self.assertEqual(
            [result.declaration_id for result in W.get_all_results()],
            ["test.order.first", "test.order.second"],
        )

    def test_clipboard_payload_contains_full_domain_and_derived_values(self):
        """The clipboard string payload must include full domain and derived data, not a truncated summary."""
        from ..helpers_actions import result_payload_to_string

        obj = create_test_mesh_object()

        def _derived(instance, _action, _context):
            instance.derived["sequence"] = np.arange(20, dtype=np.int32)
            instance.derived["complex_keys"] = {
                ("pair", (1, 2)): np.array([3, 4], dtype=np.int32),
            }

        result = W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
            declaration_id="test.clipboard",
            read_source=Enum_Read_Source.ORIGINAL,
            steps=(Read_Step(MET.VERTEX.CO), Callback_Step(_derived)),
        ))
        text = result_payload_to_string(result)
        self.assertIn("'vertex'", text)
        self.assertIn("'derived'", text)
        self.assertIn("'sequence'", text)
        self.assertIn("'complex_keys'", text)
        self.assertIn("pair", text)
        self.assertIn("19", text)
        self.assertNotIn("...", text)

    def test_same_id_is_stored_separately_for_each_object(self):
        """The same declaration_id run against two different objects must produce two independent results."""
        first_obj = create_test_mesh_object("identity_a")
        second_obj = create_test_mesh_object("identity_b")
        declaration = Geometry_Actions_Declaration(
            declaration_id="test.same-id",
            read_source=Enum_Read_Source.ORIGINAL,
        )
        first = W.run_geometry_action_for_object(first_obj, declaration)
        second = W.run_geometry_action_for_object(second_obj, declaration)
        self.assertEqual(len(W.get_all_results()), 2)
        self.assertNotEqual(first.storage_key, second.storage_key)

    def test_grouped_run_inherits_data_and_new_read_replaces_slot(self):
        """A grouped run must inherit derived data from an earlier run in the same group, while re-reading fresh geometry."""
        obj = create_test_mesh_object()
        first_declaration = Geometry_Actions_Declaration(
            declaration_id="test.group.first",
            grouping_id="test.group",
            read_source=Enum_Read_Source.ORIGINAL,
            steps=(Read_Step(MET.VERTEX.CO), Callback_Step(
                lambda instance, _action, _context: instance.derived.update(marker="inherited")
            )),
        )
        first = W.run_geometry_action_for_object(obj, first_declaration)
        first_coords = first.vertex.co.copy()
        obj.data.vertices[0].co.z = 5.0

        second = W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
            declaration_id="test.group.second",
            grouping_id="test.group",
            read_source=Enum_Read_Source.ORIGINAL,
            steps=(Read_Step(MET.VERTEX.CO),),
        ))
        self.assertEqual(second.derived["marker"], "inherited")
        self.assertNotEqual(float(second.vertex.co[0, 2]), float(first_coords[0, 2]))
        np.testing.assert_array_equal(first.vertex.co, first_coords)

    def test_grouped_payload_is_deep_copied(self):
        """Inherited derived data in a grouped run must be deep-copied — mutating it must not affect the earlier run's result."""
        obj = create_test_mesh_object()

        def _seed(instance, _action, _context):
            instance.derived["values"] = np.array([1, 2, 3], dtype=np.int32)

        first = W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
            declaration_id="test.copy.first", grouping_id="test.copy",
            read_source=Enum_Read_Source.ORIGINAL, steps=(Callback_Step(_seed),),
        ))

        def _mutate(instance, _action, _context):
            instance.derived["values"][0] = 99

        second = W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
            declaration_id="test.copy.second", grouping_id="test.copy",
            read_source=Enum_Read_Source.ORIGINAL, steps=(Callback_Step(_mutate),),
        ))
        self.assertEqual(int(first.derived["values"][0]), 1)
        self.assertEqual(int(second.derived["values"][0]), 99)

    def test_grouping_is_isolated_by_object(self):
        """The same grouping_id used on two different objects must not leak derived data between them."""
        first_obj = create_test_mesh_object("group_a")
        second_obj = create_test_mesh_object("group_b")

        def _seed(instance, _action, _context):
            instance.derived["only_first"] = True

        W.run_geometry_action_for_object(first_obj, Geometry_Actions_Declaration(
            declaration_id="test.object.first", grouping_id="test.object-group",
            read_source=Enum_Read_Source.ORIGINAL, steps=(Callback_Step(_seed),),
        ))
        second = W.run_geometry_action_for_object(second_obj, Geometry_Actions_Declaration(
            declaration_id="test.object.second", grouping_id="test.object-group",
            read_source=Enum_Read_Source.ORIGINAL,
        ))
        self.assertNotIn("only_first", second.derived)


# ==============================================================================================================================
# CURVES
# ==============================================================================================================================

class Test_Curves(_Base):

    def test_native_curve_reads(self):
        """Native curve-point and curve-count reads must produce a valid CURVES-type result."""
        obj = create_test_curve_object()
        if obj is None:
            self.skipTest("This Blender build has no Curves object support.")

        declaration = Geometry_Actions_Declaration(
            declaration_id  = "test.curve",
            read_source     = Enum_Read_Source.ORIGINAL,
            geometry_target = Enum_Geometry_Target.NATIVE_DATA,
            steps           = (
                Read_Step(CET.POINT.POSITION),
                Read_Step(CET.CURVE.POINTS_LENGTH),
            ),
        )
        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertTrue(result.is_valid, result.error_str)
        self.assertEqual(result.geometry_type, Enum_Geometry_Type.CURVES)
        self.assertEqual(result.point.count, 3)
        self.assertEqual(result.curve.count, 1)
        self.assertEqual(result.point.position.shape, (3, 3))

    def test_curve_custom_attribute_round_trip(self):
        """A custom curve-point attribute written via a callback must be readable back with the same values."""
        obj = create_test_curve_object()
        if obj is None:
            self.skipTest("This Blender build has no Curves object support.")

        attr = CET.POINT.CUSTOM_ATTRIBUTE("test_p", data_type="FLOAT")

        def _write_it(instance, action, context):
            context.write_attr(attr, np.array([1.0, 2.0, 3.0], dtype="float32"))

        declaration = Geometry_Actions_Declaration(
            declaration_id  = "test.curve_attr",
            read_source     = Enum_Read_Source.ORIGINAL,
            geometry_target = Enum_Geometry_Target.NATIVE_DATA,
            steps           = (
                Read_Step(CET.POINT.POSITION),
                Callback_Step(_write_it),
                Read_Step(attr),
            ),
        )
        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertTrue(result.is_valid, result.error_str)
        np.testing.assert_allclose(result.point.custom["test_p"], [1.0, 2.0, 3.0])


# ==============================================================================================================================
# SERIALIZATION
# ==============================================================================================================================

class Test_Serialization(_Base):

    def test_mesh_round_trip_with_custom_attribute(self):
        """Serializing a mesh with a custom attribute and applying it to another object must reproduce the geometry and attribute."""
        source = create_test_mesh_object("src")
        add_named_attribute(source, "test_f", "FACE", "INT", [42])
        target = create_test_mesh_object("dst")

        serialized = W.serialize_object_geometry(source)
        self.assertIsInstance(serialized, str)

        header = W.inspect_serialized_geometry(serialized)
        self.assertEqual(header["counts"]["VERTEX"], 4)

        W.apply_serialized_geometry_to_object(target, serialized)
        self.assertEqual(len(target.data.vertices), 4)
        self.assertEqual(len(target.data.polygons), 1)
        self.assertIn("test_f", target.data.attributes)
        self.assertEqual(target.data.attributes["test_f"].data[0].value, 42)

    def test_serialize_callback_stores_in_derived(self):
        """The built-in serialize callback must store its payload under the documented derived key."""
        obj = create_test_mesh_object()
        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.serialize",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (Callback_Step(CB.cb_serialize_geometry),),
        )
        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertTrue(result.is_valid, result.error_str)
        self.assertTrue(result.derived[DERIVED_KEY_SERIALIZED])

    def test_malformed_payload_raises(self):
        """Applying a malformed/non-payload string to an object must raise, not silently no-op."""
        obj = create_test_mesh_object()
        with self.assertRaises(Exception):
            W.apply_serialized_geometry_to_object(obj, "not-a-payload")


# ==============================================================================================================================
# SUITE
# ==============================================================================================================================

def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for test_case in (
        Test_Mesh_Reads,
        Test_Callbacks_And_Writes,
        Test_Storage_And_Grouping,
        Test_Curves,
        Test_Serialization,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

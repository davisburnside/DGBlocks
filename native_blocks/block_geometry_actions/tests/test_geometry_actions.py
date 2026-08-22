"""
test_geometry_actions.py — unittest suite covering the block's major features.

Run from the Blender Text Editor / Python Console:

    from DGBlocks.native_blocks.block_geometry_actions.tests import run_tests
    run_tests.run()

Or headless:

    blender --background --python <addon>/native_blocks/block_geometry_actions/tests/run_tests.py

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

    def test_missing_attribute_fails_only_that_op(self):
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
        obj = create_test_mesh_object()

        def _boom(instance, action, context):
            raise ValueError("intentional")

        declaration = Geometry_Actions_Declaration(
            declaration_id = "test.boom",
            read_source    = Enum_Read_Source.ORIGINAL,
            steps          = (Read_Step(MET.VERTEX.CO), Callback_Step(_boom)),
        )
        result = W.run_geometry_action_for_object(obj, declaration)
        self.assertFalse(result.is_valid)
        self.assertIsNotNone(result.error_str)
        self.assertIsNotNone(result.vertex.co)          # pre-failure data retained


# ==============================================================================================================================
# STORAGE / GROUPING
# ==============================================================================================================================

class Test_Storage_And_Grouping(_Base):

    def test_same_id_replaces_previous_run_and_keeps_new_run_number(self):
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
        obj = create_test_mesh_object()
        for declaration_id in ("test.one", "test.two"):
            W.run_geometry_action_for_object(obj, Geometry_Actions_Declaration(
                declaration_id=declaration_id,
                read_source=Enum_Read_Source.ORIGINAL,
            ))
        self.assertEqual(len(W.get_all_results()), 2)

    def test_same_id_is_stored_separately_for_each_object(self):
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

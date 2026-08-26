"""
test_pure_math.py — pure numpy/math helpers that never touch bpy/gpu state at call time (the
containing modules still need bpy importable to load at all, like everything else in this
addon): polyline_geometry_utils' shared segment-quad math, and animations.engine._lerp.
Currently untested despite backing every custom polyline/animated shader in this block.
"""

import unittest

import numpy as np

from ..animations.engine import _lerp
from ..builtin_shaders_and_effects.polyline_geometry_utils import segment_quad_corner_attrs, segment_quad_indices


class Test_Segment_Quad_Indices(unittest.TestCase):
    def test_zero_offset(self):
        self.assertEqual(segment_quad_indices(0), ((0, 1, 2), (2, 1, 3)))

    def test_nonzero_offset_shifts_every_index(self):
        self.assertEqual(segment_quad_indices(8), ((8, 9, 10), (10, 9, 11)))


class Test_Segment_Quad_Corner_Attrs(unittest.TestCase):
    def test_all_four_corners_match_the_documented_layout(self):
        expected = [(0.0, 1.0), (0.0, -1.0), (1.0, 1.0), (1.0, -1.0)]
        actual = [segment_quad_corner_attrs(None, None, i) for i in range(4)]
        self.assertEqual(actual, expected)


class Test_Lerp(unittest.TestCase):
    def test_halfway_scalar(self):
        self.assertAlmostEqual(_lerp(0.0, 10.0, 0.5), 5.0, places=5)

    def test_t_zero_returns_start(self):
        self.assertAlmostEqual(_lerp(2.0, 8.0, 0.0), 2.0, places=5)

    def test_t_one_returns_end(self):
        self.assertAlmostEqual(_lerp(2.0, 8.0, 1.0), 8.0, places=5)

    def test_vector_interpolation(self):
        result = _lerp((0.0, 0.0, 0.0), (2.0, 4.0, 6.0), 0.5)
        np.testing.assert_allclose(result, (1.0, 2.0, 3.0), atol=1e-5)

    def test_falls_back_to_end_on_unconvertible_input_when_t_is_high(self):
        self.assertEqual(_lerp("bad", "also bad", 1.0), "also bad")


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Segment_Quad_Indices, Test_Segment_Quad_Corner_Attrs, Test_Lerp):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

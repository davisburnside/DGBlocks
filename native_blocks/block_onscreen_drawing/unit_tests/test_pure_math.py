"""
test_pure_math.py — pure numpy/math helpers that never touch bpy/gpu state at call time (the
containing modules still need bpy importable to load at all, like everything else in this
addon): polyline_geometry_utils' shared segment-quad math, and animations.engine._lerp /
_ease_out_bounce / _ease_out_back / _ease_out_elastic / _apply_easing.
Currently untested despite backing every custom polyline/animated shader in this block.
"""

import unittest

import numpy as np

from ..animations.constants import ANIM_VALID_EASINGS
from ..animations.engine import _apply_easing, _ease_out_back, _ease_out_bounce, _ease_out_elastic, _lerp
from ..builtin_shaders_and_effects.polyline_geometry_utils import segment_quad_corner_attrs, segment_quad_indices


class Test_Segment_Quad_Indices(unittest.TestCase):
    def test_zero_offset(self):
        """With no offset, a segment quad's two triangles use the base (0,1,2)/(2,1,3) indices."""
        self.assertEqual(segment_quad_indices(0), ((0, 1, 2), (2, 1, 3)))

    def test_nonzero_offset_shifts_every_index(self):
        """A non-zero offset must shift every index in both triangles by exactly that amount."""
        self.assertEqual(segment_quad_indices(8), ((8, 9, 10), (10, 9, 11)))


class Test_Segment_Quad_Corner_Attrs(unittest.TestCase):
    def test_all_four_corners_match_the_documented_layout(self):
        """The 4 corner indices must map to the (end_flag, side) pairs documented in SEGMENT_CORNERS."""
        expected = [(0.0, 1.0), (0.0, -1.0), (1.0, 1.0), (1.0, -1.0)]
        actual = [segment_quad_corner_attrs(None, None, i) for i in range(4)]
        self.assertEqual(actual, expected)


class Test_Lerp(unittest.TestCase):
    def test_halfway_scalar(self):
        """Interpolating two scalars at t=0.5 must return their midpoint."""
        self.assertAlmostEqual(_lerp(0.0, 10.0, 0.5), 5.0, places=5)

    def test_t_zero_returns_start(self):
        """t=0.0 must return the start value unchanged."""
        self.assertAlmostEqual(_lerp(2.0, 8.0, 0.0), 2.0, places=5)

    def test_t_one_returns_end(self):
        """t=1.0 must return the end value unchanged."""
        self.assertAlmostEqual(_lerp(2.0, 8.0, 1.0), 8.0, places=5)

    def test_vector_interpolation(self):
        """Interpolation must work element-wise on vector (tuple/array) operands, not just scalars."""
        result = _lerp((0.0, 0.0, 0.0), (2.0, 4.0, 6.0), 0.5)
        np.testing.assert_allclose(result, (1.0, 2.0, 3.0), atol=1e-5)

    def test_falls_back_to_end_on_unconvertible_input_when_t_is_high(self):
        """Operands that can't convert to a float32 array must fall back to returning `end` when t >= 1.0."""
        self.assertEqual(_lerp("bad", "also bad", 1.0), "also bad")


class Test_Ease_Out_Bounce(unittest.TestCase):
    def test_t_zero_returns_zero(self):
        """t=0.0 must return 0.0 — the bounce starts exactly at the start state."""
        self.assertAlmostEqual(_ease_out_bounce(0.0), 0.0, places=5)

    def test_t_one_returns_one(self):
        """t=1.0 must land exactly on 1.0 — the bounce always settles on the end state."""
        self.assertAlmostEqual(_ease_out_bounce(1.0), 1.0, places=5)

    def test_stays_within_unit_range(self):
        """A bounce overshoots visually but the eased t itself must never leave [0, 1]."""
        for t in np.linspace(0.0, 1.0, 101):
            eased = _ease_out_bounce(float(t))
            self.assertGreaterEqual(eased, 0.0)
            self.assertLessEqual(eased, 1.0)


class Test_Ease_Out_Back(unittest.TestCase):
    def test_t_zero_returns_zero(self):
        """t=0.0 must return 0.0 — the curve starts exactly at the start state."""
        self.assertAlmostEqual(_ease_out_back(0.0), 0.0, places=5)

    def test_t_one_returns_one(self):
        """t=1.0 must land exactly on 1.0."""
        self.assertAlmostEqual(_ease_out_back(1.0), 1.0, places=5)

    def test_overshoots_past_one_before_settling(self):
        """'Back' easing is defined by overshooting past the end value before settling on it."""
        peak = max(_ease_out_back(float(t)) for t in np.linspace(0.5, 1.0, 50))
        self.assertGreater(peak, 1.0)


class Test_Ease_Out_Elastic(unittest.TestCase):
    def test_t_zero_returns_zero(self):
        """t=0.0 must return 0.0 — the curve starts exactly at the start state."""
        self.assertAlmostEqual(_ease_out_elastic(0.0), 0.0, places=5)

    def test_t_one_returns_one(self):
        """t=1.0 must land exactly on 1.0."""
        self.assertAlmostEqual(_ease_out_elastic(1.0), 1.0, places=5)

    def test_oscillates_past_one_before_settling(self):
        """Elastic easing must overshoot past 1.0 at least once en route to settling there."""
        values = [_ease_out_elastic(float(t)) for t in np.linspace(0.0, 1.0, 200)]
        self.assertTrue(any(v > 1.0 for v in values))


class Test_Apply_Easing(unittest.TestCase):
    def test_linear_is_identity(self):
        """'linear' must pass t through unchanged."""
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            self.assertAlmostEqual(_apply_easing('linear', t), t, places=5)

    def test_unknown_easing_falls_back_to_linear(self):
        """An unrecognized easing name must not raise — it degrades to linear."""
        self.assertAlmostEqual(_apply_easing('not_a_real_easing', 0.5), 0.5, places=5)

    def test_ease_out_bounce_dispatches_to_the_bounce_curve(self):
        """'ease_out_bounce' must route through _ease_out_bounce, not linear."""
        self.assertAlmostEqual(_apply_easing('ease_out_bounce', 0.5), _ease_out_bounce(0.5), places=5)

    def test_every_valid_easing_starts_at_zero_and_ends_at_one(self):
        """Every member of ANIM_VALID_EASINGS (the easings.net 'essentials' subset) must map
        t=0 -> 0 and t=1 -> 1 — only the path between the two endpoints differs."""
        for easing in ANIM_VALID_EASINGS:
            self.assertAlmostEqual(_apply_easing(easing, 0.0), 0.0, places=5, msg=easing)
            self.assertAlmostEqual(_apply_easing(easing, 1.0), 1.0, places=5, msg=easing)


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (
        Test_Segment_Quad_Indices, Test_Segment_Quad_Corner_Attrs, Test_Lerp,
        Test_Ease_Out_Bounce, Test_Ease_Out_Back, Test_Ease_Out_Elastic, Test_Apply_Easing,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

"""
test_data_sync_tools.py — covers the pure diff algorithm every block's BL<->RTC data mirror
depends on: plan_dataclasses_to_match_collectionprop / plan_collectionprop_to_match_dataclasses
(both are thin wrappers over the same _plan_sync, so testing one direction covers both).

Strategy: rather than asserting on the exact Action sequence (an implementation detail —
how many Moves it takes to reconcile a reorder isn't a contract anyone depends on), each test
applies the computed actions to a plain-list simulation of `target` and asserts the end state
matches `source` by (key, data) in order. That's the actual contract: "after applying these
actions, target looks like source." A bug that produces a *different* but still-correct
action sequence would wrongly fail an exact-sequence assertion; this catches only real bugs.
"""

import copy
import unittest
from dataclasses import dataclass, field

from ..core_features.runtime_cache.data_sync_tools import (
    Create,
    Edit,
    Move,
    Noop,
    Remove,
    plan_dataclasses_to_match_collectionprop,
)

KEY_FIELDS = ["uid"]
DATA_FIELDS = ["value"]


@dataclass
class _Row:
    uid: str
    value: int = 0


def _apply(target: list, source: list, actions: list) -> list:
    """Mirrors apply_dataclasses_to_match_collectionprop's semantics against a plain list."""
    target = list(target)
    for action in actions:
        if isinstance(action, Remove):
            target.pop(action.from_idx)
        elif isinstance(action, Noop):
            pass
        elif isinstance(action, Edit):
            src = source[action.source_idx]
            for name in DATA_FIELDS:
                setattr(target[action.idx], name, getattr(src, name))
        elif isinstance(action, Move):
            item = target.pop(action.from_idx)
            target.insert(action.to_idx, item)
        elif isinstance(action, Create):
            target.insert(action.to_idx, copy.deepcopy(source[action.source_idx]))
    return target


def _as_key_value_pairs(rows: list) -> list:
    return [(r.uid, r.value) for r in rows]


class Test_Plan_Sync_Round_Trip(unittest.TestCase):
    """For every scenario: plan, apply, and assert target now equals source exactly."""

    def _assert_reconciles(self, source: list, target: list):
        actions = plan_dataclasses_to_match_collectionprop(source, target, KEY_FIELDS, DATA_FIELDS)
        result = _apply(target, source, actions)
        self.assertEqual(_as_key_value_pairs(result), _as_key_value_pairs(source))
        return actions

    def test_identical_lists_are_all_noop(self):
        """Source and target already match by key and data -> every action is a Noop."""
        source = [_Row("a", 1), _Row("b", 2)]
        target = [_Row("a", 1), _Row("b", 2)]
        actions = self._assert_reconciles(source, target)
        self.assertTrue(all(isinstance(a, Noop) for a in actions))

    def test_empty_target_is_all_creates(self):
        """An empty target reconciled against a populated source produces only Create actions."""
        source = [_Row("a", 1), _Row("b", 2)]
        actions = self._assert_reconciles(source, target=[])
        self.assertTrue(all(isinstance(a, Create) for a in actions))
        self.assertEqual(len(actions), 2)

    def test_empty_source_is_all_removes(self):
        """An empty source reconciled against a populated target produces only Remove actions."""
        target = [_Row("a", 1), _Row("b", 2)]
        actions = self._assert_reconciles(source=[], target=target)
        self.assertTrue(all(isinstance(a, Remove) for a in actions))
        self.assertEqual(len(actions), 2)

    def test_removes_are_descending_by_from_idx(self):
        """Removes must be emitted highest-index-first, so each from_idx stays valid against a live list."""
        target = [_Row("a", 1), _Row("b", 2), _Row("c", 3)]
        actions = plan_dataclasses_to_match_collectionprop([], target, KEY_FIELDS, DATA_FIELDS)
        from_idxs = [a.from_idx for a in actions]
        self.assertEqual(from_idxs, sorted(from_idxs, reverse=True))

    def test_reorder_only(self):
        """Same keys and data, different order -> reconciles to source's order."""
        source = [_Row("b", 2), _Row("a", 1)]
        target = [_Row("a", 1), _Row("b", 2)]
        self._assert_reconciles(source, target)

    def test_data_change_same_position_is_edit(self):
        """Same key at the same position but a changed data field -> a single Edit action."""
        source = [_Row("a", 99)]
        target = [_Row("a", 1)]
        actions = self._assert_reconciles(source, target)
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], Edit)

    def test_reorder_and_edit_combined(self):
        """An item both moves position and changes data in the same plan -> still reconciles."""
        source = [_Row("b", 20), _Row("a", 1)]
        target = [_Row("a", 1), _Row("b", 2)]
        self._assert_reconciles(source, target)

    def test_mixed_create_remove_and_reorder(self):
        """One item added, one removed, remainder reordered, all in a single plan -> still reconciles."""
        source = [_Row("c", 3), _Row("a", 1), _Row("d", 4)]
        target = [_Row("a", 1), _Row("b", 2), _Row("c", 3)]
        self._assert_reconciles(source, target)

    def test_duplicate_key_in_source_raises(self):
        """Two source items sharing the same key is an input error, not a valid diff to compute."""
        source = [_Row("a", 1), _Row("a", 2)]
        with self.assertRaises(ValueError):
            plan_dataclasses_to_match_collectionprop(source, [], KEY_FIELDS, DATA_FIELDS)

    def test_duplicate_key_in_target_raises(self):
        """Two target items sharing the same key is an input error, not a valid diff to compute."""
        target = [_Row("a", 1), _Row("a", 2)]
        with self.assertRaises(ValueError):
            plan_dataclasses_to_match_collectionprop([], target, KEY_FIELDS, DATA_FIELDS)

    def test_unsupported_key_type_raises(self):
        """Key fields must be str/bool/int — a float key field must be rejected, not silently accepted."""
        @dataclass
        class _Float_Keyed:
            uid: float
            value: int = 0

        source = [_Float_Keyed(1.5)]
        with self.assertRaises(TypeError):
            plan_dataclasses_to_match_collectionprop(source, [], ["uid"], ["value"])


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(Test_Plan_Sync_Round_Trip))
    return suite

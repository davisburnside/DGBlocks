"""
test_modal_events.py — pure validation/classification/id-expansion logic:
validate_listener_definitions, classify_event, workspace_tools._validate_definitions +
_concrete_tool_id, and the Modal_Listener_End_Info snapshot dataclass. No modal router is
started and no real listener is registered anywhere in this suite — see §9's rule against
touching live repoll()-equivalent machinery from a test.
"""

import dataclasses
import unittest

from ..data_structures import Modal_Listener_Definition, Modal_Listener_End_Info, Workspace_Tool_Definition, Workspace_Tool_Placement
from ..helpers import classify_event, validate_listener_definitions
from ..workspace_tools import _concrete_tool_id, _validate_definitions


class _Fake_Event:
    def __init__(self, event_type):
        self.type = event_type


def _noop_on_event(listener_instance, context, event):
    return None


class Test_Validate_Listener_Definitions(unittest.TestCase):
    def test_at_most_one_definition_per_block(self):
        """A block returning more than one Modal_Listener_Definition must be rejected — one listener per block."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(), Modal_Listener_Definition()]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_on_event_must_be_callable(self):
        """A definition whose on_event is not callable must be rejected."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event="not_callable")]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_single_valid_definition_passes(self):
        """One block with one definition and a callable on_event is valid."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event)]}
        validate_listener_definitions(defs_by_block)  # must not raise

    def test_before_modal_start_must_be_callable_when_provided(self):
        """A non-callable before_modal_start (not None) must be rejected."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, before_modal_start="not_callable")]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_before_modal_end_must_be_callable_when_provided(self):
        """A non-callable before_modal_end (not None) must be rejected."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, before_modal_end="not_callable")]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_none_before_modal_hooks_are_allowed(self):
        """Leaving before_modal_start/end at their default None must be valid — they're optional."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event)]}
        validate_listener_definitions(defs_by_block)  # must not raise

    def test_non_int_priority_is_rejected(self):
        """A non-int priority must be rejected — it drives dispatch ordering."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, priority="high")]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_bool_priority_is_rejected(self):
        """A bool priority must be rejected even though bool is technically an int subclass in Python."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, priority=True)]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_bare_string_workspace_tool_ids_is_rejected(self):
        """A bare string for workspace_tool_ids must be rejected — it would iterate as characters elsewhere."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, workspace_tool_ids="my.tool")]}
        with self.assertRaises(ValueError):
            validate_listener_definitions(defs_by_block)

    def test_tuple_workspace_tool_ids_is_accepted(self):
        """A proper tuple of tool ids for workspace_tool_ids must be accepted."""
        defs_by_block = {"block-a": [Modal_Listener_Definition(on_event=_noop_on_event, workspace_tool_ids=("my.tool",))]}
        validate_listener_definitions(defs_by_block)  # must not raise

    def test_empty_dict_passes(self):
        """No blocks subscribing at all is trivially valid."""
        validate_listener_definitions({})  # must not raise


class Test_Classify_Event(unittest.TestCase):
    def test_mouse_move_types(self):
        """MOUSEMOVE must classify as the MOUSE_MOVE category."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("MOUSEMOVE")), Modal_Event_Category.MOUSE_MOVE)

    def test_mouse_click_types(self):
        """LEFTMOUSE must classify as the MOUSE_CLICK category."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("LEFTMOUSE")), Modal_Event_Category.MOUSE_CLICK)

    def test_scroll_types(self):
        """WHEELUPMOUSE must classify as the SCROLL category."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("WHEELUPMOUSE")), Modal_Event_Category.SCROLL)

    def test_window_types(self):
        """WINDOW_DEACTIVATE must classify as the WINDOW category."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("WINDOW_DEACTIVATE")), Modal_Event_Category.WINDOW)

    def test_keyboard_falls_through_to_keyboard_category(self):
        """Any event type not matching a known non-keyboard type falls through to KEYBOARD."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("A")), Modal_Event_Category.KEYBOARD)

    def test_timer_and_ndof_are_other(self):
        """TIMER and NDOF_MOTION are explicitly excluded from KEYBOARD and classify as OTHER."""
        from ..data_structures import Modal_Event_Category
        self.assertEqual(classify_event(_Fake_Event("TIMER")), Modal_Event_Category.OTHER)
        self.assertEqual(classify_event(_Fake_Event("NDOF_MOTION")), Modal_Event_Category.OTHER)


class Test_Workspace_Tool_Validation(unittest.TestCase):
    def test_non_namespaced_tool_id_is_rejected(self):
        """A tool_id with no '.' separator is not namespaced and must be rejected."""
        defs = {"block-a": [Workspace_Tool_Definition(
            tool_id="notnamespaced", label="Test", placements=(Workspace_Tool_Placement(),),
        )]}
        with self.assertRaises(ValueError):
            _validate_definitions(defs)

    def test_duplicate_logical_tool_id_is_rejected(self):
        """Two definitions (even from different blocks) sharing the same logical tool_id must be rejected."""
        defs = {"block-a": [
            Workspace_Tool_Definition(tool_id="test.tool", label="A", placements=(Workspace_Tool_Placement(),)),
            Workspace_Tool_Definition(tool_id="test.tool", label="B", placements=(Workspace_Tool_Placement(),)),
        ]}
        with self.assertRaises(ValueError):
            _validate_definitions(defs)

    def test_no_placements_is_rejected(self):
        """A tool definition with zero placements has nowhere to appear and must be rejected."""
        defs = {"block-a": [Workspace_Tool_Definition(tool_id="test.tool", label="A", placements=())]}
        with self.assertRaises(ValueError):
            _validate_definitions(defs)

    def test_duplicate_concrete_placement_is_rejected(self):
        """The same (tool_id, placement) pair appearing twice would collide on registration and must be rejected."""
        placement = Workspace_Tool_Placement("VIEW_3D", "OBJECT")
        defs = {"block-a": [Workspace_Tool_Definition(
            tool_id="test.tool", label="A", placements=(placement, placement),
        )]}
        with self.assertRaises(ValueError):
            _validate_definitions(defs)

    def test_valid_multi_placement_definition_expands_to_deterministic_ids(self):
        """One logical tool with two placements expands to two deterministic, stable concrete ids."""
        decl = Workspace_Tool_Definition(
            tool_id="test.tool", label="Test",
            placements=(Workspace_Tool_Placement("VIEW_3D", "OBJECT"), Workspace_Tool_Placement("VIEW_3D", "EDIT_MESH")),
        )
        flattened = _validate_definitions({"block-a": [decl]})
        self.assertEqual(len(flattened), 1)
        ids = [_concrete_tool_id(decl.tool_id, p) for p in decl.placements]
        self.assertEqual(ids, ["test.tool.view_3d.object", "test.tool.view_3d.edit_mesh"])


class Test_Listener_End_Info_Snapshot(unittest.TestCase):
    def test_snapshot_is_immutable(self):
        """Modal_Listener_End_Info is frozen — mutating a field after construction must raise."""
        info = Modal_Listener_End_Info(
            src_block_id="test", priority=0, is_enabled=True, workspace_tool_ids=(),
            event_count=0, last_return=None, modal_start_timestamp=0.0,
            last_event_timestamp=0.0, listener_error_str=None,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            info.event_count = 5


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (
        Test_Validate_Listener_Definitions,
        Test_Classify_Event,
        Test_Workspace_Tool_Validation,
        Test_Listener_End_Info_Snapshot,
    ):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

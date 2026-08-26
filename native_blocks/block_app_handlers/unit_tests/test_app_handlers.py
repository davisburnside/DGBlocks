"""
test_app_handlers.py — merge_handler_subscriptions (pure, extracted from
Wrapper_App_Handlers.repoll() specifically so it could be tested without touching
bpy.app.handlers) and RTC_App_Handler_Status_Instance's defaults.
"""

import unittest

from ..data_structures import App_Handler_Subscription_Declaration, App_Handler_Type, RTC_App_Handler_Status_Instance
from ..feature_app_handlers import merge_handler_subscriptions


class Test_Merge_Handler_Subscriptions(unittest.TestCase):
    def test_single_subscriber_is_passed_through(self):
        """One block subscribing to one handler type produces exactly that count and frequency."""
        raw = {"block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.save_pre, 0.5)]}
        merged = merge_handler_subscriptions(raw)
        self.assertEqual(merged["save_pre"], {"subscriber_count": 1, "min_freq": 0.5})

    def test_two_subscribers_merge_to_minimum_frequency(self):
        """When two blocks subscribe to the same handler type, the merged frequency is the minimum of the two."""
        raw = {
            "block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.frame_change_post, 0.5)],
            "block-b": [App_Handler_Subscription_Declaration(App_Handler_Type.frame_change_post, 0.1)],
        }
        merged = merge_handler_subscriptions(raw)
        self.assertEqual(merged["frame_change_post"]["min_freq"], 0.1)
        self.assertEqual(merged["frame_change_post"]["subscriber_count"], 2)

    def test_different_types_are_tracked_independently(self):
        """Two distinct handler types from the same block must produce two independent merge entries."""
        raw = {"block-a": [
            App_Handler_Subscription_Declaration(App_Handler_Type.save_pre),
            App_Handler_Subscription_Declaration(App_Handler_Type.save_post),
        ]}
        merged = merge_handler_subscriptions(raw)
        self.assertEqual(set(merged.keys()), {"save_pre", "save_post"})

    def test_non_list_return_is_skipped_not_raised(self):
        """A block whose poll hook returns something other than a list is skipped, never raises."""
        merged = merge_handler_subscriptions({"block-a": "not-a-list"})
        self.assertEqual(merged, {})

    def test_non_declaration_item_is_skipped_not_raised(self):
        """A list item that isn't an App_Handler_Subscription_Declaration is skipped, never raises."""
        merged = merge_handler_subscriptions({"block-a": [object(), 42]})
        self.assertEqual(merged, {})

    def test_empty_raw_results_produce_empty_merge(self):
        """No subscribers at all merges to an empty dict."""
        self.assertEqual(merge_handler_subscriptions({}), {})

    def test_invalid_handler_type_is_skipped_not_raised(self):
        """A handler_type that isn't a real App_Handler_Type member is skipped, never raises."""
        # A plausible-looking string in place of the actual enum member — dataclasses don't
        # enforce their own type hints at runtime, so this constructs without error.
        bad = App_Handler_Subscription_Declaration(handler_type="save_pre", frequency_filter_seconds=0.0)
        merged = merge_handler_subscriptions({"block-a": [bad]})
        self.assertEqual(merged, {})

    def test_negative_frequency_is_skipped_not_raised(self):
        """A negative frequency_filter_seconds is nonsensical and must be skipped, never raised."""
        raw = {"block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.save_pre, -1.0)]}
        self.assertEqual(merge_handler_subscriptions(raw), {})

    def test_non_numeric_frequency_is_skipped_not_raised(self):
        """A non-numeric frequency_filter_seconds must be skipped, never raised or silently coerced."""
        raw = {"block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.save_pre, "fast")]}
        self.assertEqual(merge_handler_subscriptions(raw), {})

    def test_bool_frequency_is_skipped_not_raised(self):
        """A bool frequency_filter_seconds must be rejected even though bool is an int subclass in Python."""
        raw = {"block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.save_pre, True)]}
        self.assertEqual(merge_handler_subscriptions(raw), {})

    def test_zero_frequency_is_accepted(self):
        """A frequency of exactly 0.0 (no rate limit) is valid and must be accepted."""
        raw = {"block-a": [App_Handler_Subscription_Declaration(App_Handler_Type.save_pre, 0.0)]}
        merged = merge_handler_subscriptions(raw)
        self.assertEqual(merged["save_pre"]["min_freq"], 0.0)


class Test_RTC_App_Handler_Status_Instance_Defaults(unittest.TestCase):
    def test_new_instance_starts_unregistered_and_enabled(self):
        """A freshly constructed status record starts disconnected from bpy but enabled by default."""
        instance = RTC_App_Handler_Status_Instance(handler_type_name="save_pre")
        self.assertFalse(instance.is_registered)
        self.assertTrue(instance.is_enabled)
        self.assertEqual(instance.fire_count, 0)
        self.assertEqual(instance.subscriber_count, 0)


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_case in (Test_Merge_Handler_Subscriptions, Test_RTC_App_Handler_Status_Instance_Defaults):
        suite.addTests(loader.loadTestsFromTestCase(test_case))
    return suite

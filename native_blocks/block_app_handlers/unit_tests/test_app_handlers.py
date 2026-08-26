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

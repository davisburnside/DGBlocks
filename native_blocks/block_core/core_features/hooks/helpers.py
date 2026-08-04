
from typing import Callable

from .....addon_helpers.generic_tools import force_redraw_ui

# Intra-block imports
from ...core_helpers.constants import  Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger

# Aliases
cache_key_blocks = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS
cache_key_hook_sources = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES
cache_key_hook_subscribers = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS

# ==============================================================================================================================
# HOOK DATA FILTER DECORATOR
# ==============================================================================================================================

_HOOK_DATA_FILTER_ATTR = "__hook_data_filter__"
def hook_data_filter(predicate: Callable[..., bool]):
    """
    Decorator. Attaches a data-filter predicate to a subscriber hook function.

    The predicate is evaluated at call time inside run_hooked_funcs, BEFORE the
    hook function itself is invoked. If the predicate returns False the call is
    skipped and counted as a 'bypass-via-data-filter'.

    Predicate signature:
        predicate(hook_metadata, **kwargs) -> bool

    Args:
        hook_metadata : RTC_Hook_Subscriber_Instance  — the live metadata record for this
                        hook/block pair.
        **kwargs      : The same keyword arguments that will be forwarded to the
                        hook function. Use **_ to absorb args you don't care about.

    Returns True  → proceed with the hook call.
    Returns False → skip (bypass-via-data-filter, counted separately).

    The decorated function is returned UNCHANGED — zero call-path overhead when
    the filter passes.
    """
    def decorator(func):
        setattr(func, _HOOK_DATA_FILTER_ATTR, predicate)
        return func  # function is NOT wrapped — no call-path overhead
    return decorator


def increment_bypass_count_of_subs(hook_source_instance, actual_hook_func_name):
    cached_hook_subs: dict = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)
    for hook_sub_instance in cached_hook_subs[actual_hook_func_name]:
        hook_sub_instance.count_bypass_via_status += 1


def _callback_hook_sub_uilist_selection_idx_updated(self, context):
    print("update list")


def _callback_hooks_hide_unsub_changed(self, context):
    """
    Fired when the "Hide hooks with no subscribers" checkbox is toggled.
    Forces a UI redraw so the filter_items callback re-runs immediately.
    """
    
    force_redraw_ui(context)

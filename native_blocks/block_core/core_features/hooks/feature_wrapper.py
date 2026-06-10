# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from collections import Counter, defaultdict
from enum import Enum
from typing import Any, Callable, Dict, Optional
import inspect
import time


# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .....addon_helpers.data_tools import get_actual_id
from .....addon_helpers.data_structures import Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager, Abstract_Feature_Wrapper, Enum_Sync_Events
from .....addon_helpers.generic_tools import find_blocks_owning_func_with_name
from .....addon_helpers.ui import set_shared_uilist_config

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache, get_actual_rtc_key
from ..loggers.feature_wrapper import get_logger
from .data_structures import RTC_Hook_Subscriber_Instance, RTC_Hook_Source_Instance
from .ui import _uilayout_draw_hooks_uilist_selection_detail

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
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

# ==============================================================================================================================
# MAIN MODULE FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Hooks(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_RTC_List_Syncronizer):
    # Manager — classmethods only, no instance state
    # Manages hook registrations and src->subscriber propagation between blocks
    # All data managed by this wrapper is stored in RTC

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_wrapper(cls):
        pass
        # set_shared_uilist_config(
        #     list_id="HOOKS_LIST",
        #     col_names=("Function Name", "Source Block", "Is Enabled?"),
        #     col_widths=(2, 2, 1),
        #     columns_def=[
        #         {"type": "LABEL", "field": "hook_func_name"},
        #         {"type": "LABEL", "field": "src_block_id"},
        #         {"type": "PROP", "field": "is_hook_enabled", "icon_only": True, "icon_true": "CHECKBOX_HLT", "icon_false": "CHECKBOX_DEHLT"}
        #     ],
        #     details_func=_uilayout_draw_hooks_uilist_selection_detail
        # )

    @classmethod
    def destroy_wrapper(cls):
        "No-op"

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    # @classmethod
    # def update_RTC_with_mirrored_BL_data(cls, event):
    #     pass


    # @classmethod
    # def update_BL_with_mirrored_RTC_data(cls, event):
    #     pass

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        src_block_id: str,
        hook_func_name: str | Enum,
        hook_func_named_args: Dict[str, Any] = None,
    ) -> None:

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug(f"Creating hook source '{hook_func_name}'")

        # # Validate uniqueness. Return with no action upon duplication attempt
        actual_hook_func_name = get_actual_rtc_key(hook_func_name)
        idx, existing_instance, cached_hook_sources = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(cache_key_hook_sources, "hook_func_name", actual_hook_func_name)
        if existing_instance:
            logger.debug(f"Hook source '{actual_hook_func_name}' already exists in RTC. Returning with no action")
            return

        # Create & cache new hook source
        hook_src_instance = RTC_Hook_Source_Instance(
            src_block_id,
            actual_hook_func_name,
            hook_func_named_args,
        )
        cached_hook_sources.append(hook_src_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_hook_sources, cached_hook_sources)

        return hook_src_instance


    @classmethod
    def destroy_instance(
        cls,
        event: Enum_Sync_Events,
        hook_func_name: str,
    ) -> None:
        """
        Remove hook source & derived subscribers
        """

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug(f"Removing hook source '{hook_func_name}'")

        # Remove source hook from registry
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key=cache_key_hook_sources,
            uniqueness_field="hook_func_name",
            uniqueness_field_value=hook_func_name,
        )

    # --------------------------------------------------------------
    # Public funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def run_hooked_funcs(
        cls,
        hook_func_name: any,
        subscriber_block_id: Optional[str] = None,
        should_halt_on_exception: bool = True,
        **kwargs,
    ) -> Any:
        """
        Trigger hook callbacks for all registered blocks with full rate-limiting and timing support.

        Args:
            hook_func_name: The hook function to call
            subscriber_block_id: If provided, only call this specific block's hook
            should_halt_on_exception: If True, re-raise exceptions
            **kwargs: Arguments passed to hook functions

        Returns:
            If subscriber_block_id: single return value
            Otherwise: dict of {block_id: return_value}
        """
        logger = get_logger(Core_Block_Loggers.HOOKS)
        all_returns: Dict[str, Any] = {}
        actual_hook_func_name = get_actual_id(hook_func_name)
        # RTC_subscriber_hooks = Wrapper_Runtime_Cache.get_all_with_key_value_from_registry_list(
        #     cache_key_hook_subscribers,
        #     key_field_name="hook_func_name",
        #     key_field_value=hook_func_name,
        # )

        cached_hook_subs = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)

        if actual_hook_func_name not in cached_hook_subs:
            logger.debug(f"No subscriber listeners found for hook '{actual_hook_func_name}'")
            return all_returns

        current_time_ms = int(time.time() * 1000)
        start_time_nanos = None
        end_time_nanos = None
        for hook_sub_instance in cached_hook_subs[actual_hook_func_name]:
            block_id = hook_sub_instance.subscriber_block_id
            if not hook_sub_instance.is_hook_enabled:
                continue

            # 1. Filter by subscriber block if specified
            if subscriber_block_id is not None and subscriber_block_id != block_id:
                continue

            # 2. Check bypass timeout/reset logic
            if hook_sub_instance.should_bypass_run and hook_sub_instance.max_ms_timout_for_bypass_reset > 0:
                time_since_last = current_time_ms - hook_sub_instance.timestamp_ms_last_attempt
                if time_since_last >= hook_sub_instance.max_ms_timout_for_bypass_reset:
                    hook_sub_instance.should_bypass_run = False
                    logger.debug(f"Reset bypass flag for hook '{actual_hook_func_name}' on block '{block_id}'")

            # 3. Check re-entrancy protection  [bypass-via-status]
            if hook_sub_instance.is_currently_running:
                hook_sub_instance.count_bypass_via_status += 1
                logger.debug(f"Skipping hook '{actual_hook_func_name}' on block '{block_id}' (re-entrancy protection)")
                continue

            # 4. Check rate limiting  [bypass-via-frequency]
            if hook_sub_instance.min_ms_between_runs > 0:
                time_since_last = current_time_ms - hook_sub_instance.timestamp_ms_last_attempt
                if time_since_last < hook_sub_instance.min_ms_between_runs:
                    hook_sub_instance.count_bypass_via_frequency += 1
                    logger.debug(f"Skipping hook '{actual_hook_func_name}' on block '{block_id}' (rate limited)")
                    continue

            # 5. Check @hook_data_filter predicate  [bypass-via-data-filter]
            if hook_sub_instance.arg_filter is not None:
                try:
                    should_run = hook_sub_instance.arg_filter(hook_sub_instance, **kwargs)
                except Exception:
                    logger.error(
                        f"arg_filter raised an exception for hook '{actual_hook_func_name}' on block '{block_id}' — skipping",
                        exc_info=True,
                    )
                    should_run = False
                if not should_run:
                    hook_sub_instance.count_bypass_via_data_filter += 1
                    logger.debug(f"Skipping hook '{actual_hook_func_name}' on block '{block_id}' (data filter)")
                    continue

            logger.debug(f"Calling hook '{actual_hook_func_name}' of subscriber block '{block_id}'")

            # 7. Execute with timing and re-entrancy protection
            start_time_nanos = time.time()  # recalculate right before func call
            hook_sub_instance.is_currently_running = True
            hook_sub_instance.timestamp_ms_last_attempt = start_time_nanos * 1000
            try:
                result = hook_sub_instance.actual_function(**kwargs)
                end_time_nanos = time.time()  # recalculate right after func call
                hook_sub_instance.count_hook_propagate_success += 1

                if subscriber_block_id is not None:
                    return result
                all_returns[block_id] = result

            except Exception as e:
                end_time_nanos = time.time()
                hook_sub_instance.count_hook_propagate_failure += 1
                logger.error(f"Exception when calling hook '{actual_hook_func_name}' of subscriber '{block_id}'", exc_info=True)
                if should_halt_on_exception:
                    raise e
                all_returns[block_id] = None

            finally:
                # Always reset running flag, even on exception
                hook_sub_instance.is_currently_running = False

                # Track execution time
                execution_time_nanos = end_time_nanos - start_time_nanos
                hook_sub_instance.total_nanos_running_time += execution_time_nanos

        return all_returns


    @classmethod
    def rebuild_hook_subs_cache(cls):
        """
        Rebuild REGISTRY_ALL_HOOK_SUBSCRIBERS from REGISTRY_ALL_HOOK_SOURCES and REGISTRY_ALL_BLOCKS.
        """
        
        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug("Rebuilding RTC Hook subscribers")

        cached_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        cached_hook_sources = Wrapper_Runtime_Cache.get_cache(cache_key_hook_sources)

        # Rebuild hook subs cache. This will reset all action counters.
        new_cached_hook_subs = defaultdict(list)
        for hook_source_instance in cached_hook_sources:
            func_name = hook_source_instance.hook_func_name
            block_instances = find_blocks_owning_func_with_name(func_name, cached_blocks, logger)
            for subbed_block_instance in block_instances:
                hook_func_ref = getattr(subbed_block_instance.block_module, func_name, None)
                arg_filter = getattr(hook_func_ref, _HOOK_DATA_FILTER_ATTR, None)
                subscriber_hook_instance = RTC_Hook_Subscriber_Instance(
                    src_block_id = hook_source_instance.src_block_id,
                    subscriber_block_id = subbed_block_instance.block_id,
                    subscriber_block_module = subbed_block_instance.block_module,
                    hook_func_named_args = hook_source_instance.hook_func_named_args,
                    arg_filter = arg_filter,
                    hook_func_name = func_name,
                    actual_function = hook_func_ref,
                    is_hook_enabled = True,
                )
                new_cached_hook_subs[func_name].append(subscriber_hook_instance)

        Wrapper_Runtime_Cache.set_cache(cache_key_hook_subscribers, dict(new_cached_hook_subs))

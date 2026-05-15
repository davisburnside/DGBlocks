# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from collections import Counter
from enum import Enum
from typing import Any, Callable, Dict, Optional
import inspect
import time

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .....addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_RTC_List_Syncronizer, Enum_Sync_Events, Enum_Sync_Actions, RTC_FWC_Data_Mirror_List_Reference, RTC_FWC_Instance
from .....addon_helpers.generic_tools import is_bpy_ready, find_blocks_owning_func_with_name

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members
from ...core_helpers.BL_RTC_data_sync_tools import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop, compare_unique_tuple_lists
from ..runtime_cache import Wrapper_Runtime_Cache
from ..loggers.feature_wrapper import get_logger
from .data_structures import RTC_Hook_Subscriber_Instance, RTC_Hook_Source_Instance, rtc_sync_key_fields, rtc_sync_data_fields

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
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> None:
        "no-op"
        return True

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events, self_FWC_instance: type[RTC_FWC_Instance]) -> None:

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Running post-bpy init for Wrapper_Hooks")

        # Setup the data mirror for Loggers, then store it directly inside this class's parent FWC instance
        # self_data_mirror_instance = RTC_FWC_Data_Mirror_List_Reference(
        #     RTC_key = cache_key_blocks,
        #     sync_key_field_names = rtc_sync_key_fields, 
        #     sync_data_field_names = rtc_sync_data_fields,
        #     default_BL_scene_child_propertygroup_path = "dgblocks_core_props.managed_blocks"
        # )
        # self_FWC_instance.data_mirror_lists.append(self_data_mirror_instance)

        # All hook sources from all blocks have been added by now. Rebuild Subscription cache from sources
        cls._rebuild_hook_subs_cache()

        # BL<->RTC 2-way sync, keeping user's saved hook settings if they exist
        cls.update_BL_with_mirrored_RTC_data(event=Enum_Sync_Events.ADDON_INIT)  # Causes partial RTC->BL sync
        cls.update_RTC_with_mirrored_BL_data(event=Enum_Sync_Events.ADDON_INIT)  # Causes full BL-RTC resync
        return True

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> None:
        "no-op"
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
        import bpy  # type: ignore
        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating hooks RTC with mirrored BL Data")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_hook_subs = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)
        scene_hook_subs = core_props.managed_hooks

        # BL->RTC Sync
        update_dataclasses_to_match_collectionprop(
            actual_FWC=Wrapper_Hooks,
            source=scene_hook_subs,
            target=cached_hook_subs,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=set(),
            debug_logger=debug_logger,
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):
        import bpy  # type: ignore
        core_props = bpy.context.scene.dgblocks_core_props
        logger = get_logger(Core_Block_Loggers.RTC_DATA_SYNC)
        logger.debug(f"Updating hooks BL data with mirrored RTC")
        debug_logger = logger if core_props.debug_log_all_RTC_BL_sync_actions else None

        # Sanity check before sync
        Wrapper_Runtime_Cache.asset_cache_is_not_syncing(cache_key_hook_subscribers, cls)

        # Get mirrored BL/RTC data (potentially de-synced)
        cached_hook_subs = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)
        scene_hook_subs = core_props.managed_hooks

        # During init, allow add/move/remove but not edit. This allows user choices to be reloaded after save
        actions_denied = set()
        if event == Enum_Sync_Events.ADDON_INIT:
            actions_denied = {Enum_Sync_Actions.EDIT}

        # RTC->BL Sync
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_hook_subscribers, True)
        update_collectionprop_to_match_dataclasses(
            source=cached_hook_subs,
            target=scene_hook_subs,
            key_fields=rtc_sync_key_fields,
            data_fields=rtc_sync_data_fields,
            actions_denied=actions_denied,
            debug_logger=debug_logger,
        )
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key_hook_subscribers, False)

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        event: Enum_Sync_Events,
        src_block_id: str,
        new_hook_func_id: any,
        new_hook_func_named_args: Dict[str, Any] = None,
        skip_BL_sync: bool = False,
        skip_subscriber_cache_rebuild: bool = False
    ) -> None:

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug(f"Creating hook source '{new_hook_func_id}'")

        # Get hook func name from str/enum input
        hook_func_name = cls._get_func_name_from_hook_id(new_hook_func_id)
        all_cached_hook_sources = Wrapper_Runtime_Cache.get_cache(cache_key_hook_sources)

        # Validate uniqueness. Return with no action upon duplication attempt
        if Wrapper_Runtime_Cache.cache_list_contains_member(all_cached_hook_sources, "hook_func_name", hook_func_name):
            logger.debug(f"Hook Source '{hook_func_name}' already exists in RTC. Returning with no action")
            return

        # Create new hook source instance & update runtime cache
        new_hook_source_instance = RTC_Hook_Source_Instance(
            src_block_id,
            hook_func_name,
            new_hook_func_named_args,
        )
        all_cached_hook_sources.append(new_hook_source_instance)
        Wrapper_Runtime_Cache.set_cache(cache_key_hook_sources, all_cached_hook_sources)

        # Update subscribers
        if not skip_subscriber_cache_rebuild:
            cls._rebuild_hook_subs_cache()

        # Add hook data from Blender file
        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event=Enum_Sync_Events.PROPERTY_UPDATE)

    @classmethod
    def destroy_instance(
        cls,
        event: Enum_Sync_Events,
        hook_func_name: str,
        subscriber_block_id: Optional[str] = None,
        skip_BL_sync: bool = False,
        skip_subscriber_cache_rebuild: bool = False,
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

        # Rebuild subscribers after updating sources
        if not skip_subscriber_cache_rebuild:
            cls._rebuild_hook_subs_cache()

        # Remove hook data from Blender file
        if is_bpy_ready() and not skip_BL_sync:
            cls.update_BL_with_mirrored_RTC_data(event)

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

        # Get hook func name from str/enum input
        hook_func_name = cls._get_func_name_from_hook_id(hook_func_name)

        RTC_subscriber_hooks = Wrapper_Runtime_Cache.get_all_with_key_value_from_registry_list(
            cache_key_hook_subscribers,
            key_field_name="hook_func_name",
            key_field_value=hook_func_name,
        )

        if len(RTC_subscriber_hooks) == 0:
            logger.debug(f"No subscriber listeners found for hook '{hook_func_name}'")
            return all_returns

        current_time_ms = int(time.time() * 1000)
        start_time_nanos = None
        end_time_nanos = None
        for instance in RTC_subscriber_hooks:
            block_module = instance.subscriber_block_module
            block_id = block_module._BLOCK_ID
            if not instance.is_hook_enabled:
                continue

            # 1. Filter by subscriber block if specified
            if subscriber_block_id is not None and subscriber_block_id != block_id:
                continue

            # 2. Check bypass timeout/reset logic
            if instance.should_bypass_run and instance.max_ms_timout_for_bypass_reset > 0:
                time_since_last = current_time_ms - instance.timestamp_ms_last_attempt
                if time_since_last >= instance.max_ms_timout_for_bypass_reset:
                    instance.should_bypass_run = False
                    logger.debug(f"Reset bypass flag for hook '{hook_func_name}' on block '{block_id}'")

            # 3. Check re-entrancy protection  [bypass-via-status]
            if instance.is_currently_running:
                instance.count_bypass_via_status += 1
                logger.debug(f"Skipping hook '{hook_func_name}' on block '{block_id}' (re-entrancy protection)")
                continue

            # 4. Check rate limiting  [bypass-via-frequency]
            if instance.min_ms_between_runs > 0:
                time_since_last = current_time_ms - instance.timestamp_ms_last_attempt
                if time_since_last < instance.min_ms_between_runs:
                    instance.count_bypass_via_frequency += 1
                    logger.debug(f"Skipping hook '{hook_func_name}' on block '{block_id}' (rate limited)")
                    continue

            # 5. Check @hook_data_filter predicate  [bypass-via-data-filter]
            if instance.arg_filter is not None:
                try:
                    should_run = instance.arg_filter(instance, **kwargs)
                except Exception:
                    logger.error(
                        f"arg_filter raised an exception for hook '{hook_func_name}' on block '{block_id}' — skipping",
                        exc_info=True,
                    )
                    should_run = False
                if not should_run:
                    instance.count_bypass_via_data_filter += 1
                    logger.debug(f"Skipping hook '{hook_func_name}' on block '{block_id}' (data filter)")
                    continue

            # 6. Get cached function reference (avoids repeated getattr)
            hook_func = instance.get_hook_func()
            if hook_func is None:
                raise Exception(f"Subscriber hook function '{hook_func_name}' not found in block '{block_id}'")

            logger.debug(f"Calling hook '{hook_func_name}' of subscriber block '{block_id}'")

            # 7. Execute with timing and re-entrancy protection
            start_time_nanos = time.time()  # recalculate right before func call
            instance.is_currently_running = True
            instance.timestamp_ms_last_attempt = start_time_nanos * 1000
            try:
                result = hook_func(**kwargs)
                end_time_nanos = time.time()  # recalculate right after func call
                instance.count_hook_propagate_success += 1

                if subscriber_block_id is not None:
                    return result
                all_returns[block_id] = result

            except Exception as e:
                end_time_nanos = time.time()
                instance.count_hook_propagate_failure += 1
                logger.error(f"Exception when calling hook '{hook_func_name}' of subscriber '{block_id}'", exc_info=True)
                if should_halt_on_exception:
                    raise e
                all_returns[block_id] = None

            finally:
                # Always reset running flag, even on exception
                instance.is_currently_running = False

                # Track execution time
                execution_time_nanos = end_time_nanos - start_time_nanos
                instance.total_nanos_running_time += execution_time_nanos

        return all_returns

    @classmethod
    def get_subscriber_blocks_of_hook(cls, hook_src_id: Enum):

        # Get hook func name from str/enum input
        actual_hook_func_name = hook_src_id.value[0]

        # Get registered downstream hooks for a func name
        cached_hook_subs = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)
        hook_sub_instances = [h for h in cached_hook_subs if h.hook_func_name == actual_hook_func_name]
        return hook_sub_instances

    # --------------------------------------------------------------
    # Private funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def _rebuild_hook_subs_cache(cls):
        """
        Rebuild REGISTRY_ALL_HOOK_SUBSCRIBERS from REGISTRY_ALL_HOOK_SOURCES and REGISTRY_ALL_BLOCKS.
        """

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug("Rebuilding RTC Hook subscribers")

        registry_all_blocks = Wrapper_Runtime_Cache.get_cache(cache_key_blocks)
        registry_all_hook_sources = Wrapper_Runtime_Cache.get_cache(cache_key_hook_sources)
        registry_all_hook_subscribers = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers, should_copy=True)

        remapped_block_registry = {b.block_id: b for b in registry_all_blocks}
        remapped_hook_source_registry = {s.src_block_id: s for s in registry_all_hook_sources}
        keys_of_current_subscribers = [(p.subscriber_block_id, p.src_block_id, p.hook_func_name) for p in registry_all_hook_subscribers]

        # Build a list of tuples to determine what the subscriber list should look like
        keys_of_desired_subscribers = []
        for hook_source_instance in registry_all_hook_sources:
            hook_func_name = hook_source_instance.hook_func_name
            subscriber_blocks = find_blocks_owning_func_with_name(hook_func_name, registry_all_blocks)
            for subscriber_block_instance in subscriber_blocks:
                new_subscriber_key = tuple((
                    subscriber_block_instance.block_id,
                    hook_source_instance.src_block_id,
                    hook_func_name))
                keys_of_desired_subscribers.append(new_subscriber_key)

        actions_to_perform = compare_unique_tuple_lists(keys_of_current_subscribers, keys_of_desired_subscribers)
        for action in actions_to_perform:
            index = action["index"]
            action_name = action["action"]
            subscriber_block_id = action["tuple"][0]
            src_block_id = action["tuple"][1]
            hook_func_name = action["tuple"][2]

            if action_name == "remove":
                registry_all_hook_subscribers.pop(index)

            elif action_name == "move":
                from_index = action["from_index"]
                subscriber_hook_instance = registry_all_hook_subscribers.pop(from_index)
                registry_all_hook_subscribers.insert(index, subscriber_hook_instance)

            elif action_name == "add":

                # Get block data from remapped funcs
                subscriber_block_module = remapped_block_registry[subscriber_block_id].block_module
                hook_func_named_args = remapped_hook_source_registry[src_block_id].hook_func_named_args

                # Read @hook_data_filter predicate from the function attribute (if present)
                hook_func_ref = getattr(subscriber_block_module, hook_func_name, None)
                arg_filter = getattr(hook_func_ref, _HOOK_DATA_FILTER_ATTR, None)

                # Create and insert new subscriber
                subscriber_hook_instance = RTC_Hook_Subscriber_Instance(
                    src_block_id=src_block_id,
                    subscriber_block_id=subscriber_block_id,
                    hook_func_name=hook_func_name,
                    is_hook_enabled=True,
                    subscriber_block_module=subscriber_block_module,
                    hook_func_named_args=hook_func_named_args,
                    arg_filter=arg_filter,
                )
                registry_all_hook_subscribers.insert(index, subscriber_hook_instance)

        # Log results
        actions_list = [i["action"] for i in actions_to_perform]
        if len(actions_to_perform) == 0:
            actions_str = "No updates to subscriber hooks"
        else:
            actions_str = "Subscriber hooks " + ", ".join(f"to {k}={v}" for k, v in Counter(actions_list).items())
        logger.debug(actions_str)

        # Write updates back to registry
        Wrapper_Runtime_Cache.set_cache(cache_key_hook_subscribers, registry_all_hook_subscribers)

    @classmethod
    def _get_func_name_from_hook_id(cls, hook_func):

        # hook_func input can be either the str func name, or an enum class member from a *_constants.py file
        if isinstance(hook_func, str):
            return hook_func
        elif isinstance(hook_func, Enum):
            return hook_func.value[0]
        else:
            raise Exception(f"Invalid input, expects <str> or <Enum> for hook_func: {hook_func}")

    @classmethod
    def _validate_hook_args(cls, func_name, expected_args):

        # Get the signature of the passed function
        sig = inspect.signature(func_name)
        params = sig.parameters

        # 1. Check if the number of arguments matches
        if len(params) != len(expected_args):
            return False, f"Expected {len(expected_args)} args, got {len(params)}"

        for name, expected_type in expected_args.items():
            # 2. Check if the parameter name exists
            if name not in params:
                return False, f"Missing expected argument: '{name}'"

            # 3. Check if the type hint matches
            actual_type = params[name].annotation
            if actual_type != expected_type:
                return False, f"Type mismatch for '{name}': Expected {expected_type}, got {actual_type}"

        return True, "Valid"

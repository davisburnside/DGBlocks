from dataclasses import dataclass, field
from collections import Counter
from types import ModuleType
from typing import Any, Callable, Dict, Optional
from enum import Enum
import logging
import inspect
import time
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional
import bpy # type: ignore
from bpy.app.handlers import persistent # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helper_funcs import  is_bpy_ready, py_dicty_get_field_value, find_blocks_owning_func_with_name
from ....addon_data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_and_RTC_Data_Syncronizer

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_logs import get_logger
from ..core_helpers.constants import _BLOCK_ID, Core_Block_Loggers, Core_Runtime_Cache_Members
from ..core_helpers.helper_datasync import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop, compare_unique_tuple_lists
from .feature_runtime_cache import Wrapper_Runtime_Cache

#=================================================================================
# MODULE VARS & CONSTANTS
#=================================================================================

rtc_hook_sources_key = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES
rtc_hook_downstreams_key = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS

# Variable names of DGBLOCKS_PG_Debug_Block_Reference & RTC_Block_Instance
rtc_sync_key_fields = ["hook_func_name"]
rtc_sync_data_fields = [
    "src_block_id",
    "downstream_block_id", 
    "is_hook_enabled",
]
uilist_col_width_A = 1.5
uilist_col_width_B = 10
uilist_col_width_C = 3
uilist_col_width_D = 3

#=================================================================================
# BLENDER DATA FOR FEATURE - Stored in Scene
#=================================================================================

def _callback_update_hook_enabled(self, context):

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS):
        return
    Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, True)
    Wrapper_Hooks.update_RTC_with_mirrored_BL_data()
    Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, False)

class DGBLOCKS_PG_Hook_Reference(bpy.types.PropertyGroup):
    # RTC Mirror = 'RTC_Hook_Downstream_Instance'
    # Used to toggle Hooks On/Off in Debug mode
    
    src_block_id: bpy.props.StringProperty(name = "Source Block ID") # type: ignore
    downstream_block_id: bpy.props.StringProperty(name = "Downstream Block ID") # type: ignore
    hook_func_name: bpy.props.StringProperty(name = "Hook Function Name") # type: ignore
    is_hook_enabled: bpy.props.BoolProperty(default = True, update = _callback_update_hook_enabled) # type: ignore

#=================================================================================
# RTC DATA FOR FEATURE
#=================================================================================

@dataclass
class RTC_Hook_Source_Instance:
    """
    Record — instance state only, no manager logic
    This dataclass also stores the callable downstream hook func
    """
    
    src_block_id: str # The creator block of the hook
    hook_func_name: str
    hook_func_named_args: Dict[str, Any] # Used for type-warnings & debugging

@dataclass
class RTC_Hook_Downstream_Instance:
    # Record — instance state only, no manager logic
    # This dataclass also stores a callable reference to the hook func from the downstream block

    # Mirrored fields of DGBLOCKS_PG_Hook_Reference
    src_block_id: str
    downstream_block_id: str
    hook_func_name: str
    is_hook_enabled: bool

    # Not present in mirror
    downstream_block_module: ModuleType # The block which owns the hook func
    hook_func_name: str # The name of the hooked function inside destination block
    hook_func_named_args: Dict[str, Any] # Used for type-warnings & debugging. Copied from RTC_Hook_Source_Instance
    is_currently_running: bool = False # Falsed upon successful or failed hook func run
    should_bypass_run: bool = False # Causes hook call bypass (bypass-via-status)
    min_ms_between_runs: int = 0 # Causes hook call bypass (bypass-via-frequency)
    max_ms_timout_for_bypass_reset: int = 0 # resets should_bypass_run to False
    timestamp_ms_last_attempt: int = 0 # used by min_ms_between_runs
    total_nanos_running_time: float = 0.0 # used for debugging & UI Alerts
    count_hook_propagate_success: int = 0 # increments when hook func completes without exception
    count_hook_propagate_failure: int = 0 # increments when hook func raises an exception
    count_bypass_via_data_filter: int = 0 # increments when arg_filter predicate returns False
    count_bypass_via_status: int = 0 # increments when should_bypass_run is True, or re-entrancy guard fires
    count_bypass_via_frequency: int = 0 # increments when min_ms_between_runs rate-limit fires

    # Predicate set by @hook_data_filter. Receives (hook_metadata, **kwargs).
    # None = no filter (always run). Set automatically by _resync_downstream_listeners.
    arg_filter: Optional[Callable[..., bool]] = field(default=None, repr=False)

    # The callable hook function from the downsteam block
    _cached_func: Optional[Callable] = field(default=None, init=False, repr=False) # Cached function reference

    def get_hook_func(self) -> Optional[Callable]:
        """Get cached function reference, avoiding repeated getattr() calls."""
        if self._cached_func is None:
            self._cached_func = getattr(
                self.downstream_block_module,
                self.hook_func_name,
                None
            )
        return self._cached_func

#=================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
#=================================================================================

class Wrapper_Hooks(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_and_RTC_Data_Syncronizer):
    # Manager — classmethods only, no instance state
    # Manages hook registrations and src->downstream propagation between blocks
    # All data managed by this wrapper is stored in RTC

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> None:
        "no-op"
        return True
    
    @classmethod
    def init_post_bpy(cls) -> None:

        logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
        logger.debug(f"Running post-bpy init for Wrapper_Hooks")

        Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, True)
        cls.rebuild_RTC_downstreams_from_sources()
        cls.update_BL_with_mirrored_RTC_data()
        Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, False)
        return True
    
    @classmethod
    def destroy_wrapper(cls) -> None:
        "no-op"
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_and_RTC_Data_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, skip_downstream_sync = False):

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating hooks cache with mirrored Blender data")
        
        registry_all_downstream_hooks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS)
        scene_hooks_collection = bpy.context.scene.dgblocks_core_props.managed_hooks
        update_dataclasses_to_match_collectionprop(
            source = scene_hooks_collection,
            target = registry_all_downstream_hooks,
            dataclass_type = Wrapper_Hooks,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields
        )
        if not skip_downstream_sync:
            cls.rebuild_RTC_downstreams_from_sources()

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls):

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating Blender data with mirrored hooks cache")
        
        registry_all_downstream_hooks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS)
        scene_hooks_collection = bpy.context.scene.dgblocks_core_props.managed_hooks
        update_collectionprop_to_match_dataclasses(
            source = registry_all_downstream_hooks,
            target = scene_hooks_collection,
            key_fields = rtc_sync_key_fields,
            data_fields = rtc_sync_data_fields
        )

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        src_block_id: str,
        new_hook_func_id: any,
        new_hook_func_named_args: Dict[str, Any] = None,
        skip_BL_sync:bool = False, 
        skip_downstream_sync:bool = False
    ) -> None:

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug(f"Creating hook source '{new_hook_func_id}'")
        
        # Get hook func name from str/enum input
        hook_func_name = cls._get_func_name_from_hook_id(new_hook_func_id)
        all_cached_hook_sources = Wrapper_Runtime_Cache.get_cache(rtc_hook_sources_key)

        # Validate uniquness. Return with no action upon duplication attempt
        if Wrapper_Runtime_Cache.cache_list_contains_member(all_cached_hook_sources, "hook_func_name", hook_func_name):
            logger.debug(f"Hook Source '{hook_func_name}' already exists in RTC. Returning with no action")
            return
        
        # Create new hook source instance & update runtime cache. Uniqueness is validated inside 'add_unique_'
        new_hook_source_instance = RTC_Hook_Source_Instance(
            src_block_id,
            hook_func_name,
            new_hook_func_named_args,
        )
        all_cached_hook_sources.append(new_hook_source_instance)
        Wrapper_Runtime_Cache.set_cache(rtc_hook_sources_key, all_cached_hook_sources)
        # Wrapper_Runtime_Cache.add_unique_instance_to_registry_list(
        #     member_key = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES,
        #     uniqueness_field = "hook_func_name",
        #     new_instance = new_hook_source_instance,
        # )

        # Update downstreams
        if not skip_downstream_sync:
            cls.rebuild_RTC_downstreams_from_sources()

        # Add hook data from Blender file
        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, False)

    @classmethod
    def get_instance(
        cls,
        hook_func_name: str,
        downstream_block_id: Optional[str] = None,
    ) -> list[RTC_Hook_Downstream_Instance]:
        """
        Get hook metadata.
        - returns list of all downstreams instances for hook
        """
        
        # Get hook func name from str/enum input
        hook_func_name = cls._get_func_name_from_hook_id(hook_func_name)
        if hook_func_name is None:
            return None
        
        # Get registered downstream hooks for a func name
        all_downstream_instances = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS)
        if hook_func_name not in all_downstream_instances:
            return []
        instances_to_return = all_downstream_instances[hook_func_name]

        # Return either a list of, or a single/None instance
        if downstream_block_id is None:
            return instances_to_return
        else:
            single_instance = next((i for i in instances_to_return if i.downstream_block_module._BLOCK_ID == downstream_block_id), None)
            return [single_instance]

    @classmethod
    def set_instance(cls) -> None:
        raise Exception("set_instance is not used for Hooks Wrapper. Use create_instance and destroy_instance")

    @classmethod
    def destroy_instance(cls, hook_func_name, skip_BL_sync:bool = False, skip_downstream_sync:bool = False) -> None:
        """
        Remove hook registration
        """

        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug(f"Removing hook source '{hook_func_name}'")

        # Remove source hook from registry
        hook_func_name = cls._get_func_name_from_hook_id(hook_func_name)
        all_source_instances = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES)
        instances_to_destroy = (i for i in all_source_instances if i.hook_func_name == hook_func_name)
        for instance in instances_to_destroy:
            list_idx = all_source_instances.index(instance)
            del all_source_instances[list_idx]
        Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES, all_source_instances)

        # Update downstreams
        if not skip_downstream_sync:
            cls.rebuild_RTC_downstreams_from_sources()

        # Remove hook data from Blender file
        if is_bpy_ready() and not skip_BL_sync:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, False)


    # --------------------------------------------------------------
    # Public funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def run_hooked_funcs(
        cls,
        hook_func_name: any,
        specific_downstream_block_id: Optional[str] = None,
        should_halt_on_exception: bool = True,
        **kwargs,
    ) -> Any:
        """
        Trigger hook callbacks for all registered blocks with full rate-limiting and timing support.
        
        Args:
            hook_func: The hook function to call
            specific_downstream_block_id: If provided, only call this specific block's hook
            should_halt_on_exception: If True, re-raise exceptions
            **kwargs: Arguments passed to hook functions
            
        Returns:
            If specific_downstream_block_id: single return value
            Otherwise: dict of {block_id: return_value}
        """
        logger = get_logger(Core_Block_Loggers.HOOKS)
        all_returns: Dict[str, Any] = {}
        
        # Get hook func name from str/enum input
        hook_func_name = cls._get_func_name_from_hook_id(hook_func_name)

        RTC_downstream_hooks = Wrapper_Runtime_Cache.get_all_with_key_value_from_registry_list(
            Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS,
            key_field_name = "hook_func_name",
            key_field_value = hook_func_name,
        )

        if len(RTC_downstream_hooks) == 0:
            logger.info(f"No downstream listeners found for hook '{hook_func_name}'")
            return all_returns
        
        current_time_ms = int(time.time() * 1000)
        start_time_nanos = None
        end_time_nanos = None
        for instance in RTC_downstream_hooks:
            block_module = instance.downstream_block_module
            block_id = block_module._BLOCK_ID
            if not instance.is_hook_enabled:
                # logger.warning(f"Downstream Hook '{hook_func_name}' of block '{block_id}' is disabled")
                continue
            
            # 1. Filter by downstream block if specified
            if specific_downstream_block_id is not None and specific_downstream_block_id != block_id:
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
                raise Exception (f"Downstream hook function '{hook_func_name}' not found in block '{block_id}'")
                continue
            
            logger.debug(f"Calling hook '{hook_func_name}' of downstream block '{block_id}'")
            
            # 7. Execute with timing and re-entrancy protection
            start_time_nanos = time.time() # recalculate right before func call
            instance.is_currently_running = True
            instance.timestamp_ms_last_attempt = start_time_nanos * 1000
            try:
                result = hook_func(**kwargs)
                end_time_nanos = time.time() # recalculate right after func call
                instance.count_hook_propagate_success += 1

                if specific_downstream_block_id is not None:
                    return result
                all_returns[block_id] = result

            except Exception as e:
                end_time_nanos = time.time()
                instance.count_hook_propagate_failure += 1
                logger.error(f"Exception when calling hook '{hook_func_name}' of downstream '{block_id}'", exc_info=True)
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

    # --------------------------------------------------------------
    # Private funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def rebuild_RTC_downstreams_from_sources(cls):
        """
        Rebuild REGISTRY_ALL_HOOK_DOWNSTREAMS from REGISTRY_ALL_HOOK_SOURCES and REGISTRY_ALL_BLOCKS.
        RTC_Hook_Downstream_Instance's copy-logic is unsuited for RTC's builtin sync (sync_blender_propertygroup_and_raw_python), so copy-logic is handled here instead
        Creates optimal data structure for fast hook lookup:
        {
            "hook_func_name": [RTC_Hook_Downstream_Instance, RTC_Hook_Downstream_Instance, ...],
            ...
        }
        
        Args:
            should_keep_stats: If True, preserve existing hook skip/success/failure/timing statistics when rebuilding REGISTRY_ALL_HOOK_DOWNSTREAMS
        """
        
        logger = get_logger(Core_Block_Loggers.HOOKS)
        logger.debug("Rebuilding RTC Hook downstreams")
        
        registry_all_blocks = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)
        registry_all_hook_sources = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SOURCES)
        registry_all_hook_downstreams = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, should_copy = True)

        remapped_block_registry = { b.block_id : b for b in registry_all_blocks}
        remapped_hook_source_registry = { s.src_block_id : s for s in registry_all_hook_sources}
        keys_of_current_downstreams = [(p.downstream_block_id, p.src_block_id, p.hook_func_name) for p in registry_all_hook_downstreams]

        # Build a list of tuples to determine what the downstream list should look like. Each tuple is a unique key of (downstream-block, src-block, func-name)
        keys_of_desired_downstreams = []
        for hook_source_instance in registry_all_hook_sources:
            hook_func_name = hook_source_instance.hook_func_name
            downstream_blocks = find_blocks_owning_func_with_name(hook_func_name, registry_all_blocks)
            for downstream_block_instance in downstream_blocks:
                new_downstream_key = tuple((
                    downstream_block_instance.block_id, 
                    hook_source_instance.src_block_id, 
                    hook_func_name))
                keys_of_desired_downstreams.append(new_downstream_key)
        
        actions_to_perform = compare_unique_tuple_lists(keys_of_current_downstreams, keys_of_desired_downstreams)
        for action in actions_to_perform:
            index = action["index"]
            action_name = action["action"]
            downstream_block_id = action["tuple"][0]
            src_block_id = action["tuple"][1]
            hook_func_name = action["tuple"][2]

            if action_name == "remove":
                registry_all_hook_downstreams.pop(index)

            elif action_name == "move":
                from_index = action["from_index"]
                downstream_hook_instance = registry_all_hook_downstreams.pop(from_index)
                registry_all_hook_downstreams.insert(index, downstream_hook_instance)

            elif action_name == "add":

                # Get block data from remapped funcs
                downstream_block_module = remapped_block_registry[downstream_block_id].block_module
                hook_func_named_args = remapped_hook_source_registry[src_block_id].hook_func_named_args

                # Read @hook_data_filter predicate from the function attribute (if present)
                hook_func_ref = getattr(downstream_block_module, hook_func_name, None)
                arg_filter = getattr(hook_func_ref, _HOOK_DATA_FILTER_ATTR, None)

                # Create and insert new downstream
                downstream_hook_instance = RTC_Hook_Downstream_Instance(
                    src_block_id = src_block_id,
                    downstream_block_id = downstream_block_id,
                    hook_func_name = hook_func_name,
                    is_hook_enabled = True,
                    downstream_block_module = downstream_block_module,
                    hook_func_named_args = hook_func_named_args,
                    arg_filter=arg_filter,
                )
                registry_all_hook_downstreams.insert(index, downstream_hook_instance)

        # Log results
        actions_list = [i["action"] for i in actions_to_perform]
        if len(actions_to_perform) == 0:
            actions_str = "No updates to downstream hooks"
        else:
            actions_str = "Downstream hooks " + ", ".join(f"to {k}={v}" for k, v in Counter(actions_list).items())
        logger.debug(actions_str)

        # Write updates back to registry
        Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_DOWNSTREAMS, registry_all_hook_downstreams)

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

# Optional Decorator for any downstream hook func
_HOOK_DATA_FILTER_ATTR = "__hook_data_filter__"
def hook_data_filter(predicate: Callable[..., bool]):
    """
    Decorator. Attaches a data-filter predicate to a downstream hook function.

    The predicate is evaluated at call time inside run_hooked_funcs, BEFORE the
    hook function itself is invoked. If the predicate returns False the call is
    skipped and counted as a 'bypass-via-data-filter'.

    Predicate signature:
        predicate(hook_metadata, **kwargs) -> bool

    Args:
        hook_metadata : RTC_Hook_Downstream_Instance  — the live metadata record for this
                        hook/block pair. Gives access to counts, timing, bypass
                        flags, and the downstream_block_module (i.e. the block's own
                        datablock / state) so the filter can inspect block state.
        **kwargs      : The same keyword arguments that will be forwarded to the
                        hook function. Use **_ to absorb args you don't care about.

    Returns True  → proceed with the hook call.
    Returns False → skip (bypass-via-data-filter, counted separately).

    The decorated function is returned UNCHANGED — zero call-path overhead when
    the filter passes.

    Examples
    --------
    # Only run when the addon is active (inspect a kwarg):
        @hook_data_filter(lambda hook_metadata, context, **_:
            context.scene.dgblocks_core_props.addon_is_active)
        def hook_post_register_init(context):
            ...

    # Only run when this block's own scene prop is enabled (inspect block state):
        @hook_data_filter(lambda hook_metadata, context, **_:
            getattr(context.scene, 'my_block_props', None) is not None and
            context.scene.my_block_props.is_enabled)
        def hook_on_depsgraph_update(context, depsgraph):
            ...

    # Named predicate for complex / reusable logic:
        def _only_for_mesh(hook_metadata, context, **_):
            obj = context.active_object
            return obj is not None and obj.type == 'MESH'

        @hook_data_filter(_only_for_mesh)
        def hook_on_selection_changed(context):
            ...

    # No decorator → arg_filter is None → always runs, zero overhead:
        def hook_post_register_init(context):
            ...
    """
    def decorator(func):
        setattr(func, _HOOK_DATA_FILTER_ATTR, predicate)
        return func  # function is NOT wrapped — no call-path overhead
    return decorator

#=================================================================================
# UI
#=================================================================================

class DGBLOCKS_UL_Hooks(bpy.types.UIList):
    """UIList to display RTC hooks with enable toggle and alert states."""
    
    def draw_item(self, context, container, data, item, icon, active_data, active_propname, index):

        row = container.row(align=True)
        
        # Hook name
        sub = row.row()
        sub.ui_units_x = uilist_col_width_B
        sub.label(text=item.hook_func_name)

        # Downstream block
        sub = row.row()
        sub.ui_units_x = uilist_col_width_B
        sub.label(text=item.downstream_block_id)

        # Is enabled status
        sub = row.row()
        sub.ui_units_x = uilist_col_width_D
        sub.prop(item, "is_hook_enabled", text="", icon='CHECKBOX_HLT' if item.is_hook_enabled else 'CHECKBOX_DEHLT')

def _uilayout_draw_hooks_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_scene_hooks_mgmt", default_closed=True)
    panel_header.label(text = "All Hooks")
    if panel_body is not None:        

        # Draw column headers - must match draw_item layout exactly
        header = panel_body.row()
        header.separator(factor=0.5)  # Account for UIList left padding
        sub = header.row()
        sub.ui_units_x = uilist_col_width_A
        sub.label(text="")  # Alert icon
        sub = header.row()
        sub.ui_units_x = uilist_col_width_B
        sub.label(text="Name")
        sub = header.row()
        sub.ui_units_x = uilist_col_width_D
        sub.label(text="Is Enabled?")

        # Draw the UIList
        row = panel_body.row()
        row_count = len(core_props.managed_hooks)
        row.template_list(
            "DGBLOCKS_UL_Hooks",
            "",
            core_props, "managed_hooks",           # Collection property
            core_props, "managed_hooks_selected_idx",     # Active index property
            rows = row_count,
            maxrows = row_count,
            columns = 3, 
        )
        
        # # Show disabled reason for selected alert row
        # if core_props.managed_hooks and 0 <= core_props.managed_hooks_selected_idx < len(core_props.managed_hooks):
        #     active_block = core_props.managed_hooks[core_props.managed_hooks_selected_idx]
        #     is_alert = active_block.should_block_be_enabled and not active_block.is_block_enabled
            
        #     if is_alert and active_block.block_disabled_reason:
        #         box = panel_body.box()
        #         box.alert = True
        #         box.label(text=f"Reason: {active_block.block_disabled_reason}", icon='INFO')

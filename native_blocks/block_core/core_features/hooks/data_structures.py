# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Callable, Dict, Optional
from enum import Enum
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from .....addon_helpers.data_structures import Enum_Sync_Events
from .....addon_helpers.generic_helpers import is_bpy_ready

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Runtime_Cache_Members
from ..runtime_cache import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_hook_subscribers = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS

# ==============================================================================================================================
# BLENDER DATA (PropertyGroup + update callback)
# ==============================================================================================================================

def _callback_update_hook_sub_enabled(self, context):

    # Skip further action if a sync is already in progress
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key_hook_subscribers):
        return
    # Lazy import to avoid circular dependency: data_structures <- feature_wrapper <- data_structures
    from .feature_wrapper import Wrapper_Hooks
    Wrapper_Hooks.update_RTC_with_mirrored_BL_data(event=Enum_Sync_Events.PROPERTY_UPDATE)


class DGBLOCKS_PG_Hook_Reference(bpy.types.PropertyGroup):
    # RTC Mirror = 'RTC_Hook_Subscriber_Instance'
    # Used to toggle Hooks On/Off in Debug mode

    src_block_id: bpy.props.StringProperty(name="Source Block ID")  # type: ignore
    subscriber_block_id: bpy.props.StringProperty(name="Subscriber Block ID")  # type: ignore
    hook_func_name: bpy.props.StringProperty(name="Hook Function Name")  # type: ignore
    is_hook_enabled: bpy.props.BoolProperty(default=True, update=_callback_update_hook_sub_enabled)  # type: ignore

# ==============================================================================================================================
# RTC DATA
# ==============================================================================================================================

# Used during RTC <-> BL data sync
rtc_sync_key_fields = ["hook_func_name", "subscriber_block_id"]
rtc_sync_data_fields = [
    "src_block_id",
    "is_hook_enabled",
]


@dataclass
class RTC_Hook_Subscriber_Instance:
    # Record — instance state only, no manager logic
    # This dataclass also stores a callable reference to the hook func from the subscriber block

    # Mirrored fields of DGBLOCKS_PG_Hook_Reference
    src_block_id: str
    subscriber_block_id: str
    hook_func_name: str
    is_hook_enabled: bool

    # Not present in mirror
    subscriber_block_module: ModuleType  # The block which owns the hook func
    hook_func_named_args: Dict[str, Any]  # Used for type-warnings & debugging. Copied from RTC_Hook_Source_Instance
    is_currently_running: bool = False  # Falsed upon successful or failed hook func run
    should_bypass_run: bool = False  # Causes hook call bypass (bypass-via-status)
    min_ms_between_runs: int = 0  # Causes hook call bypass (bypass-via-frequency)
    max_ms_timout_for_bypass_reset: int = 0  # resets should_bypass_run to False
    timestamp_ms_last_attempt: int = 0  # used by min_ms_between_runs
    total_nanos_running_time: float = 0.0  # used for debugging & UI Alerts
    count_hook_propagate_success: int = 0  # increments when hook func completes without exception
    count_hook_propagate_failure: int = 0  # increments when hook func raises an exception
    count_bypass_via_data_filter: int = 0  # increments when arg_filter predicate returns False
    count_bypass_via_status: int = 0  # increments when should_bypass_run is True, or re-entrancy guard fires
    count_bypass_via_frequency: int = 0  # increments when min_ms_between_runs rate-limit fires

    # Predicate set by @hook_data_filter. Receives (hook_metadata, **kwargs).
    # None = no filter (always run). Set automatically by _resync_subscriber_listeners.
    arg_filter: Optional[Callable[..., bool]] = field(default=None, repr=False)

    # The callable hook function from the downstream block
    _cached_func: Optional[Callable] = field(default=None, init=False, repr=False)  # Cached function reference

    def get_hook_func(self) -> Optional[Callable]:
        """Get cached function reference, avoiding repeated getattr() calls."""
        if self._cached_func is None:
            self._cached_func = getattr(
                self.subscriber_block_module,
                self.hook_func_name,
                None
            )
        return self._cached_func


@dataclass
class RTC_Hook_Source_Instance:
    """
    Record — instance state only, no manager logic
    This dataclass also stores the callable subscriber hook func.
    Hook-sources are used to drive hook-subscribers
    """

    src_block_id: str  # The creator block of the hook
    hook_func_name: str
    hook_func_named_args: Dict[str, Any]  # Used for type-warnings & debugging

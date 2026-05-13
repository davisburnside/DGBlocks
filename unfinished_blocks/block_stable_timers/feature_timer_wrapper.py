
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from ...native_blocks.block_core import Abstract_Feature_Wrapper
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_tools import (
    diff_collections,
)

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...native_blocks.block_core import Abstract_Datawrapper_Instance_Manager
from ...native_blocks.block_core.core_features.runtime_cache import Wrapper_Runtime_Cache
from ...native_blocks.block_core.core_features.hooks import Wrapper_Hooks
from ...native_blocks.block_core.core_features.loggers import get_logger
from ...native_blocks.block_core.core_features.control_plane import Wrapper_Control_Plane

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .block_constants import (
    Block_Logger_Definitions,
    Block_Runtime_Cache_Members,
    Block_Hooks,
)

# =============================================================================
# PUBLIC API - Usable by any block
# =============================================================================

# --------------------------------------------------------------
# Instance Definition
# --------------------------------------------------------------
@dataclass
class Timer_Instance_Data:
    """
    Record — instance state only, no manager logic.
    Holds all metadata for a single named timer, including the bpy.app.timers
    callable reference so only one RTC member is needed.
    """
    timer_name: str
    frequency_ms: int
    is_enabled: bool = True

    # Runtime stats (mirrors RTC_Hook_Subscriber_Instance pattern)
    timestamp_ms_last_fire: int = 0
    count_fire_success: int = 0
    count_fire_failure: int = 0
    is_currently_running: bool = False  # Re-entrancy guard

    # Names of subscriber hook functions this timer will trigger on fire.
    # Rebuilt from RTC hook sources whenever timer config changes.
    subscriber_hook_func_names: List[str] = field(default_factory=list)

    # Private: actual bpy.app.timers callable. Not serialisable; rebuilt on sync.
    _timer_func: Optional[Callable] = field(default=None, init=False, repr=False)

# --------------------------------------------------------------
# Main wrapper for feature
# --------------------------------------------------------------
class Timer_Wrapper(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """
    Manager — classmethods only, no instance state.
    Manages Blender app timers with metadata tracking and hook propagation.
    All per-timer state is stored in Timer_Instance_Data objects inside a single RTC member.
    Scene properties are the source of truth for timer definitions; RTC is rebuilt from them.
    """

    # ------------------------------------------------------------------
    # Abstract_Feature_Wrapper implementations
    # ------------------------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        timer_name: str,
        frequency_ms: int,
        is_enabled: bool = True,
    ) -> bool:
        """
        Create a new timer Timer_Instance_Data record and, if enabled, register it with bpy.

        Returns:
            True if created successfully, False if a timer with that name already exists.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)

        all_timers = _rtc_get_all()

        if timer_name in all_timers:
            logger.warning(f"Timer '{timer_name}' already exists — use set_instance to update it")
            return False

        data = Timer_Instance_Data(
            timer_name=timer_name,
            frequency_ms=frequency_ms,
            is_enabled=is_enabled,
        )
        data.subscriber_hook_func_names = cls._collect_subscriber_hook_names()

        if is_enabled:
            cls._register_bpy_timer(data)

        all_timers[timer_name] = data
        _rtc_set_all(all_timers)

        logger.info(f"Created timer '{timer_name}' ({frequency_ms} ms, enabled={is_enabled})")
        return True

    @classmethod
    def get_instance(cls, timer_name: str) -> Optional[Timer_Instance_Data]:
        """
        Return the Timer_Instance_Data for *timer_name*, or None if not found.
        """
        return _rtc_get_all().get(timer_name)

    @classmethod
    def set_instance(
        cls,
        timer_name: str,
        frequency_ms: Optional[int] = None,
        is_enabled: Optional[bool] = None,
    ) -> bool:
        """
        Update an existing timer's frequency and/or enabled state.
        Re-registers the bpy timer if frequency or enabled state changes.

        Returns:
            True if updated, False if the timer does not exist.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)

        all_timers = _rtc_get_all()
        if timer_name not in all_timers:
            logger.warning(f"Timer '{timer_name}' does not exist — use create_instance first")
            return False

        data = all_timers[timer_name]
        needs_rereg = False

        if frequency_ms is not None and frequency_ms != data.frequency_ms:
            logger.debug(f"Timer '{timer_name}': frequency {data.frequency_ms} → {frequency_ms} ms")
            data.frequency_ms = frequency_ms
            needs_rereg = data.is_enabled  # Only re-register if currently active

        if is_enabled is not None and is_enabled != data.is_enabled:
            logger.debug(f"Timer '{timer_name}': enabled {data.is_enabled} → {is_enabled}")
            data.is_enabled = is_enabled
            needs_rereg = True  # State change always requires re-registration check

        if needs_rereg:
            cls._unregister_bpy_timer(data)
            if data.is_enabled:
                cls._register_bpy_timer(data)

        # Refresh subscriber hook names in case hooks changed since last sync
        data.subscriber_hook_func_names = cls._collect_subscriber_hook_names()

        _rtc_set_all(all_timers)
        return True

    @classmethod
    def destroy_instance(cls, timer_name: str) -> bool:
        """
        Stop and remove a timer entirely.

        Returns:
            True if removed, False if not found.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)

        all_timers = _rtc_get_all()
        if timer_name not in all_timers:
            logger.warning(f"Timer '{timer_name}' not found — nothing to destroy")
            return False

        data = all_timers[timer_name]
        cls._unregister_bpy_timer(data)
        del all_timers[timer_name]
        _rtc_set_all(all_timers)

        logger.info(f"Destroyed timer '{timer_name}'")
        return True

    @classmethod
    def init_pre_bpy(cls) -> bool:
        """Called during register() before bpy is fully available. No action needed."""
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        """
        Called once bpy.context is available (post-register hook).
        Loads saved timer definitions from scene properties into RTC.
        Registers this wrapper with Wrapper_Control_Plane for undo/redo/load sync.
        """
        scene = bpy.context.scene
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)
        logger.debug("Timer_Wrapper.init_post_bpy: syncing scene → RTC")
        cls.update_BL_with_mirrored_RTC_data(scene)
        
        # Register for automatic undo/redo/load sync
        Wrapper_Control_Plane.destroy_instance(
            block_id="block-stable-timers",
            wrapper_class=cls,
            scene_propgroup_attr="dgblocks_timer_props",
        )
        Wrapper_Control_Plane.ensure_sync_toggle_exists(scene, "block-stable-timers")
        
        logger.info("Timer_Wrapper.init_post_bpy: done")
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        """
        Unregister all bpy timers and clear the RTC member.
        Called during unregister().
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)
        logger.debug("Timer_Wrapper.destroy_wrapper: stopping all timers")

        all_timers = _rtc_get_all()
        for data in list(all_timers.values()):
            cls._unregister_bpy_timer(data)

        _rtc_set_all({})
        logger.info("Timer_Wrapper.destroy_wrapper: done")
        return True

    # ------------------------------------------------------------------
    # Public convenience methods
    # ------------------------------------------------------------------

    @classmethod
    def activate_timer(cls, timer_name: str) -> bool:
        """Enable a timer by name. No-op if already enabled."""
        return cls.set_instance(timer_name, is_enabled=True)

    @classmethod
    def deactivate_timer(cls, timer_name: str) -> bool:
        """Disable a timer by name. No-op if already disabled."""
        return cls.set_instance(timer_name, is_enabled=False)

    @classmethod
    def get_all_timers(cls) -> Dict[str, Timer_Instance_Data]:
        """Return the full dict of all Timer_Instance_Data records (live reference)."""
        return _rtc_get_all()

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, scene) -> None:
        """
        Rebuild RTC from scene properties. Scene is the source of truth.
        Called by Wrapper_Control_Plane on undo/redo/load, and by property update callbacks.
        Implements Abstract_Feature_Wrapper.update_BL_with_mirrored_RTC_data.
        """
        pass
        # cls._sync_scene_to_rtc_impl(scene)

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, scene) -> None:
        """
        Write RTC timer state back into scene properties. RTC is the source of truth.
        Implements Abstract_Feature_Wrapper.update_RTC_with_mirrored_BL_data.
        """
        pass
        # logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)
        # logger.debug("Timer_Wrapper.update_RTC_with_mirrored_BL_data: starting")

        # if not hasattr(scene, "dgblocks_timer_props"):
        #     logger.warning("update_RTC_with_mirrored_BL_data: scene has no 'dgblocks_timer_props'")
        #     return

        # all_timers = _rtc_get_all()
        # timer_props = scene.dgblocks_timer_props

        # # Build a lookup of existing scene items by name
        # scene_timer_names = {item.timer_name: idx for idx, item in enumerate(timer_props.timers)}

        # # Update existing scene items and add new ones from RTC
        # for timer_name, data in all_timers.items():
        #     if timer_name in scene_timer_names:
        #         item = timer_props.timers[scene_timer_names[timer_name]]
        #         item.frequency_ms = data.frequency_ms
        #         item.is_enabled = data.is_enabled
        #     else:
        #         item = timer_props.timers.add()
        #         item.timer_name = data.timer_name
        #         item.frequency_ms = data.frequency_ms
        #         item.is_enabled = data.is_enabled

        # # Remove scene items that no longer exist in RTC
        # for i in range(len(timer_props.timers) - 1, -1, -1):
        #     if timer_props.timers[i].timer_name not in all_timers:
        #         timer_props.timers.remove(i)

        # logger.debug("Timer_Wrapper.update_RTC_with_mirrored_BL_data: done")

    @classmethod
    def sync_scene_to_rtc(cls, scene) -> None:
        """
        Legacy convenience alias for update_BL_with_mirrored_RTC_data.
        Kept for backward compatibility with existing update callbacks.
        """
        cls.update_BL_with_mirrored_RTC_data(scene)

    @classmethod
    def _sync_scene_to_rtc_impl(cls, scene) -> None:
        """
        Internal implementation: Rebuild RTC timer records from scene properties.
        Scene properties are the source of truth.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)
        logger.debug("Timer_Wrapper.sync_scene_to_rtc: starting")

        if not hasattr(scene, "dgblocks_timer_props"):
            logger.warning("sync_scene_to_rtc: scene has no 'dgblocks_timer_props'")
            return

        # Step 1: Convert PropertyGroup → dict using helper
        # scene_data = propertygroup_to_dict(scene.dgblocks_timer_props) # TODO replace
        scene_data = Wrapper_Runtime_Cache.sync_blender_propertygroup_and_raw_python(
            bl_propgroup_data = scene.dgblocks_timer_props, 
            py_raw_data = {}, 
            blender_as_truth_source = True
        )
        all_timers = _rtc_get_all()

        # Step 2: Find differences using helper
        to_add, to_remove, to_update = diff_collections(
            all_timers.keys(),
            [t['timer_name'] for t in scene_data['timers']]
        )

        # Step 3: Remove stale timers
        for stale_name in to_remove:
            logger.debug(f"sync_scene_to_rtc: removing stale timer '{stale_name}'")
            cls.destroy_instance(stale_name)

        # Step 4: Add new and update existing timers
        for timer_dict in scene_data['timers']:
            name = timer_dict['timer_name']
            if name in to_add:
                print("!!!", timer_dict)
                cls.create_instance(**timer_dict)
            elif name in to_update:
                # set_instance uses merge_dataclass_with_dict internally to preserve stats
                cls.set_instance(
                    name,
                    frequency_ms=timer_dict['frequency_ms'],
                    is_enabled=timer_dict['is_enabled']
                )

        logger.debug("Timer_Wrapper.sync_scene_to_rtc: done")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _collect_subscriber_hook_names(cls) -> List[str]:
        """
        Return a list of hook function names that are currently registered
        as subscriber listeners for Block_Hooks.TIMER_FIRE.
        This list is stored on Timer_Instance_Data and used at fire-time.
        """
        hook_func_name = Block_Hooks.TIMER_FIRE.value[0]
        listeners = Wrapper_Hooks.get_instance(Block_Hooks.TIMER_FIRE)
        if not listeners:
            return []
        # listeners is a list of RTC_Hook_Subscriber_Instance objects
        return [hook_func_name for _ in listeners]  # same func name, one entry per listener block

    @classmethod
    def _register_bpy_timer(cls, timer_instance: Timer_Instance_Data) -> None:
        """
        Create and register a bpy.app.timers callable for *data*.
        Stores the callable on data._timer_func so it can be unregistered later.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)

        if timer_instance._timer_func is not None and bpy.app.timers.is_registered(timer_instance._timer_func):
            logger.debug(f"_register_bpy_timer: '{timer_instance.timer_name}' already registered, skipping")
            return

        def _callback():
            return Timer_Wrapper._timer_callback(timer_instance)

        interval_s = timer_instance.frequency_ms / 1000.0
        bpy.app.timers.register(_callback, first_interval=interval_s)
        timer_instance._timer_func = _callback

        logger.debug(f"_register_bpy_timer: registered '{timer_instance.timer_name}' at {interval_s:.3f}s interval")

    @classmethod
    def _unregister_bpy_timer(cls, timer_instance: Timer_Instance_Data) -> None:
        """
        Unregister the bpy.app.timers callable stored on *data* and clear the reference.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)

        if timer_instance._timer_func is None:
            return

        if bpy.app.timers.is_registered(timer_instance._timer_func):
            bpy.app.timers.unregister(timer_instance._timer_func)
            logger.debug(f"_unregister_bpy_timer: unregistered '{timer_instance.timer_name}'")

        timer_instance._timer_func = None

    @classmethod
    def _timer_callback(cls, timer_instance: Timer_Instance_Data) -> Optional[float]:
        """
        Executed by bpy.app.timers each time the timer fires.

        Returns:
            Interval in seconds until next fire, or None to stop the timer.
        """
        logger = get_logger(Block_Logger_Definitions.TIMER_FIRE)

        all_timers = _rtc_get_all()
        if timer_instance.timer_name not in all_timers:
            logger.warning(f"_timer_callback: '{timer_instance.timer_name}' fired but not found in RTC — stopping")
            return None
        data = all_timers[timer_instance.timer_name]

        # Stop if disabled
        if not data.is_enabled:
            logger.debug(f"_timer_callback: '{timer_instance.timer_name}' is disabled — stopping")
            return None
        
        # Re-entrancy guard
        if data.is_currently_running:
            logger.debug(f"_timer_callback: '{timer_instance.timer_name}' already running — skipping this fire")
            return data.frequency_ms / 1000.0

        data.is_currently_running = True
        data.timestamp_ms_last_fire = int(time.time() * 1000)

        try:

            # Propagate hook to all subscriber blocks
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=Block_Hooks.TIMER_FIRE,
                should_halt_on_exception=False,
                timer_instance=timer_instance,
            )
            data.count_fire_success += 1

        except Exception as e:
            data.count_fire_failure += 1
            logger.error(f"_timer_callback: exception for '{timer_instance.timer_name}'", exc_info=True)

        finally:
            data.is_currently_running = False

        return data.frequency_ms / 1000.0

# =============================================================================
# PRIVATE — RTC convenience helpers (module-level, not part of the public API)
# =============================================================================

def _rtc_get_all() -> Dict[str, Timer_Instance_Data]:
    """Return the live dict of all Timer_Instance_Data records from RTC."""
    return Wrapper_Runtime_Cache.get_cache(Block_Runtime_Cache_Members.TIMER_INSTANCES)

def _rtc_set_all(data: Dict[str, Timer_Instance_Data]) -> None:
    """Write the full Timer_Instance_Data dict back to RTC."""
    Wrapper_Runtime_Cache.set_cache(Block_Runtime_Cache_Members.TIMER_INSTANCES, data)


import bpy

# Addon-level imports
from ...addon_helpers.data_structures import (
    Abstract_BL_RTC_List_Syncronizer,
    Abstract_Feature_Wrapper,
    Enum_Sync_Events,
)

# Inter-block imports
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import App_Handler_Subscription_Declaration, App_Handler_Type, RTC_App_Handler_Status_Instance
from .handler_callbacks import install_handler, uninstall_handler, uninstall_all_handlers


def merge_handler_subscriptions(raw_results: dict, logger=None) -> dict:
    """
    Merge per-block App_Handler_Subscription_Declaration lists (as returned by
    hook_get_app_handler_subscriptions) into one dict keyed by handler_type_name ->
    {"subscriber_count": int, "min_freq": float}.

    "Most-permissive" merge: when multiple blocks subscribe to the same handler type, the
    MINIMUM frequency_filter_seconds across all subscriptions wins, so no subscriber is
    starved of events it requested.

    A misbehaving block (non-list return, a list containing something other than an
    App_Handler_Subscription_Declaration, a handler_type that isn't a real App_Handler_Type
    member, or a negative/non-numeric frequency_filter_seconds) has that one entry skipped
    with a warning — never raises, so one broken block can't break polling for every other
    block. Pulled out of Wrapper_App_Handlers.repoll() so it's testable without touching
    bpy.app.handlers at all.
    """
    merged: dict = {}
    for block_id, result in raw_results.items():
        if not isinstance(result, list):
            if logger:
                logger.warning(
                    f"repoll: block '{block_id}' returned "
                    f"{type(result)!r} from poll hook — expected list, skipping"
                )
            continue
        for item in result:
            if not isinstance(item, App_Handler_Subscription_Declaration):
                if logger:
                    logger.warning(
                        f"repoll: block '{block_id}' returned "
                        f"non-App_Handler_Subscription_Declaration item — skipping"
                    )
                continue
            if not isinstance(item.handler_type, App_Handler_Type):
                if logger:
                    logger.warning(
                        f"repoll: block '{block_id}' subscribed with handler_type "
                        f"{item.handler_type!r}, not a real App_Handler_Type member — skipping"
                    )
                continue
            freq = item.frequency_filter_seconds
            if isinstance(freq, bool) or not isinstance(freq, (int, float)) or freq < 0:
                if logger:
                    logger.warning(
                        f"repoll: block '{block_id}' subscribed to '{item.handler_type.name}' with "
                        f"invalid frequency_filter_seconds={freq!r} (must be a number >= 0) — skipping"
                    )
                continue
            type_name = item.handler_type.name
            if type_name not in merged:
                merged[type_name] = {
                    "subscriber_count": 0,
                    "min_freq": item.frequency_filter_seconds,
                }
            merged[type_name]["subscriber_count"] += 1
            # Most-permissive merge: take the minimum (most frequent) rate limit
            merged[type_name]["min_freq"] = min(
                merged[type_name]["min_freq"], item.frequency_filter_seconds
            )
    return merged


class Wrapper_App_Handlers(Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer):
    """
    Feature Wrapper for block_app_handlers.

    Manages the lifecycle of all bpy.app.handlers registrations (except block_core's
    structural handlers: load_post, undo_post, redo_post).

    Downstream blocks declare which handlers they need via hook_get_app_handler_subscriptions.
    This wrapper:
      - Polls downstream on startup (via hook_post_startup subscription) and on demand.
      - Installs/uninstalls Blender callbacks based on which types have subscribers.
      - Fires per-type notification hooks when Blender triggers the handler.
      - Guards against re-entrant handler execution (saves from save_pre, etc.).
    """

    # ----------------------------------------------------------
    # Public API

    @classmethod
    def repoll(cls) -> None:
        """
        Re-poll all downstream blocks for their handler subscriptions, then reconcile
        which bpy.app.handlers are installed.

        Called automatically via hook_post_startup on addon start.
        Call this manually from any downstream block when its subscription needs change
        at runtime (e.g. when a tool activates / deactivates).
        """
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        logger.debug("repoll: polling downstream blocks")

        # 1. Poll all subscribers
        raw_results = Wrapper_Hooks.run_hooked_funcs(Block_Hook_Sources.hook_get_app_handler_subscriptions)

        # 2. Merge subscriptions per handler type (pure function — see merge_handler_subscriptions)
        merged = merge_handler_subscriptions(raw_results, logger)

        # 3. Load existing status instances
        existing_status: dict[str, RTC_App_Handler_Status_Instance] = {
            inst.handler_type_name: inst
            for inst in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST)
        }

        # 4. Uninstall handlers that no longer have subscribers
        stale_types = set(existing_status.keys()) - set(merged.keys())
        for type_name in stale_types:
            uninstall_handler(type_name, logger)

        # 5. Build new status list
        new_status_list: list[RTC_App_Handler_Status_Instance] = []

        for type_name, data in merged.items():
            inst = existing_status.get(type_name)
            if inst is None:
                inst = RTC_App_Handler_Status_Instance(handler_type_name=type_name)

            inst.subscriber_count          = data["subscriber_count"]
            inst.frequency_filter_seconds  = data["min_freq"]
            inst.is_enabled                = True  # always reset on refresh per spec

            if not inst.is_registered:
                if install_handler(type_name, logger):
                    inst.is_registered      = True
                    inst.fire_count         = 0
                    inst.last_fired_timestamp = 0.0
            
            new_status_list.append(inst)

        # Sort alphabetically for consistent UIList display
        new_status_list.sort(key=lambda x: x.handler_type_name)

        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST, new_status_list)

        # 6. Sync to BL mirror
        cls._sync_status_to_BL()

        logger.info(
            f"repoll: {len(new_status_list)} handler type(s) active, "
            f"{len(stale_types)} removed"
        )

    # TODO: implement update_BL
    @classmethod
    def set_handler_enabled(cls, handler_type_name: str, is_enabled: bool, update_BL: bool = True) -> None:
        """
        Enable or disable the notification hook for a specific handler type.
        When disabled the Blender callback still fires, but the downstream hook is suppressed.
        Called by the BL property update callback when the user toggles the UIList checkbox.
        """
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        status_list = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST)
        for inst in status_list:
            if inst.handler_type_name == handler_type_name:
                inst.is_enabled = is_enabled
                logger.debug(f"set_handler_enabled: '{handler_type_name}' -> {is_enabled}")
                return
        logger.warning(f"set_handler_enabled: '{handler_type_name}' not found in status list")

    # ----------------------------------------------------------
    # Abstract_Feature_Wrapper implementation

    @classmethod
    def _init_wrapper(cls) -> bool:
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        logger.debug("Wrapper_App_Handlers._init_wrapper — ready (subscriptions loaded via hook_post_startup)")
        return True

    @classmethod
    def _remove_wrapper(cls) -> None:
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        logger.debug("Wrapper_App_Handlers._remove_wrapper — uninstalling all handlers")
        uninstall_all_handlers(logger)
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.APP_HANDLER_STATUS_LIST, [])
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.APP_HANDLERS_CURRENTLY_EXECUTING, set())

    # ----------------------------------------------------------
    # Abstract_BL_RTC_List_Syncronizer implementation

    @classmethod
    def _update_RTC_with_mirrored_BL_data(cls, event, FWC_instance, data_mirror_instance):
        """
        BL → RTC direction.
        BL data is ephemeral display only — RTC is the sole truth source for this block.
        This is a no-op; the only BL field that can change is is_enabled (via update callback),
        which is handled directly by set_handler_enabled().
        """
        pass

    @classmethod
    def _update_BL_with_mirrored_RTC_data(cls, event, FWC_instance, data_mirror_instance):
        """
        RTC → BL direction. Push current status list to the BL CollectionProperty.
        Called during data-mirror sync (startup / undo / redo).
        """
        cls._sync_status_to_BL()

    # ----------------------------------------------------------
    # Internal helpers

    @classmethod
    def _sync_status_to_BL(cls) -> None:
        """
        Rebuild the BL handler_status_mirror CollectionProperty from the RTC status list.
        Guarded against re-entrant sync via is_cache_flagged_as_syncing.
        """
        logger = get_logger(Block_Loggers.APP_HANDLERS_LIFECYCLE)
        cache_key = Block_RTC_Members.APP_HANDLER_STATUS_LIST

        try:
            props = bpy.context.scene.dgblocks_app_handlers_props
        except AttributeError:
            logger.warning("_sync_status_to_BL: bpy.context.scene not available")
            return

        if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key):
            return

        status_list = Wrapper_Runtime_Cache.get_cache(cache_key)

        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key, True)
        try:
            props.handler_status_mirror.clear()
            for inst in status_list:
                row = props.handler_status_mirror.add()
                row.handler_type_name         = inst.handler_type_name
                row.is_enabled                = inst.is_enabled
                row.is_registered             = inst.is_registered
                row.subscriber_count          = inst.subscriber_count
                row.frequency_filter_seconds  = inst.frequency_filter_seconds
        finally:
            Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key, False)

        logger.debug(f"_sync_status_to_BL: synced {len(status_list)} row(s)")

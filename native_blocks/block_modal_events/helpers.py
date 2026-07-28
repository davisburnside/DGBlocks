
import time
import bpy

# Addon-level imports
from ...addon_helpers.generic_tools import get_exception_last_n_lines

from ...addon_helpers.data_structures import Enum_Sync_Events

# Inter-block imports
from ...native_blocks.block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.hooks.feature_wrapper import Wrapper_Hooks
from ...native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .data_structures import Modal_Event_Category, RTC_Modal_Listener_Instance

# Aliases
cache_key_listeners = Block_RTC_Members.LISTENERS

# ==============================================================================================================================
# ROUTER RUNNING STATE
# ==============================================================================================================================
# A modal operator does not survive a file reload, and Blender exposes no API to enumerate
# running modals. We track the single router operator's running state here so we never invoke
# it twice and can detect that it must be re-launched after load/register.

_router_is_running: bool = False


def is_router_running() -> bool:
    return _router_is_running


def _set_router_running(value: bool) -> None:
    global _router_is_running
    _router_is_running = value

# ==============================================================================================================================
# EVENT CLASSIFICATION
# ==============================================================================================================================

_MOUSE_CLICK_TYPES = {"LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE", "BUTTON4MOUSE", "BUTTON5MOUSE",
                      "BUTTON6MOUSE", "BUTTON7MOUSE"}
_MOUSE_MOVE_TYPES  = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}
_SCROLL_TYPES      = {"WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
                      "TRACKPADPAN", "TRACKPADZOOM"}
_WINDOW_TYPES      = {"WINDOW_DEACTIVATE"}


def classify_event(event) -> Modal_Event_Category:
    """Map a Blender event to one coarse Modal_Event_Category for ignore_* filtering."""
    etype = event.type
    if etype in _MOUSE_MOVE_TYPES:
        return Modal_Event_Category.MOUSE_MOVE
    if etype in _SCROLL_TYPES:
        return Modal_Event_Category.SCROLL
    if etype in _MOUSE_CLICK_TYPES:
        return Modal_Event_Category.MOUSE_CLICK
    if etype in _WINDOW_TYPES:
        return Modal_Event_Category.WINDOW
    # Keyboard events expose a non-empty unicode OR an alphanumeric/named key with PRESS/RELEASE.
    # Anything left that is not a known non-keyboard type is treated as keyboard.
    if etype not in {"TIMER", "NDOF_MOTION", "NONE"}:
        return Modal_Event_Category.KEYBOARD
    return Modal_Event_Category.OTHER


# Maps each category to the listener attribute that suppresses it.
_CATEGORY_TO_IGNORE_ATTR = {
    Modal_Event_Category.MOUSE_CLICK: "ignore_mouse_click_events",
    Modal_Event_Category.MOUSE_MOVE:  "ignore_mouse_move",
    Modal_Event_Category.SCROLL:      "ignore_scroll_events",
    Modal_Event_Category.KEYBOARD:    "ignore_keyboard_events",
    Modal_Event_Category.WINDOW:      "ignore_window_events",
}


def _listener_ignores_category(listener: RTC_Modal_Listener_Instance, category: Modal_Event_Category) -> bool:
    attr = _CATEGORY_TO_IGNORE_ATTR.get(category)
    if attr is None:
        return False  # OTHER — always delivered
    return getattr(listener, attr, False)

# ==============================================================================================================================
# VALIDATION
# ==============================================================================================================================

def validate_listener_definitions(defs_by_block: dict) -> None:
    """
    Validate the per-block lists of Modal_Listener_Definition returned by the hook.
    Raises ValueError if any check fails. Runs before any RTC/bpy state is mutated.

      - At most one definition per block (the listener is keyed by src_block_id).
      - on_event must be callable.
    """
    for block_id, defs in defs_by_block.items():
        if len(defs) > 1:
            raise ValueError(
                f"Block '{block_id}' returned {len(defs)} Modal_Listener_Definition objects. "
                f"Each block may register at most ONE modal listener (keyed by src_block_id)."
            )
        for d in defs:
            if not callable(d.on_event):
                raise ValueError(
                    f"Block '{block_id}': Modal_Listener_Definition.on_event must be callable, "
                    f"got {type(d.on_event)}."
                )

# ==============================================================================================================================
# CLEAR / REBUILD
# ==============================================================================================================================

def _clear_all_listeners(include_BL_data: bool = True) -> None:

    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, [])

    if include_BL_data:
        modal_props = bpy.context.scene.dgblocks_modal_events_props
        modal_props.listener_mirror.clear()
        modal_props.listener_mirror_selected_idx = 0

    logger.debug("_clear_all_listeners: complete")


def _rebuild_all_listeners(event: Enum_Sync_Events, sync_BL: bool = True) -> None:
    """
    Full rebuild cycle:
        1. Clear existing RTC_Modal_Listener_Instance objects.
        2. Fire hook_get_modal_listener_definitions — downstream blocks return a (single-element)
           list of Modal_Listener_Definition objects.
        3. Validate (one definition per block, callable on_event).
        4. Create RTC_Modal_Listener_Instance objects, keyed by src_block_id.
        5. Restore is_enabled from the BL listener_mirror (user preference survives rebuilds).
        6. Sync BL listener_mirror rows to reflect the current live listener set.

    Note: this rebuilds the listener registry only. It does NOT start/stop the router operator
    (that is controlled by the enable_modal scene property). Listeners are read live from the
    RTC by the router on every event, so a rebuild while the modal is running takes effect
    immediately without restarting the modal.
    """
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    logger.debug("_rebuild_all_listeners: starting")

    # Capture current is_enabled before clearing, so user toggles survive the rebuild
    modal_props = bpy.context.scene.dgblocks_modal_events_props
    bl_enabled_by_block: dict = {
        row.src_block_id: row.is_enabled
        for row in modal_props.listener_mirror
    }

    _clear_all_listeners()

    # Collect Modal_Listener_Definitions from all downstream blocks
    defs_by_block = Wrapper_Hooks.run_hooked_funcs(
        hook_func_name=Block_Hook_Sources.hook_get_modal_listener_definitions,
        should_halt_on_exception=False,
    )

    if not defs_by_block or sum(len(v) for v in defs_by_block.values()) == 0:
        logger.info("_rebuild_all_listeners: no Modal_Listener_Definitions returned, returning early")
        modal_props.enable_modal = False
        return

    validate_listener_definitions(defs_by_block)

    # Build RTC_Modal_Listener_Instances (one per block)
    rtc_listeners = []
    for block_id, defs in defs_by_block.items():
        if len(defs) == 0:
            continue
        d = defs[0]
        is_enabled = bl_enabled_by_block.get(block_id, True)

        instance = RTC_Modal_Listener_Instance(
            src_block_id              = block_id,
            priority                  = d.priority,
            is_enabled                = is_enabled,
            ignore_mouse_click_events = d.ignore_mouse_click_events,
            ignore_mouse_move         = d.ignore_mouse_move,
            ignore_scroll_events      = d.ignore_scroll_events,
            ignore_keyboard_events    = d.ignore_keyboard_events,
            ignore_window_events      = d.ignore_window_events,
        )
        instance._on_event           = d.on_event
        instance._before_modal_start = d.before_modal_start
        instance._before_modal_end   = d.before_modal_end
        rtc_listeners.append(instance)
        logger.debug(
            f"Created listener src='{block_id}' priority={d.priority} enabled={is_enabled}"
        )

    # Stable, deterministic dispatch order: ascending priority, then block id
    rtc_listeners.sort(key=lambda i: (i.priority, i.src_block_id))

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, rtc_listeners)
    logger.info(f"_rebuild_all_listeners: created {len(rtc_listeners)} listener(s)")

    if sync_BL:
        FWC_instance, data_mirror_instance = Wrapper_Runtime_Cache.get_FWC_and_data_mirror(cache_key_listeners)
        Wrapper_Runtime_Cache.resync_single_data_mirror(
            event=Enum_Sync_Events,
            BL_is_truth_source=False,
            cache_key=cache_key_listeners,
            FWC_instance=FWC_instance,
            data_mirror_instance=data_mirror_instance,
            actions_denied=set(),
            logger=logger,
        )
        
    if not modal_props.enable_modal:
        modal_props.enable_modal = True

# ==============================================================================================================================
# ROUTER START / STOP HELPERS
# ==============================================================================================================================

def _get_enabled_listeners_sorted() -> list:
    listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS)
    enabled = [l for l in listeners if l.is_enabled]
    enabled.sort(key=lambda i: (i.priority, i.src_block_id))
    return enabled


def start_router() -> None:
    """Invoke the single router modal operator if it is not already running."""
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)

    if _router_is_running:
        logger.debug("start_router: router already running, skipping")
        return

    try:
        bpy.ops.dgblocks.modal_event_router("INVOKE_DEFAULT")
    except Exception:
        logger.error("start_router: failed to invoke router operator", exc_info=True)


def request_router_stop() -> None:
    """
    Request the router to stop. The router self-terminates on its next received event when it
    sees enable_modal == False. (Disabling typically resolves within one mouse-move.)
    """
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    logger.debug("request_router_stop: router will terminate on next event")
    # Nothing to invoke here — DGBLOCKS_OT_Modal_Event_Router.modal() checks enable_modal.


def _fire_before_modal_start(context) -> None:
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    now = time.time()
    for listener in _get_enabled_listeners_sorted():
        listener.modal_start_timestamp = now
        if listener._before_modal_start is None:
            continue
        try:
            listener._before_modal_start(listener, context)
        except Exception as e:
            listener.listener_error_str = get_exception_last_n_lines(2, e)
            listener.is_enabled = False
            logger.error(f"before_modal_start failed for '{listener.src_block_id}'", exc_info=True)


def _fire_before_modal_end(context, reason: str) -> None:
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    for listener in _get_enabled_listeners_sorted():
        if listener._before_modal_end is None:
            continue
        try:
            listener._before_modal_end(listener, context, reason)
        except Exception:
            logger.error(f"before_modal_end failed for '{listener.src_block_id}'", exc_info=True)

# ==============================================================================================================================
# ROUTER MODAL OPERATOR — single instance, fans events to ordered logical listeners
# ==============================================================================================================================

class DGBLOCKS_OT_Modal_Event_Router(bpy.types.Operator):
    """Single router modal operator that fans events to ordered, per-block modal listeners."""
    bl_idname = "dgblocks.modal_event_router"
    bl_label = "DGBlocks Modal Event Router"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)

        if is_router_running():
            logger.debug("router invoke: already running, cancelling duplicate")
            return {"CANCELLED"}

        try:
            _fire_before_modal_start(context)
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=Block_Hook_Sources.hook_modal_started,
                should_halt_on_exception=False,
                context=context,
            )
        except Exception:
            logger.error("router invoke: error during start hooks", exc_info=True)

        context.window_manager.modal_handler_add(self)
        _set_router_running(True)
        logger.info("Modal event router started")
        return {"RUNNING_MODAL"}

    def _end(self, context, reason: str):
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        try:
            _fire_before_modal_end(context, reason)
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=Block_Hook_Sources.hook_modal_ended,
                should_halt_on_exception=False,
                context=context,
                reason=reason,
            )
        except Exception:
            logger.error("router end: error during end hooks", exc_info=True)
        _set_router_running(False)
        logger.info(f"Modal event router ended (reason='{reason}')")

    def modal(self, context, event):
        logger = get_logger(Block_Loggers.MODAL_EVENTS)

        try:
            # Master toggle off → terminate (fires end hooks)
            try:
                enabled = context.scene.dgblocks_modal_events_props.enable_modal
            except AttributeError:
                enabled = False
            if not enabled:
                self._end(context, "disabled")
                return {"FINISHED"}

            category = classify_event(event)
            now = time.time()
            result = {"PASS_THROUGH"}

            for listener in _get_enabled_listeners_sorted():
                if _listener_ignores_category(listener, category):
                    continue

                try:
                    ret = listener._on_event(listener, context, event)
                except Exception as e:
                    # Disable the offender, keep the router alive
                    listener.listener_error_str = get_exception_last_n_lines(2, e)
                    listener.is_enabled = False
                    logger.error(
                        f"on_event failed for '{listener.src_block_id}' — listener disabled",
                        exc_info=True,
                    )
                    continue

                listener.event_count += 1
                listener.last_event_timestamp = now
                if ret:
                    listener.last_return = str(ret)

                # First non-PASS_THROUGH return wins and short-circuits remaining listeners
                if ret and ret != {"PASS_THROUGH"}:
                    result = ret
                    break

            # A listener may end the modal explicitly
            if result in ({"FINISHED"}, {"CANCELLED"}):
                self._end(context, "listener_requested")
                return result

            return result

        except Exception:
            # Never let an exception escape the modal callback (would silently kill the modal)
            logger.error("Unhandled exception in modal router", exc_info=True)
            return {"PASS_THROUGH"}

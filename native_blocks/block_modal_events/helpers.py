
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
from .data_structures import (
    Modal_Event_Category,
    Modal_Listener_End_Info,
    Modal_Listener_End_Reason,
    RTC_Modal_Listener_Instance,
    User_Input_Capture_Instance,
)
from .workspace_tools import get_active_logical_tool_id

# Aliases
cache_key_listeners = Block_RTC_Members.LISTENERS

def _update_user_input_capture_instance(context, event, should_clear = False):
    """ Create new instance every event"""
    
    if should_clear:
        user_input_capture = User_Input_Capture_Instance() # All None'd fields
    else:
        user_input_capture = User_Input_Capture_Instance(
            mouse_x = event.mouse_x,
            mouse_y = event.mouse_y,
            shift = event.shift,
            ctrl = event.ctrl,
            alt = event.alt,
            oskey = event.oskey,
            value = event.value,
            area_id = context.area.as_pointer() if context.area else None,
            area_type = context.area.type if context.area else None,
            mouse_x_area = event.mouse_x - context.area.x if context.area else None,
            mouse_y_area = event.mouse_y - context.area.y if context.area else None,
            region_type = context.region.type if context.region else None,
            workspace_name = context.workspace.name if context.workspace else None,
            window_id = context.window.as_pointer() if context.window else None,
        )

    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.USER_INPUT_CAPTURE, user_input_capture)

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
      - before_modal_start / before_modal_end must be callable when provided (optional, so
        None is fine — but anything else, e.g. a truthy non-callable left over from a typo,
        would otherwise only fail much later, when the router actually tries to call it).
      - priority must be an int — it drives dispatch ordering.
      - workspace_tool_ids must be a tuple/list, not a bare string. A bare string is a classic
        footgun here: iterating "my.tool" elsewhere yields characters, not one tool id.
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
            for field_name in ("before_modal_start", "before_modal_end"):
                value = getattr(d, field_name)
                if value is not None and not callable(value):
                    raise ValueError(
                        f"Block '{block_id}': Modal_Listener_Definition.{field_name} must be "
                        f"callable or None, got {type(value)}."
                    )
            if not isinstance(d.priority, int) or isinstance(d.priority, bool):
                raise ValueError(
                    f"Block '{block_id}': Modal_Listener_Definition.priority must be an int, "
                    f"got {type(d.priority)}."
                )
            if isinstance(d.workspace_tool_ids, str) or not isinstance(d.workspace_tool_ids, (tuple, list)):
                raise ValueError(
                    f"Block '{block_id}': Modal_Listener_Definition.workspace_tool_ids must be a "
                    f"tuple/list of tool ids, not {type(d.workspace_tool_ids)} — a bare string would "
                    f"iterate as individual characters."
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


def _listener_end_info(listener: RTC_Modal_Listener_Instance) -> Modal_Listener_End_Info:
    return Modal_Listener_End_Info(
        src_block_id=listener.src_block_id,
        priority=listener.priority,
        is_enabled=listener.is_enabled,
        workspace_tool_ids=listener.workspace_tool_ids,
        event_count=listener.event_count,
        last_return=listener.last_return,
        modal_start_timestamp=listener.modal_start_timestamp,
        last_event_timestamp=listener.last_event_timestamp,
        listener_error_str=listener.listener_error_str,
    )


def _sync_listener_mirror_from_RTC() -> None:
    """Refresh the existing BL mirror without polling listener definitions."""
    try:
        modal_props = bpy.context.scene.dgblocks_modal_events_props
    except (AttributeError, ReferenceError):
        return

    listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
    Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.LISTENERS, True)
    try:
        modal_props.listener_mirror.clear()
        for listener in listeners:
            row = modal_props.listener_mirror.add()
            row.src_block_id = listener.src_block_id
            row.priority = listener.priority
            row.is_enabled = listener.is_enabled
        modal_props.listener_mirror_selected_idx = min(
            modal_props.listener_mirror_selected_idx,
            max(0, len(listeners) - 1),
        )
    finally:
        Wrapper_Runtime_Cache.flag_cache_as_syncing(Block_RTC_Members.LISTENERS, False)


def _notify_listener_ended(listener, context, reason: Modal_Listener_End_Reason) -> None:
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    try:
        if listener._before_modal_end is not None:
            listener._before_modal_end(listener, context, reason.value)
    except Exception:
        logger.error(f"before_modal_end failed for '{listener.src_block_id}'", exc_info=True)

    try:
        Wrapper_Hooks.run_hooked_funcs(
            hook_func_name=Block_Hook_Sources.hook_modal_listener_ended,
            should_halt_on_exception=False,
            context=context,
            reason=reason.value,
            listener_info=_listener_end_info(listener),
        )
    except Exception:
        logger.error(
            f"Unable to publish listener-ended hook for '{listener.src_block_id}'",
            exc_info=True,
        )


def _remove_listener(listener, context, reason: Modal_Listener_End_Reason, sync_BL=True) -> None:
    _notify_listener_ended(listener, context, reason)
    listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
    # Preserve list identity so the shared router generation remains valid for survivors.
    listeners[:] = [item for item in listeners if item is not listener]
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, listeners)
    if sync_BL:
        _sync_listener_mirror_from_RTC()


def end_all_listeners(reason: Modal_Listener_End_Reason, context=None, include_BL_data=True) -> None:
    """End all current listeners without polling downstream definitions."""
    context = context or bpy.context
    listeners = list(Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or [])
    for listener in listeners:
        _notify_listener_ended(listener, context, reason)
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, [])
    if include_BL_data:
        _sync_listener_mirror_from_RTC()


def _rebuild_all_listeners(event: Enum_Sync_Events, sync_BL: bool = True) -> tuple[bool, bool]:
    """
    Full rebuild cycle:
        1. Clear existing RTC_Modal_Listener_Instance objects.
        2. Fire hook_get_modal_listener_definitions — downstream blocks return a (single-element)
           list of Modal_Listener_Definition objects.
        3. Validate (one definition per block, callable on_event).
        4. Create RTC_Modal_Listener_Instance objects, keyed by src_block_id.
        5. Restore is_enabled from the BL listener_mirror (user preference survives rebuilds).
        6. Sync BL listener_mirror rows to reflect the current live listener set.

    Returns ``(had_unbound_listeners, has_unbound_listeners)`` so the public repoll API launches
    the raw router only when a listener without workspace-tool bindings needs it. Tool-bound
    listeners receive events from their active tool keymaps instead.
    """
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    logger.debug("_rebuild_all_listeners: starting")

    old_registry = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
    old_listeners = list(old_registry)
    had_unbound_listeners = any(not listener.workspace_tool_ids for listener in old_listeners)

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
        for listener in old_listeners:
            _notify_listener_ended(listener, bpy.context, Modal_Listener_End_Reason.DEFINITION_REMOVED)
        if sync_BL:
            _sync_listener_mirror_from_RTC()
        return had_unbound_listeners, False

    validate_listener_definitions(defs_by_block)

    declared_block_ids = {block_id for block_id, defs in defs_by_block.items() if defs}
    for listener in old_listeners:
        if listener.src_block_id not in declared_block_ids:
            _notify_listener_ended(
                listener, bpy.context, Modal_Listener_End_Reason.DEFINITION_REMOVED
            )

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
            workspace_tool_ids        = tuple(d.workspace_tool_ids),
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

    if old_listeners:
        # Keep the live router's generation token valid for a normal non-empty rebuild.
        old_registry[:] = rtc_listeners
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, old_registry)
    else:
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.LISTENERS, rtc_listeners)
    logger.info(f"_rebuild_all_listeners: created {len(rtc_listeners)} listener(s)")

    if sync_BL:
        _sync_listener_mirror_from_RTC()

    has_unbound_listeners = any(not listener.workspace_tool_ids for listener in rtc_listeners)
    return had_unbound_listeners, has_unbound_listeners

# ==============================================================================================================================
# ROUTER START / STOP HELPERS
# ==============================================================================================================================

def _get_enabled_listeners_sorted() -> list:
    listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS)
    enabled = [l for l in listeners if l.is_enabled]
    enabled.sort(key=lambda i: (i.priority, i.src_block_id))
    return enabled


def _has_unbound_listeners() -> bool:
    listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
    return any(not listener.workspace_tool_ids for listener in listeners)


def _find_view3d_window_override():
    """Return a consistent window/screen/VIEW_3D/WINDOW tuple, or None."""
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return None
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is not None:
                return {"window": window, "screen": screen, "area": area, "region": region}
    return None


def start_router() -> bool:
    """Invoke the router in a valid 3D-view context; return whether invocation succeeded."""
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    try:
        override = _find_view3d_window_override()
        if override is None:
            logger.warning("start_router: no VIEW_3D WINDOW context is currently available")
            return False
        with bpy.context.temp_override(**override):
            result = bpy.ops.dgblocks.modal_event_router("INVOKE_DEFAULT")
        return result == {"RUNNING_MODAL"}
    except Exception:
        logger.error("start_router: failed to invoke router operator", exc_info=True)
        return False


def _start_listener_if_needed(listener, context) -> None:
    logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
    if listener.modal_start_timestamp != 0.0:
        return
    listener.modal_start_timestamp = time.time()
    if listener._before_modal_start is not None:
        try:
            listener._before_modal_start(listener, context)
        except Exception as e:
            listener.listener_error_str = get_exception_last_n_lines(2, e)
            listener.is_enabled = False
            logger.error(f"before_modal_start failed for '{listener.src_block_id}'", exc_info=True)


def _fire_before_modal_start(context) -> None:
    for listener in _get_enabled_listeners_sorted():
        if not listener.workspace_tool_ids:
            _start_listener_if_needed(listener, context)


def dispatch_event_to_listeners(context, event, logical_tool_id: str | None = None):
    """Dispatch one event through the shared listener pipeline.

    ``logical_tool_id=None`` is the raw-router path and intentionally selects only unbound
    listeners. A concrete logical id is the WorkSpaceTool keymap path and selects only listeners
    that reference that id. This makes the two event sources mutually exclusive.
    """
    logger = get_logger(Block_Loggers.MODAL_EVENTS)
    category = classify_event(event)
    now = time.time()
    result = {"PASS_THROUGH"}

    _update_user_input_capture_instance(context, event)

    ending_listener = None
    for listener in _get_enabled_listeners_sorted():
        if _listener_ignores_category(listener, category):
            continue
        if logical_tool_id is None:
            if listener.workspace_tool_ids:
                continue
        elif logical_tool_id not in listener.workspace_tool_ids:
            continue

        _start_listener_if_needed(listener, context)
        if not listener.is_enabled:
            continue

        try:
            ret = listener._on_event(listener, context, event)
        except Exception as e:
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

        if ret and ret != {"PASS_THROUGH"}:
            result = ret
            ending_listener = listener
            break

    if result in ({"FINISHED"}, {"CANCELLED"}):
        reason = (
            Modal_Listener_End_Reason.FINISHED
            if result == {"FINISHED"}
            else Modal_Listener_End_Reason.CANCELLED
        )
        _remove_listener(ending_listener, context, reason)

    return result


class DGBLOCKS_OT_Workspace_Tool_Listener_Event(bpy.types.Operator):
    """Forward one active WorkSpaceTool keymap event to matching logical listeners."""

    bl_idname = "dgblocks.workspace_tool_listener_event"
    bl_label = "DGBlocks Workspace Tool Listener Event"
    bl_options = {"INTERNAL"}

    logical_tool_id: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore

    def invoke(self, context, event):
        logger = get_logger(Block_Loggers.MODAL_EVENTS)
        try:
            # Guard against stale keymap entries and direct operator calls. Blender normally only
            # reaches this through the active tool's keymap.
            if get_active_logical_tool_id(context) != self.logical_tool_id:
                return {"PASS_THROUGH"}

            result = dispatch_event_to_listeners(
                context, event, logical_tool_id=self.logical_tool_id
            )
            # This is a one-shot keymap operator, not a Blender modal handler. RUNNING_MODAL means
            # "consume this event" at listener level and therefore maps to FINISHED here.
            if result == {"PASS_THROUGH"} or not result:
                return {"PASS_THROUGH"}
            return {"FINISHED"}
        except Exception:
            logger.error("Unhandled workspace-tool listener event", exc_info=True)
            return {"PASS_THROUGH"}


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

        listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
        if not _has_unbound_listeners():
            logger.debug("router invoke: no unbound listeners require raw routing")
            return {"CANCELLED"}

        # The registry object is the router generation token. Rebuild/reload replaces the list,
        # allowing a stale pre-reload modal to identify itself without a global running flag.
        self._listener_registry = listeners

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
        logger.info("Modal event router started")
        return {"RUNNING_MODAL"}

    def _end(self, context, reason: str):
        logger = get_logger(Block_Loggers.MODAL_LIFECYCLE)
        try:
            Wrapper_Hooks.run_hooked_funcs(
                hook_func_name=Block_Hook_Sources.hook_modal_ended,
                should_halt_on_exception=False,
                context=context,
                reason=reason,
            )
        except Exception:
            logger.error("router end: error during end hooks", exc_info=True)
        _update_user_input_capture_instance(context, event = None, should_clear = True)
        logger.info(f"Modal event router ended (reason='{reason}')")

    def modal(self, context, event):
        logger = get_logger(Block_Loggers.MODAL_EVENTS)

        try:
            current_listeners = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.LISTENERS) or []
            if current_listeners is not self._listener_registry:
                self._end(context, Modal_Listener_End_Reason.ROUTER_SHUTDOWN.value)
                return {"FINISHED"}
            if not _has_unbound_listeners():
                self._end(context, Modal_Listener_End_Reason.ROUTER_SHUTDOWN.value)
                return {"FINISHED"}

            result = dispatch_event_to_listeners(context, event)

            # FINISHED/CANCELLED remove only the returning logical listener. They never trigger
            # another declaration poll and never terminate unrelated listeners.
            if result in ({"FINISHED"}, {"CANCELLED"}):
                if not _has_unbound_listeners():
                    self._end(context, Modal_Listener_End_Reason.ROUTER_SHUTDOWN.value)
                    return {"FINISHED"}
                return {"RUNNING_MODAL"}

            return result

        except Exception:
            # Never let an exception escape the modal callback (would silently kill the modal)
            logger.error("Unhandled exception in modal router", exc_info=True)
            return {"PASS_THROUGH"}

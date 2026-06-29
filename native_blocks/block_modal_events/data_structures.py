
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Callable, Optional

# ==============================================================================================================================
# EVENT CLASSIFICATION
# ==============================================================================================================================

class Modal_Event_Category(StrEnum):
    """
    Coarse classification of incoming modal events. Each category (except OTHER) maps to one
    of the per-listener ignore_* flags on Modal_Listener_Definition / RTC_Modal_Listener_Instance.
    OTHER events (e.g. NDOF) are always delivered to every enabled listener.
    """

    @staticmethod  # Preserves uppercase str (lowercase by python default)
    def _generate_next_value_(name, *args):
        return name

    MOUSE_CLICK = auto()
    MOUSE_MOVE  = auto()
    SCROLL      = auto()
    KEYBOARD    = auto()
    WINDOW      = auto()
    OTHER       = auto()

# ==============================================================================================================================
# DECLARATIVE CONFIG DATACLASSES
# ==============================================================================================================================

@dataclass
class Modal_Listener_Definition:
    """
    Flat descriptor for a single block's interest in modal events. Supplied by downstream
    blocks inside hook_get_modal_listener_definitions. A block may return at most ONE
    definition — the listener is keyed by the source block id.

    on_event is called by the router for each (non-ignored) event while the listener is
    enabled. Signature:
        on_event(listener_instance: RTC_Modal_Listener_Instance, context, event) -> set | None
    Return one of Blender's modal return sets ({'PASS_THROUGH'}, {'RUNNING_MODAL'},
    {'FINISHED'}, {'CANCELLED'}) or None (treated as {'PASS_THROUGH'}). The first listener
    (in ascending priority order) to return a non-PASS_THROUGH value wins for that event.

    before_modal_start / before_modal_end are called once, at true router start / stop:
        before_modal_start(listener_instance, context) -> None
        before_modal_end(listener_instance, context, reason: str) -> None
    """
    priority: int = 0                       # lower = dispatched earlier
    on_event: Optional[Callable] = None
    before_modal_start: Optional[Callable] = None
    before_modal_end:   Optional[Callable] = None

    # Per-event-category opt-outs
    ignore_mouse_click_events: bool = False
    ignore_mouse_move:         bool = False
    ignore_scroll_events:      bool = False
    ignore_keyboard_events:    bool = False
    ignore_window_events:      bool = False


@dataclass
class RTC_Modal_Listener_Instance:
    """
    Live runtime record for a single block's modal-event subscription.
    Fully managed by Wrapper_Modal_Manager — do not construct directly.
    """

    # Identity — src_block_id is the unique key (one listener per block)
    src_block_id: str
    priority: int = 0

    # Status
    is_enabled: bool = True

    # Per-event-category opt-outs (mirrored from the definition)
    ignore_mouse_click_events: bool = False
    ignore_mouse_move:         bool = False
    ignore_scroll_events:      bool = False
    ignore_keyboard_events:    bool = False
    ignore_window_events:      bool = False

    # Statistics
    event_count: int = 0
    last_return: Optional[str] = None        # e.g. "{'PASS_THROUGH'}" / "{'RUNNING_MODAL'}"
    modal_start_timestamp: float = 0.0       # set at true router start
    last_event_timestamp: float = 0.0
    listener_error_str: Optional[str] = None  # None = healthy; set on exception, clears is_enabled

    # Callbacks — set at creation time from the Modal_Listener_Definition
    _on_event:           Optional[Callable] = field(init=False, default=None, repr=False)
    _before_modal_start: Optional[Callable] = field(init=False, default=None, repr=False)
    _before_modal_end:   Optional[Callable] = field(init=False, default=None, repr=False)

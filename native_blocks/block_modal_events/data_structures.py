
from dataclasses import dataclass, field
from enum import StrEnum, auto
import time
from typing import Any, Callable, Optional

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


class Modal_Listener_End_Reason(StrEnum):
    """Why a listener left the live modal-listener registry."""

    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"
    DEFINITION_REMOVED = "DEFINITION_REMOVED"
    ROUTER_SHUTDOWN = "ROUTER_SHUTDOWN"
    ADDON_SHUTDOWN = "ADDON_SHUTDOWN"


@dataclass
class User_Input_Capture_Instance:
    """
    Capture all relevant modal event details for mouse movement.
    All fields are updated every event if a modals are active, even if some fields are ignored.
    This instance can be read in the RTC when the modal is running
    """
    
    # Core event data
    last_type: str = None  # 'MOUSEMOVE', 'LEFTMOUSE', etc.
    mouse_x: int = None  # Window x position
    mouse_y: int = None  # Window y position
    shift: bool = None
    ctrl: bool = None
    alt: bool = None
    oskey: bool  = None # Windows key / Command key
    value: str  = None # 'PRESS', 'RELEASE', 'CLICK', etc.
    event_time: float = None
    
    # Context info
    window_id: Optional[int] = None
    area_id: Optional[int] = None
    area_type: Optional[str] = None  # 'VIEW_3D', 'NODE_EDITOR', etc.
    region_type: Optional[str] = None  # 'WINDOW', 'HEADER', etc.
    workspace_name: Optional[str] = None
    
    # Derived positions
    mouse_x_area: Optional[int] = None  # Position within current area
    mouse_y_area: Optional[int] = None
    
    @property
    def pos_window(self) -> tuple[int, int]:
        """Return (x, y) in window coordinates."""
        return (self.mouse_x, self.mouse_y)
    
    @property
    def pos_area(self) -> Optional[tuple[int, int]]:
        """Return (x, y) in area coordinates if available."""
        if self.mouse_x_area is not None and self.mouse_y_area is not None:
            return (self.mouse_x_area, self.mouse_y_area)
        return None
    
    @property
    def is_modifier_only(self) -> bool:
        """Check if this is just a modifier key event."""
        return self.type == 'TIMER' and not any([self.shift, self.ctrl, self.alt, self.oskey])

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

    # Empty means the listener is valid regardless of the active workspace tool. Values refer
    # to logical Modal_Workspace_Tool_Definition.tool_id values, not expanded placement ids.
    workspace_tool_ids: tuple[str, ...] = ()

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
    current_event: User_Input_Capture_Instance = None
    workspace_tool_ids: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class Modal_Listener_End_Info:
    """Immutable snapshot broadcast after a listener leaves the live registry."""

    src_block_id: str
    priority: int
    is_enabled: bool
    workspace_tool_ids: tuple[str, ...]
    event_count: int
    last_return: Optional[str]
    modal_start_timestamp: float
    last_event_timestamp: float
    listener_error_str: Optional[str]


@dataclass(frozen=True)
class Modal_Workspace_Tool_Placement:
    """One concrete editor/mode placement for a logical workspace tool."""

    space_type: str = "VIEW_3D"
    context_mode: Optional[str] = "OBJECT"
    keymap: Optional[tuple] = None


@dataclass(frozen=True)
class Modal_Workspace_Tool_Definition:
    """Logical tool declaration expanded to one WorkSpaceTool per placement at startup."""

    tool_id: str
    label: str
    placements: tuple[Modal_Workspace_Tool_Placement, ...]
    description: str = ""
    icon: Optional[str] = "ops.generic.select"
    image_icon_name: Optional[str] = None
    keymap: Optional[tuple] = None
    widget: Optional[str] = None
    cursor: Optional[str] = None
    after: frozenset[str] = frozenset()
    separator: bool = False
    group: bool = False
    draw_settings: Optional[Callable] = None


@dataclass
class RTC_Modal_Workspace_Tool_Instance:
    """One registered concrete WorkSpaceTool placement; runtime-only and never BL-mirrored."""

    src_block_id: str
    logical_tool_id: str
    concrete_tool_id: str
    space_type: str
    context_mode: Optional[str]
    image_icon_name: Optional[str]
    fallback_icon: str
    icon_handle: str
    actual_tool_class: Any


from __future__ import annotations

from dataclasses import dataclass, field
from enum import auto

from ...addon_helpers.data_structures import String_Comparable_Mixin


# ==============================================================================================================================
# APP HANDLER TYPE ENUM
# Member .name == the exact bpy.app.handlers attribute name AND the notification hook suffix.
# ==============================================================================================================================

class App_Handler_Type(String_Comparable_Mixin):
    """
    Enum of all bpy.app.handlers types managed by block_app_handlers.

    Member .name is the exact bpy.app.handlers attribute name and is used to construct
    the notification hook name:
        App_Handler_Type.save_pre  →  hook_app_handler_save_pre

    NOT managed by this block (block_core structural handlers):
        load_post, undo_post, redo_post
    """
    # File I/O
    save_pre              = auto()
    save_post             = auto()
    load_pre              = auto()
    # Depsgraph
    depsgraph_update_post = auto()
    depsgraph_update_pre  = auto()
    # Render
    render_init           = auto()
    render_pre            = auto()
    render_post           = auto()
    render_write          = auto()
    render_stats          = auto()
    render_cancel         = auto()
    render_complete       = auto()
    # Bake
    object_bake_pre       = auto()
    object_bake_complete  = auto()
    object_bake_cancel    = auto()
    # Animation
    frame_change_pre      = auto()
    frame_change_post     = auto()
    # Annotation
    annotation_pre        = auto()
    annotation_post       = auto()
    # Compositing
    composite_pre         = auto()
    composite_post        = auto()
    composite_cancel      = auto()
    # Version / XR
    version_update        = auto()
    xr_session_start_pre  = auto()
    xr_session_end        = auto()


# ==============================================================================================================================
# SUBSCRIPTION DECLARATION
# Submitted by downstream blocks inside hook_get_app_handler_subscriptions.
# ==============================================================================================================================

@dataclass
class App_Handler_Subscription_Declaration:
    """
    Declaration submitted by a downstream block via hook_get_app_handler_subscriptions.

    handler_type
        Which bpy.app.handler event to subscribe to.

    frequency_filter_seconds
        Minimum seconds that must elapse between notification-hook fires for this
        handler type. 0.0 = no rate limit (fire every time Blender triggers the handler).
        When multiple blocks subscribe to the same type, the MINIMUM across all
        subscriptions is used — "most-permissive" merge — so no subscriber is
        starved of events it requested.

    Example:
        def hook_get_app_handler_subscriptions():
            return [
                App_Handler_Subscription_Declaration(
                    handler_type = App_Handler_Type.save_pre,
                ),
                App_Handler_Subscription_Declaration(
                    handler_type             = App_Handler_Type.frame_change_post,
                    frequency_filter_seconds = 0.5,
                ),
            ]
    """
    handler_type:             App_Handler_Type
    frequency_filter_seconds: float = 0.0


# ==============================================================================================================================
# RTC STATUS INSTANCE
# One record per active handler type; managed exclusively by Wrapper_App_Handlers.
# ==============================================================================================================================

@dataclass
class RTC_App_Handler_Status_Instance:
    """
    Runtime record for a single app handler type.
    Managed by Wrapper_App_Handlers — do not construct directly.

    handler_type_name
        Key field. Matches App_Handler_Type member .name (e.g. "save_pre").

    is_registered
        True when the Blender callback is currently appended to the corresponding
        bpy.app.handlers list. Updated by Wrapper_App_Handlers.repoll().

    is_enabled
        User-facing toggle. If False the Blender callback still fires, but the
        downstream notification hook is suppressed (a debug log message is written
        instead). Resets to True on every repoll() call.

    subscriber_count
        Number of downstream blocks that included this handler type in the most
        recent poll response.

    frequency_filter_seconds
        Merged minimum-seconds between notification-hook fires (0.0 = no limit).
        Recomputed on every repoll() call.

    fire_count
        Incremented each time the notification hook is successfully fired.
        Resets to 0 when the handler is unregistered and re-registered
        (i.e. on repoll() or _remove_wrapper()).

    last_fired_timestamp
        time.monotonic() of the last successful notification-hook fire.
        RTC-only — not mirrored to BL.
    """
    handler_type_name:         str

    is_registered:             bool  = False
    is_enabled:                bool  = True
    subscriber_count:          int   = 0
    frequency_filter_seconds:  float = 0.0

    # RTC-only fields — not mirrored to BL
    fire_count:                int   = 0
    last_fired_timestamp:      float = 0.0

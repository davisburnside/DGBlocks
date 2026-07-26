
from ...addon_helpers.data_structures import (
    Hook_Source_Declaration,
    Logger_Declaration,
    RTC_Member_Declaration,
    RTC_Member_Data_Mirror_Declaration,
    Shared_UIList_Declaration,
    String_Comparable_Mixin,
)
from .ui import _uilist_draw_row, _uilist_draw_selection_details


# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    """
    Poll hook (downstream → this block):
        hook_get_app_handler_subscriptions()
            Each subscriber returns list[App_Handler_Subscription_Declaration].
            Called during repoll() to determine which handlers to install.

    Notification hooks (this block → downstream):
        One hook per handler type. Fired after the re-entrancy guard, is_enabled check,
        and frequency filter all pass.

    NOT available (owned by block_core structural handlers):
        load_post, undo_post, redo_post
    """

    # --- Poll ---
    hook_get_app_handler_subscriptions   = Hook_Source_Declaration({})

    # Depsgraph
    hook_app_handler_depsgraph_update_pre            = Hook_Source_Declaration({"scene": object, "depsgraph": object})
    hook_app_handler_depsgraph_update_post           = Hook_Source_Declaration({"scene": object, "depsgraph": object})

    # --- File I/O ---
    hook_app_handler_save_pre            = Hook_Source_Declaration({"scene": object})
    hook_app_handler_save_post           = Hook_Source_Declaration({"scene": object})
    hook_app_handler_load_pre            = Hook_Source_Declaration({})

    # --- Render ---
    hook_app_handler_render_init         = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_pre          = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_post         = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_write        = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_stats        = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_cancel       = Hook_Source_Declaration({"scene": object})
    hook_app_handler_render_complete     = Hook_Source_Declaration({"scene": object})

    # --- Bake ---
    hook_app_handler_object_bake_pre      = Hook_Source_Declaration({"scene": object})
    hook_app_handler_object_bake_complete = Hook_Source_Declaration({"scene": object})
    hook_app_handler_object_bake_cancel   = Hook_Source_Declaration({"scene": object})

    # --- Animation ---
    hook_app_handler_frame_change_pre    = Hook_Source_Declaration({"scene": object, "depsgraph": object})
    hook_app_handler_frame_change_post   = Hook_Source_Declaration({"scene": object, "depsgraph": object})

    # --- Annotation ---
    hook_app_handler_annotation_pre      = Hook_Source_Declaration({"scene": object})
    hook_app_handler_annotation_post     = Hook_Source_Declaration({"scene": object})

    # --- Compositing ---
    hook_app_handler_composite_pre       = Hook_Source_Declaration({"scene": object})
    hook_app_handler_composite_post      = Hook_Source_Declaration({"scene": object})
    hook_app_handler_composite_cancel    = Hook_Source_Declaration({"scene": object})

    # --- Version / XR ---
    hook_app_handler_version_update      = Hook_Source_Declaration({})
    hook_app_handler_xr_session_start_pre = Hook_Source_Declaration({})
    hook_app_handler_xr_session_end      = Hook_Source_Declaration({})


class Block_Loggers(String_Comparable_Mixin):
    APP_HANDLERS_LIFECYCLE = Logger_Declaration("INFO")
    APP_HANDLERS_EVENTS    = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    # list[RTC_App_Handler_Status_Instance] — one record per active handler type
    APP_HANDLER_STATUS_LIST          = RTC_Member_Declaration([])
    # set[str] — handler_type_names currently being executed (re-entrancy guard)
    APP_HANDLERS_CURRENTLY_EXECUTING = RTC_Member_Declaration(set())


class Block_Data_Mirrors(String_Comparable_Mixin):
    APP_HANDLER_STATUS_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key                   = "APP_HANDLER_STATUS_LIST",
        FWC_name                  = "Wrapper_App_Handlers",
        mirrored_key_field_names  = ["handler_type_name"],
        mirrored_data_field_names = ["is_registered", "is_enabled", "subscriber_count",
                                     "frequency_filter_seconds"],
        # FWC manages both sync directions manually (BL data is ephemeral display only)
        scene_colprop_path        = "dgblocks_app_handlers_props.handler_status_mirror",
    )


class Block_UIList_Configs(String_Comparable_Mixin):
    APP_HANDLER_STATUS_UILIST = Shared_UIList_Declaration(
        col_names  = ["Handler", "En.", "Reg.", "Subs", "Freq (s)", "Fires"],
        col_widths = [4, 1, 1, 1, 2, 1],
        scene_parent_path                            = "dgblocks_app_handlers_props",
        scene_colprop_path                           = "handler_status_mirror",
        scene_colprop_path_UIList_selection_idx_path = "handler_status_mirror_selected_idx",
        RTC_key                                      = Block_RTC_Members.APP_HANDLER_STATUS_LIST,
        callback_draw_row                            = _uilist_draw_row,
        callback_draw_details_section                = _uilist_draw_selection_details,
    )

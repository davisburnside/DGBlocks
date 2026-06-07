# ==============================================================================================================================
# IMPORTS
# ==============================================================================================================================

from datetime import datetime
import bpy  # type: ignore

from .....addon_helpers.ui import ui_draw_shared_debug_list

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from ...core_helpers.constants import Core_Runtime_Cache_Members
from ..runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Aliases
# --------------------------------------------------------------
cache_key_hook_subscribers = Core_Runtime_Cache_Members.REGISTRY_ALL_HOOK_SUBSCRIBERS

# ==============================================================================================================================
# UI
# ==============================================================================================================================

def _uilayout_draw_hooks_uilist_selection_detail(context, container, item, idx):
    func_name = item.hook_func_name
    cached_hook_subs = Wrapper_Runtime_Cache.get_cache(cache_key_hook_subscribers)

    if func_name not in cached_hook_subs:
        container.label(text="No subscriptions found.")
        return

    subs = cached_hook_subs[func_name]
    box = container.box()
    box.label(text=f"Subscriptions ({len(subs)}):")
    for sub in subs:
        box.label(text=f"• {sub.subscriber_block_id}", icon='PLUGIN')

def _uilayout_draw_hooks_settings(context, container):

    core_props = context.scene.dgblocks_core_props
    box = container.box()
    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_hooks_mgmt", default_closed=True)
    panel_header.label(text=f"All Hooks ({len(core_props.managed_hooks)})")
    if panel_body is not None:
        ui_draw_shared_debug_list(
            context, panel_body, "HOOKS_LIST", 
            core_props, "managed_hooks", "managed_hooks_selected_idx", 
            rows=max(1, len(core_props.managed_hooks))
        )

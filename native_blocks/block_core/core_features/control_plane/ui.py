

from .....addon_helpers.ui import v2_draw_shared_uilist
from ...core_helpers.constants import Core_Runtime_Cache_Members
from ...core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

def _uilayout_draw_blocks_uilist_selection_detail(context, container, item, idx):

    box = container.box()
    block_instance = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)[idx]
    if item.is_valid:
        box.label(text = f"Block '{block_instance.block_id}' is active and valid", icon='CHECKMARK')
    else:
        box.alert = True
        box.label(text = f"Error: {item.error_message}", icon='ERROR')
    box.label(text = f"Location: {block_instance.block_package_name}")

def _uilayout_draw_block_manager_settings(context, container):

    box = container.box()
    core_props = context.scene.dgblocks_core_props

    panel_header, panel_body = box.panel(idname="_dummy_dgblocks_core_scene_block_mgmt", default_closed=True)
    panel_header.label(text=f"All Blocks ({len(core_props.managed_blocks)})")
    if panel_body is not None:
        v2_draw_shared_uilist(
            context, panel_body, "BLOCKS_LIST", 
            core_props, "managed_blocks", "managed_blocks_selected_idx", 
            rows=max(1, len(core_props.managed_blocks))
        )

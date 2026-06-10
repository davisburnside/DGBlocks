
import sys
import bpy


# --------------------------------------------------------------
# Addon-level imports
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members # type: ignore
from ...addon_helpers.ui import ui_draw_block_panel_header, ui_draw_shared_debug_list, v2_draw_shared_uilist

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Hook_Sources, Block_Loggers, Block_RTC_Members
from .feature_shader_manager import Wrapper_Shader_Manager



# Would I ever need to read anything other than Block_RTC_Members in the ui draws?
def _uilist_draw_uilist_row(context, container, item, idx):
    pass

def _uilist_draw_selection_details(context, container, item, idx):

    box = container.box()
    print(item, idx)
    # block_instance = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS)[idx]
    # if item.is_valid:
    #     box.label(text = f"Block '{block_instance.block_id}' is active and valid", icon='CHECKMARK')
    # else:
    #     box.alert = True
    #     box.label(text = f"Error: {item.error_message}", icon='ERROR')
    # box.label(text = f"Location: {block_instance.block_package_name}")

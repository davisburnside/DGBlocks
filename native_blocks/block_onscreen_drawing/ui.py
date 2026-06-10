
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
from ...addon_helpers.ui import ui_draw_block_panel_header, v2_draw_shared_uilist, v2_draw_shared_uilist

# --------------------------------------------------------------
# Intra-block imports



# Would I ever need to read anything other than Block_RTC_Members in the ui draws?
def _uilist_draw_uilist_row(context, container, BL_item, RTC_item, list_idx):

    row = container.row()

    sub = row.row()
    sub.label(text = RTC_item.shader_uid)

    sub = row.row()
    sub.label(text = f"{RTC_item.draw_phase}/{RTC_item.draw_region}/{RTC_item.draw_space}")

def _uilist_draw_selection_details(context, container, BL_item, RTC_item, list_idx):

    box = container.box()

    box.label(text = f"{RTC_item.last_draw_attempt_timestamp}")

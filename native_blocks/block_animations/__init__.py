
import sys

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration

# --------------------------------------------------------------
# Inter-block imports — ensure dependencies are loaded first
from .. import block_core          # noqa: F401
from .. import block_onscreen_drawing  # noqa: F401
from .. import block_timers        # noqa: F401

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .feature_animation_manager import Wrapper_Animation_Manager
from .helpers import _get_timer_definitions_from_animations

# ==============================================================================================================================
# HOOK SUBSCRIBERS
# ==============================================================================================================================

def hook_get_timer_definitions():
    """
    Subscribed to block_timers' hook_get_timer_definitions.
    Returns one Timer_Definition per unique active animation framerate.
    block_timers creates (or re-creates) one bpy.app.timer per definition returned here.
    """
    return _get_timer_definitions_from_animations()

# ==============================================================================================================================
# REQUIRED
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module                 = sys.modules[__name__],
    block_id                     = "block-animations",
    block_dependencies           = ["block-core", "block-onscreen-draw", "block-timers"],
    block_bpy_classes            = [],
    block_feature_wrapper_classes= [Wrapper_Animation_Manager],
    block_loggers                = Block_Loggers,
    block_RTC_members            = Block_RTC_Members,
)

import bpy # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Enum_Sync_Events
from ...addon_helpers.generic_helpers import get_self_block_module

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.feature_block_manager import Wrapper_Block_Management

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-usecase-minimal"
_BLOCK_VERSION = (1, 0, 0)
_BLOCK_DEPENDENCIES = ["block-core"]

# ==============================================================================================================================
# REGISTRATION EVENTS
# ==============================================================================================================================

_block_classes_to_register = []

def register_block(event: Enum_Sync_Events):
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management)
    Wrapper_Block_Management.create_instance(
        event,
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
    )

def unregister_block(event: Enum_Sync_Events):
    Wrapper_Block_Management.destroy_instance(event, block_id = _BLOCK_ID)

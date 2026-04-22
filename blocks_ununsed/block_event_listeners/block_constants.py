
from enum import Enum, StrEnum, auto
import bpy

from ..blocks_natively_included._block_core.core_block_constants import Core_Block_Loggers

# Loggers user by this block
class Block_Logger_Definitions(Enum):
    LISTENERS = Core_Block_Loggers("EVENT-LISTEN", "WARNING")

# class Enum_Hooked_Block_Cache_Member(StrEnum):
#     HOOKED_BLOCK_MODULE = auto()
#     HOOKED_BLOCK_NAME = auto()
#     TIMESTAMP_PREVIOUS_HOOK_EXECUTE = auto()

# # The names of required global data cache members
class Enum_Runtime_Cache_Keys(StrEnum):
    EVENT_LISTENER_WRAPPER_CACHE = auto()
    EVENT_LISTENER_HOOKED_BLOCKS_FOR_ALL_WRAPPERS = auto()

class Enum_Event_Listener_Definitions(Enum):
    """
    Supported handler types.
    Value format: (handler_attr, property_name, hook_suffix)
    """
    DEPSGRAPH_PRE = ("depsgraph_update_pre", "enable_listener_depsgraph_pre", "depsgraph_pre")
    DEPSGRAPH_POST = ("depsgraph_update_post", "enable_listener_depsgraph_post", "depsgraph_post")
    FRAME_CHANGE_PRE = ("frame_change_pre", "enable_listener_frame_change_pre", "frame_change_pre")
    FRAME_CHANGE_POST = ("frame_change_post", "enable_listener_frame_change_post", "frame_change_post")
    UNDO_PRE = ("undo_pre", "enable_listener_undo_pre", "undo_pre")
    UNDO_POST = ("undo_post", "enable_listener_undo_post", "undo_post")
    REDO_PRE = ("redo_pre", "enable_listener_redo_pre", "redo_pre")
    REDO_POST = ("redo_post", "enable_listener_redo_post", "redo_post")
    SAVE_PRE = ("save_pre", "enable_listener_save_pre", "save_pre")
    SAVE_POST = ("save_post", "enable_listener_save_post", "save_post")
    OBJECT_BAKE_PRE = ("object_bake_pre", "enable_listener_bake_pre", "bake_pre")
    OBJECT_BAKE_POST = ("object_bake_post", "enable_listener_bake_post", "bake_post")
    COMPOSITE_PRE = ("composite_pre", "enable_listener_composite_pre", "composite_pre")
    COMPOSITE_POST = ("composite_post", "enable_listener_composite_post", "composite_post")
    
    @property
    def handler_attr(self) -> str:
        return self.value[0]
    
    @property
    def property_name(self) -> str:
        return self.value[1]
    
    @property
    def hook_suffix(self) -> str:
        """Suffix for callback_hook_listener_{suffix} function names."""
        return self.value[2]
    
    @property
    def bpy_app_handlers_collection_of_listener(self) -> list:
        return getattr(bpy.app.handlers, self.handler_attr)
    
    @classmethod
    def all_names(cls) -> list[str]:
        return [ht.handler_attr for ht in cls]

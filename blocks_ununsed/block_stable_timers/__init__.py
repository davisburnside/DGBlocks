
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header
import bpy # type: ignore
from bpy.props import StringProperty, IntProperty, BoolProperty, CollectionProperty, PointerProperty # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import should_draw_delevoper_panel
from ...my_addon_config import (
        addon_title,
        addon_bl_type_prefix, 
        default_disabled_icon,
        Documentation_URLs)

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...blocks_natively_included import _block_core
from ...blocks_natively_included._block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import create_ui_box_with_header
from ...blocks_natively_included._block_core.core_features.feature_logs import get_logger
from ...blocks_natively_included._block_core.core_helpers.constants import ( Core_Block_Loggers, Core_Block_Hook_Sources)

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .helper_functions import op_timer_add, op_timer_remove, uilayout_draw_timer_list_item, uilayout_draw_timer_panel
from .feature_timer_wrapper import Timer_Wrapper, _rtc_get_all
from .block_constants import (
        Block_Logger_Definitions,
        Block_Runtime_Cache_Members,
        Block_Hooks)

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-stable-timers"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    _block_core._BLOCK_ID,
]

# ==============================================================================================================================
# CALLBACK HOOK FUNCTIONS 
# ==============================================================================================================================

def hook_post_register_init(context):
    """Called after register_block() finishes & bpy.context is fully usable"""
    
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    logger.debug("Starting post_register_init for block-timer")
    
    # Sync scene data with RTC on startup
    Timer_Wrapper.init_post_bpy(context.scene)
    
    logger.info("Finished post_register_init for block-timer")
    return True

# =============================================================================
# DATABLOCKS - Attached to Scene
# Stores persistent timer definitions
# =============================================================================

def callback_prop_update(self, context):
    Timer_Wrapper.sync_scene_to_rtc(context.scene)

class DGBLOCKS_PG_Timer_Item(bpy.types.PropertyGroup):
    """Individual timer definition stored in scene"""
    
    timer_name: StringProperty(
        name="Timer Name",
        default="New Timer",
        update = callback_prop_update
    ) # type: ignore
    
    # timer_desc: StringProperty(
    #     name="Timer desc",
    #     default="just for an expirement",
    #     update = callback_prop_update
    # ) # type: ignore
    
    frequency_ms: IntProperty(
        name="Frequency (ms)",
        default=1000,
        min=1,
        description="How often the timer fires in milliseconds",
        update=lambda self, context: Timer_Wrapper.sync_scene_to_rtc(context.scene)
    ) # type: ignore
    
    is_enabled: BoolProperty(
        name="Enabled",
        default=True,
        description="Whether this timer is active",
        update = callback_prop_update
    ) # type: ignore

class DGBLOCKS_PG_Timer_Props(bpy.types.PropertyGroup):
    """Collection of all timers for the scene"""
    
    timers: CollectionProperty(type=DGBLOCKS_PG_Timer_Item) # type: ignore
    uilist_selection_index_active_timer: IntProperty(default=0) # type: ignore

#================================================================
# OPERATORS
#================================================================

class DGBLOCKS_OT_Timer_Add(bpy.types.Operator):
    """Add a new timer to the list"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.timer_add"
    bl_label = "Add Timer"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return op_timer_add(context)

class DGBLOCKS_OT_Timer_Remove(bpy.types.Operator):
    """Remove the selected timer from the list"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.timer_remove"
    bl_label = "Remove Timer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        timer_props = context.scene.dgblocks_timer_props
        return len(timer_props.timers) > 0
    
    def execute(self, context):
        return op_timer_remove(context)

#================================================================
# UI - UIList for displaying timers
#================================================================

class DGBLOCKS_UL_Timer_List(bpy.types.UIList):
    """UIList for displaying timer items"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        uilayout_draw_timer_list_item(self.layout_type, context, layout, data, item, icon, active_data, active_propname, index)

#================================================================
# UI - Panel for Timer Management
#================================================================

class DGBLOCKS_PT_Timer_Panel(bpy.types.Panel):
    """Panel for managing timers in the N-menu"""
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Timer_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return should_draw_delevoper_panel(context)
    
    def draw_header(self, context):
        all_timer_instances = _rtc_get_all()
        enabled_count = len([t for t in all_timer_instances.values() if t.is_enabled])
        total_count = len(all_timer_instances)
        label = f"{_BLOCK_ID.upper()} ( {enabled_count}/{total_count} )"
        ui_draw_block_panel_header(context, self.layout,label, Documentation_URLs.MY_PLACEHOLDER_URL_1, icon_name = "TIME")
    
    def draw(self, context):
        uilayout_draw_timer_panel(context, self.layout)

#================================================================
# REGISTRATION EVENTS - Should only be called from the addon's main __init__.py
#================================================================

_block_classes_to_register = [
    DGBLOCKS_PG_Timer_Item,
    DGBLOCKS_PG_Timer_Props,
    DGBLOCKS_OT_Timer_Add,
    DGBLOCKS_OT_Timer_Remove,
    DGBLOCKS_UL_Timer_List,
    DGBLOCKS_PT_Timer_Panel
]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(
        block_id=_BLOCK_ID,
        block_classes=_block_classes_to_register,
        block_runtime_cache_members=Block_Runtime_Cache_Members,
        block_hooks=Block_Hooks,
        block_loggers=Block_Logger_Definitions
    )
    
    # Create Scene Property to hold timer definitions
    bpy.types.Scene.dgblocks_timer_props = PointerProperty(type=DGBLOCKS_PG_Timer_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    # Stop all timers before unregistering
    Timer_Wrapper.destroy_wrapper()
    
    unregister_block_components(
        block_id=_BLOCK_ID,
        block_classes=_block_classes_to_register,
        block_runtime_cache_members=Block_Runtime_Cache_Members,
        block_hooks=Block_Hooks,
        block_loggers=Block_Logger_Definitions
    )
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_timer_props"):
        del bpy.types.Scene.dgblocks_timer_props
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")

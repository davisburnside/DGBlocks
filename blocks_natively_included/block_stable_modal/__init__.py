
import time
import bpy # type: ignore
from bpy.props import BoolProperty, PointerProperty # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helper_funcs import should_draw_delevoper_panel, get_self_block_module
from ...my_addon_config import Documentation_URLs, should_show_developer_ui_panels, default_disabled_icon, addon_name, addon_title, addon_bl_type_prefix

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import _block_core
from .._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from .._block_core.core_features.feature_hooks import Wrapper_Hooks
from .._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from .._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from .._block_core.core_helpers.helper_uilayouts import uilayout_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .helper_functions import uilayout_draw_modal_panel, op_modal_toggle, op_modal_restart
from .test1 import BL_Modal_Instance, MODAL_OT_Delete, MODAL_UL_StackList, VIEW3D_PT_ModalStack, MODAL_OT_Add, Wrapper_Modals_Manager
from .block_constants import (
        Block_Logger_Definitions,
        Block_RTC_Members,
        Block_Hooks)

#=================================================================================
# BLOCK DEFINITION
#=================================================================================

_BLOCK_ID = "block-stable-modal"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core"
]


#=================================================================================
# CALLBACK HOOK FUNCTIONS 
#=================================================================================

def hook_post_register_init(context):
    """Called after register_block() finishes & bpy.context is fully usable"""
    
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    logger.debug("Starting post_register_init for block-stable-modal")
    
    # # Sync scene data with RTC on startup
    # Modal_Wrapper.init_post_bpy()
    
    # # Auto-start modal if configured
    # modal_props = context.scene.dgblocks_modal_props
    # modal_instance = Modal_Wrapper.get_instance()
    
    # if modal_instance and modal_props.should_be_activated_after_startup:
    #     if not modal_instance.is_running:
    #         logger.info("Auto-starting modal on post-register init")
    #         Modal_Wrapper.start_modal(context)
    
    logger.info("Finished post_register_init for block-stable-modal")
    return True

# =============================================================================
# DATABLOCKS - Attached to Scene
# Stores persistent modal configuration
# =============================================================================

class DGBLOCKS_PG_Modal_Props(bpy.types.PropertyGroup):
    """Modal configuration stored in scene"""
    
    managed_modals: bpy.props.CollectionProperty(type=BL_Modal_Instance) # type: ignore
    managed_modals_selected_idx: bpy.props.IntProperty()  # type: ignore

#================================================================
# OPERATORS
#================================================================

class DGBLOCKS_OT_StableModal(bpy.types.Operator):
    """Stable modal operator that intercepts timer/mouse/keyboard events before passing them to downstream hooks"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.stable_modal_base"
    bl_label = ""
    bl_options = {'INTERNAL'}

    uid: bpy.props.StringProperty() # type: ignore
    
    def invoke(self, context, event):
        """Start the modal operator"""
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)
        
        # Get modal instance data
        modal_instance = Modal_Wrapper.get_instance(self.uid)
        if modal_instance is None:
            logger.error("Cannot start modal: instance data not found")
            return {'CANCELLED'}
        
        if modal_instance.is_running:
            logger.warning("Modal already running")
            return {'CANCELLED'}
        
        # Mark as running and store operator instance
        modal_instance._operator_ref = self
        
        # Register modal handler
        context.window_manager.modal_handler_add(self)
        logger.info("Modal operator started")
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        """Handle events and route to hooks"""

        try:
            uid = self.uid
            logger = get_logger(Block_Logger_Definitions.MODAL_EVENTS)
            logger.debug(f"modal {uid} : event {event.type}")
            
            # Get modal instance data
            _, modal_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
                member_key = Block_RTC_Members.MODALS_CACHE, 
                uniqueness_field = "uid", 
                uniqueness_field_value = uid,
            )

            if modal_instance is None:
                logger.warning(f"No modal operator instance with uid '{uid}'")
                return {"CANCELLED"}
            
            if modal_instance.should_die:
                logger.warning(f"Modal operator '{uid}' flagged for removal, cancelling now")
                return {"CANCELLED"}
       
            # Update timestamp
            modal_instance.timestamp_ms_last_event = int(time.time() * 1000)
            
            # Route mouse & keyboard events
            if event.type != "TIMER":
                logger.debug(f"mous/key event: {event.type}")
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name = Block_Hooks.KEY_OR_MOUSE_EVENT,
                    should_halt_on_exception=False,
                    context = context,
                    event = event,
                    modal_instance = modal_instance,
                )

            # Route mouse events
            if event.type == "TIMER:":
                logger.debug(f"timer event: {event.type}")
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name = Block_Hooks.TIMER_EVENT,
                    should_halt_on_exception=False,
                    context = context,
                    event = event,
                    modal_instance = modal_instance,
                )
                
            # Detect area changes
            current_area = context.area
            if current_area != modal_instance.last_area and modal_instance.last_area is not None:
                logger.debug(f"Area change detected")
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name=Block_Hooks.AREA_CHANGE_EVENT,
                    should_halt_on_exception=False,
                    context=context,
                    event=event,
                    modal_instance = modal_instance,
                    old_area=modal_instance.last_area,
                    new_area=current_area
                )
                
            # update mouse area
            modal_instance.last_area = current_area
            
        except Exception as e:
            logger.error(f"Exception in modal operator '{self.uid}'", exc_info=True)
        
        return {"PASS-THROUGH"}

class DGBLOCKS_OT_Modal_Toggle(bpy.types.Operator):
    """Toggle the modal on/off"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.modal_toggle"
    bl_label = "Toggle Modal"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return op_modal_toggle(context)

class DGBLOCKS_OT_Modal_Restart(bpy.types.Operator):
    """Force restart the modal"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.modal_restart"
    bl_label = "Restart Modal"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return op_modal_restart(context)

#================================================================
# REGISTRATION EVENTS - Should only be called from the addon's main __init__.py
#================================================================

_block_classes_to_register = [
    BL_Modal_Instance,
    DGBLOCKS_PG_Modal_Props,
    DGBLOCKS_OT_StableModal,
    DGBLOCKS_OT_Modal_Toggle,
    DGBLOCKS_OT_Modal_Restart,
    MODAL_OT_Delete,
    MODAL_OT_Add,
    MODAL_UL_StackList,
    VIEW3D_PT_ModalStack,
]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = _block_classes_to_register,
        block_feature_wrapper_classes = [Wrapper_Modals_Manager], 
        block_hook_source_enums = Block_Hooks,
        block_RTC_member_enums = Block_RTC_Members, 
        block_logger_enums = Block_Logger_Definitions 
    )

    # Create Scene Property to hold modal configuration
    bpy.types.Scene.dgblocks_modal_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Modal_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")
    
    
    # Remove block components from RTC
    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_modal_props"):
        del bpy.types.Scene.dgblocks_modal_props

    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")

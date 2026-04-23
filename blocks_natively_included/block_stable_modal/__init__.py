
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
from .test1 import BL_Modal_Instance,MODAL_OT_Delete, MODAL_UL_StackList, VIEW3D_PT_ModalStack, MODAL_OT_Add
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
    # modal_data = Modal_Wrapper.get_instance()
    
    # if modal_data and modal_props.should_be_activated_after_startup:
    #     if not modal_data.is_running:
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
    
    managed_blocks: bpy.props.CollectionProperty(type=BL_Modal_Instance) # type: ignore
    managed_blocks_selected_idx: bpy.props.IntProperty()  # type: ignore

#================================================================
# OPERATORS
#================================================================

class DGBLOCKS_OT_StableModal(bpy.types.Operator):
    """Stable modal operator that routes keyboard and mouse events to hooks"""
    bl_idname = f"{addon_bl_type_prefix.lower()}.stable_modal"
    bl_label = "Stable Modal"
    bl_options = {'INTERNAL'}
    
    def invoke(self, context, event):
        """Start the modal operator"""
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)
        
        # Get modal instance data
        modal_data = Modal_Wrapper.get_instance()
        if modal_data is None:
            logger.error("Cannot start modal: instance data not found")
            return {'CANCELLED'}
        
        if modal_data.is_running:
            logger.warning("Modal already running")
            return {'CANCELLED'}
        
        # Mark as running and store operator instance
        modal_data.is_running = True
        modal_data._operator_ref = self
        
        # Register modal handler
        context.window_manager.modal_handler_add(self)
        logger.info("Modal operator started")
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        """Handle events and route to hooks"""
        logger = get_logger(Block_Logger_Definitions.MODAL_EVENTS)
        
        # Get modal instance data
        modal_data = Modal_Wrapper.get_instance()
        if modal_data is None:
            logger.error("Modal data lost during execution")
            return {'CANCELLED'}
        
        # Check if should stop
        if not modal_data.is_enabled or not modal_data.is_running:
            logger.info("Modal stopping (disabled or flagged)")
            modal_data.is_running = False
            modal_data._operator_ref = None
            return {'CANCELLED'}
        
        # Update timestamp
        modal_data.timestamp_ms_last_event = int(time.time() * 1000)
        
        # Default return value
        final_return = {'PASS_THROUGH'}
        
        try:
            # Route keyboard events
            if event.type not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 
                                  'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                                  'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                logger.debug(f"Key event: {event.type}")
                results = Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name=Block_Hooks.KEY_EVENT,
                    should_halt_on_exception=False,
                    context=context,
                    event=event
                )
                
                # Aggregate return values (first non-PASS_THROUGH wins)
                final_return = self._aggregate_hook_returns(results, final_return)
            
            # Route mouse events
            if event.type in {'MOUSEMOVE', 'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                              'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                logger.debug(f"Mouse event: {event.type}")
                results = Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name=Block_Hooks.MOUSE_EVENT,
                    should_halt_on_exception=False,
                    context=context,
                    event=event
                )
                
                # Aggregate return values
                final_return = self._aggregate_hook_returns(results, final_return)
            
            # Detect area changes
            current_area = context.area
            if current_area != modal_data.last_area and modal_data.last_area is not None:
                logger.debug(f"Area change detected")
                results = Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name=Block_Hooks.AREA_CHANGE_EVENT,
                    should_halt_on_exception=False,
                    context=context,
                    event=event,
                    old_area=modal_data.last_area,
                    new_area=current_area
                )
                
                # Aggregate return values
                final_return = self._aggregate_hook_returns(results, final_return)
            
            modal_data.last_area = current_area
            
        except Exception as e:
            logger.error("Exception in modal event handling", exc_info=True)
            
            # Handle auto-restart
            modal_props = context.scene.dgblocks_modal_props
            if modal_props.should_restart_on_error:
                logger.warning("Scheduling modal restart due to error")
                modal_data.count_restarts += 1
                modal_data.is_running = False
                modal_data._operator_ref = None
                
                # Schedule restart
                def restart_modal():
                    if modal_props.is_enabled:
                        Modal_Wrapper.start_modal(context)
                    return None
                
                bpy.app.timers.register(restart_modal, first_interval=0.1)
                return {'CANCELLED'}
        
        return final_return
    
    def _aggregate_hook_returns(self, results: dict, default_return: set) -> set:
        """
        Aggregate return values from multiple hooks.
        Default to PASS_THROUGH, but use first valid operator return if any hook returns one.
        
        Valid operator returns: FINISHED, CANCELLED, RUNNING_MODAL, PASS_THROUGH
        """
        valid_returns = [
            {'FINISHED'}, {'CANCELLED'}, {'RUNNING_MODAL'}, 
            {'PASS_THROUGH'}, {'INTERFACE'}
        ]
        
        for block_id, return_value in results.items():
            if return_value in valid_returns and return_value != {'PASS_THROUGH'}:
                return return_value
        
        return default_return

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
# UI - Panel for Modal Management
#================================================================

# class DGBLOCKS_PT_Modal_Panel(bpy.types.Panel):
#     """Panel for managing the stable modal in the N-menu"""
#     bl_label = ""
#     bl_idname = f"{addon_bl_type_prefix}_PT_Modal_Panel"
#     bl_space_type = 'VIEW_3D'
#     bl_region_type = 'UI'
#     bl_category = addon_title
#     bl_options = {'DEFAULT_CLOSED'}
    
#     @classmethod
#     def poll(cls, context):
#         return should_draw_delevoper_panel(context)
    
#     def draw_header(self, context):
#         modal_data = Modal_Wrapper.get_instance()
#         is_enabled = (modal_data and modal_data.is_running)
#         status_str = "( On )" if is_enabled else "( Off )"
#         label = f"{_BLOCK_ID.upper()} {status_str}"
#         uilayout_draw_block_panel_header(
#             context, 
#             self.layout, 
#             label, 
#             Documentation_URLs.MY_PLACEHOLDER_URL_1, 
#             icon_name = "MOUSE_LMB_DRAG"
#         )
    
#     def draw(self, context):
#         uilayout_draw_modal_panel(context, self.layout)
        
#         # Add quick action buttons
#         box = self.layout.box()
#         box.label(text="Quick Actions")
#         row = box.row(align=True)
#         row.operator("dgblocks.modal_toggle", text="Toggle", icon='PLAY')
#         row.operator("dgblocks.modal_restart", text="Restart", icon='FILE_REFRESH')

#================================================================
# REGISTRATION EVENTS - Should only be called from the addon's main __init__.py
#================================================================

_block_classes_to_register = [
    DGBLOCKS_PG_Modal_Props,
    DGBLOCKS_OT_StableModal,
    DGBLOCKS_OT_Modal_Toggle,
    DGBLOCKS_OT_Modal_Restart,
    BL_Modal_Instance,
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
        # block_feature_wrapper_classes = [Modal_Wrapper], 
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
    
    # Stop modal before unregistering
    # Modal_Wrapper.destroy_wrapper()
    
    # Remove block components from RTC
    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_modal_props"):
        del bpy.types.Scene.dgblocks_modal_props

    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")

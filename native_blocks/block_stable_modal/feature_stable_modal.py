from __future__ import annotations
import time
import bpy
from dataclasses import dataclass, field
from typing import Callable, Optional

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Abstract_Feature_Wrapper, Abstract_BL_RTC_List_Syncronizer, Abstract_Datawrapper_Instance_Manager

from ...addon_helpers.generic_helpers import should_draw_delevoper_panel, get_self_block_module
from ...my_addon_config import addon_name, addon_title

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import block_core
from ..block_core.core_helpers.helper_datasync import update_collectionprop_to_match_dataclasses, update_dataclasses_to_match_collectionprop
from ..block_core.core_features.loggers import Core_Block_Loggers, get_logger
from ..block_core.core_features.hooks import Wrapper_Hooks
from ..block_core.core_features.control_plane import Wrapper_Block_Management
from ..block_core.core_features.runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .block_constants import Block_RTC_Members, Block_Logger_Definitions, Block_Hooks









cache_key_blocks = Block_RTC_Members.MODALS_CACHE

# ==============================================================================================================================
# MIRRORED DATA STRUCTURES OF FEATURE
# ==============================================================================================================================

@dataclass
class RTC_Modal_Instance:

    # Mirrored fields of DGBLOCKS_PG_Hook_Reference
    uid:str

    # Not present in mirror
    label: str
    includes_timer: bool
    timer_interval: Optional[float]
    created_timestamp: int = -1
    last_event_timestamp: int = -1 # updates on timer or key/mouse events
    should_die: bool = False

class BL_Modal_Instance(bpy.types.PropertyGroup):

    # Mirrored fields of RTC_Modal_Instance
    uid: bpy.props.StringProperty() # type: ignore

# ==============================================================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
# ==============================================================================================================================

class Wrapper_Modals_Manager(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager, Abstract_BL_RTC_List_Syncronizer):
    # Manager — classmethods only, no instance state

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        #no-op
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        # no-op
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        # no-op
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------
    @classmethod
    def create_instance(
        cls,
        uid: str,
        label: str = "",
        includes_timer: bool = False,
        timer_interval: Optional[float] = None,
    ) -> RTC_Modal_Instance:

        modal_instance = RTC_Modal_Instance(
            uid = uid,
            label = label,
            includes_timer = includes_timer,
            timer_interval= timer_interval,
        )
        Wrapper_Runtime_Cache.add_unique_instance_to_registry_list(Block_RTC_Members.MODALS_CACHE, "uid", modal_instance)

        add_modal_op_to_blender_stack(modal_instance)

        cls.update_BL_with_mirrored_RTC_data()

        return modal_instance

    @classmethod
    def destroy_instance(cls, uid: str) -> None:
        # Unlike most destroy_instance functions, this one only flags a record for deletion

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Removing modal '{uid}'")
        
        all_rtc_modals = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MODALS_CACHE)
        modal_instance = next((m for m in all_rtc_modals if m.uid == uid), None)
        if modal_instance:
            modal_instance.should_die = True
            Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MODALS_CACHE, all_rtc_modals)
        else:
            logger.debug(f"Modal '{uid}' not present in RTC")
            return

    @classmethod
    def get_instance(cls):
        pass
    
    @classmethod
    def set_instance(cls, data):
        pass

    # --------------------------------------------------------------
    # Implemented from Abstract_BL_RTC_List_Syncronizer
    # --------------------------------------------------------------

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls):

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating modals cache with mirrored Blender data")
        
        rtc_all_modals = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MODALS_CACHE)
        scene_modals_collection = bpy.context.scene.dgblocks_modal_props.managed_modals

        intended_modal_uids = set([m.uid for m in scene_modals_collection])
        actual_modal_uids = set([m.uid for m in rtc_all_modals])

        if intended_modal_uids != actual_modal_uids:
            raise Exception("modal's dont match")
        
        update_dataclasses_to_match_collectionprop(
            actual_FWC = RTC_Modal_Instance,
            source = rtc_all_modals,
            target = scene_modals_collection,
            key_fields = ["uid"],
            data_fields = []
        )

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls):

        logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)
        logger.debug(f"Updating Blender data with mirrored modals cache")

        rtc_all_modals = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MODALS_CACHE)
        scene_modals_collection = bpy.context.scene.dgblocks_modal_props.managed_modals
        
        rtc_all_modals = update_collectionprop_to_match_dataclasses(
            source = rtc_all_modals,
            target = scene_modals_collection,
            key_fields = ["uid"],
            data_fields = []
        )
        
        # per_Runtime_Cache.get_cache(Block_RTC_Members.MODALS_CACHE)
        # scene_modals_collection = bpy.context.scene.dgblocks_modal_props.managed_modals

# ==============================================================================================================================
# BASE MODAL OPERATOR - Can be instanced many times
# ==============================================================================================================================

class DGBLOCKS_OT_StableModal(bpy.types.Operator):
    """Stable modal operator that intercepts timer/mouse/keyboard events before passing them to subscriber hooks"""
    bl_idname = "dgblocks.stable_modal_base"
    bl_label = ""
    bl_options = {'INTERNAL'}

    # ID of the modal, matches keys found in BL_Modal_Instances & RTC_Modal_Instances
    uid: bpy.props.StringProperty(default="") # type: ignore

    # Optional viewport area targeting — empty means "pick one automatically"
    target_area_key: bpy.props.StringProperty(default="") # type: ignore
    
    def invoke(self, context, event):
        """
        Start the modal operator. 
        This should only be called with 'bpy.ops.dgblocks.stable_modal_base', and never directly from the UI
        This operator is started immediately after 'Wrapper_Modals_Manager.create_instance' stores a new RTC_Modal_Instance in the RTC
        """
        logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)
        
        # Get modal instance data
        _, modal_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = Block_RTC_Members.MODALS_CACHE, 
            uniqueness_field = "uid", 
            uniqueness_field_value = self.uid,
        )
        if modal_instance is None:
            all_rtc_modal_uids = [m.uid for m in Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MODALS_CACHE)]
            all_rtc_modal_uids_str = "'" + ",".join(all_rtc_modal_uids) + "'"
            logger.error(f"Modal '{self.uid}' not found in modals cache {all_rtc_modal_uids_str}")
            return {'CANCELLED'}

        # Store operator instance inside RTC instance. Without this, a reference to this operator instance is lost
        modal_instance._op_ref = self

        # Resolve the area: use requested one if valid, else find a new one
        # area = _resolve_area(context, self.target_area_key)
        # if area is None:
        #     self.report({'WARNING'}, "No suitable 3D viewport found")
        #     return {'CANCELLED'}
        
        # # Store the key, not the area reference
        # self.target_area_key = self._make_area_key(context.window, area)
        
        # Register modal handler
        context.window_manager.modal_handler_add(self)
        logger.info("Modal operator started")
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        """Handle events and route to hooks"""

        try:
            uid = self.uid
            logger = get_logger(Block_Logger_Definitions.MODAL_EVENTS)
            logger.debug(f"modal {uid} : event {event.type} : {event.value}")

            # Get modal instance data
            _, modal_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
                member_key = Block_RTC_Members.MODALS_CACHE, 
                uniqueness_field = "uid", 
                uniqueness_field_value = uid,
            )

            if modal_instance is None:
                logger = get_logger(Block_Logger_Definitions.MODAL_LIFECYCLE)
                logger.warning(f"No modal operator instance with uid '{uid}', removing from RTC")
                return {"FINISHED"}
            
            if modal_instance.should_die:
                logger.info(f"Modal operator '{uid}' flagged for removal, removing from RTC")
                Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
                    member_key = Block_RTC_Members.MODALS_CACHE, 
                    uniqueness_field = "uid", 
                    uniqueness_field_value = uid,
                )
                return {"FINISHED"}
       
            # Update timestamp
            modal_instance.timestamp_ms_last_event = int(time.time() * 1000)
            
            # Route mouse & keyboard events
            if event.type != "TIMER":
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name = Block_Hooks.KEY_OR_MOUSE_EVENT,
                    should_halt_on_exception=False,
                    context = context,
                    event = event,
                    modal_instance = modal_instance,
                )

            # Route mouse events
            if event.type == "TIMER:":
                Wrapper_Hooks.run_hooked_funcs(
                    hook_func_name = Block_Hooks.TIMER_EVENT,
                    should_halt_on_exception=False,
                    context = context,
                    event = event,
                    modal_instance = modal_instance,
                )
                
            # Detect area changes
            # current_area = context.area
            # if current_area != modal_instance.last_area and modal_instance.last_area is not None:
            #     logger.debug(f"Area change detected")
            #     Wrapper_Hooks.run_hooked_funcs(
            #         hook_func_name=Block_Hooks.AREA_CHANGE_EVENT,
            #         should_halt_on_exception=False,
            #         context=context,
            #         event=event,
            #         modal_instance = modal_instance,
            #         old_area=modal_instance.last_area,
            #         new_area=current_area
            #     )
                
            # # update mouse area
            # modal_instance.last_area = current_area
            
        except Exception as e:
            logger.error(f"Exception in modal operator '{self.uid}'", exc_info=True)
        
        return {"PASS_THROUGH"}

# ==============================================================================================================================
# OPERATORS AND UI FOR FEATURE INTERACTION
# ==============================================================================================================================

class MODAL_OT_Add(bpy.types.Operator):
    """Add a new modal to the stack with default parameters."""
    bl_idname = "modal_stack.add"
    bl_label  = "Add Modal"

    uid: bpy.props.StringProperty(name="UID", default="") # type: ignore
    label: bpy.props.StringProperty(name="Label",     default="New Modal") # type: ignore
    timer_interval: bpy.props.FloatProperty(min=0.0) # type: ignore
    includes_timer: bpy.props.BoolProperty() # type: ignore

    def invoke(self, context, event):

        # Auto-generate a uid if not provided
        if not self.uid:
            import uuid
            self.uid = "modal_" + uuid.uuid4().hex[:6]
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "uid")
        layout.prop(self, "label")
        layout.prop(self, "timer_interval")
        layout.prop(self, "includes_timer")

    def execute(self, context):
        interval = self.timer_interval if self.timer_interval > 0.0 else None
        try:
            Wrapper_Modals_Manager.create_instance(
                uid = self.uid,
                label = self.label,
                timer_interval = interval,
                includes_timer = self.includes_timer,
            )
        except (KeyError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

class MODAL_OT_Delete(bpy.types.Operator):
    bl_idname = "modal_stack.delete"
    bl_label  = "Delete Modal"

    uid: bpy.props.StringProperty()# type: ignore

    def execute(self, context):
        Wrapper_Modals_Manager.destroy_instance(self.uid)
        return {'FINISHED'}

class MODAL_UL_StackList(bpy.types.UIList):
    bl_idname = "MODAL_UL_stack_list"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):

        row = layout.row(align=True)
        row.label(text=item.uid)
        row.separator_spacer()
        
        kill = row.operator("modal_stack.delete", text="", icon='X')
        kill.uid = item.uid

class VIEW3D_PT_ModalStack(bpy.types.Panel):
    bl_label       = "Modal Stack"
    bl_idname      = "VIEW3D_PT_modal_stack"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = addon_title

    def draw(self, context):
        layout = self.layout
        # _sync_ui_list(context)
        layout.template_list(
            "MODAL_UL_stack_list", "",
            context.scene.dgblocks_modal_props, "managed_modals",
            context.scene.dgblocks_modal_props, "managed_modals_selected_idx",
            rows=max(2, len(context.scene.dgblocks_modal_props.managed_modals))
        )
        layout.operator("modal_stack.add", icon='ADD') 

# ==============================================================================================================================
# PRIVATE MODULE API — should not be used outside this file
# ==============================================================================================================================

def print_current_modals():
    for op in bpy.context.window_manager.operators:
        print("==========\n", op.bl_idname)      # e.g. 'TRANSFORM_OT_translate'
        print(op.name)           # human label
        print(op.properties)     # operator property values at time of execution

def add_modal_op_to_blender_stack(modal_instance):

    bpy.ops.dgblocks.stable_modal_base("INVOKE_DEFAULT", uid = modal_instance.uid)



def _make_area_key(window, area):
    """Build a stable-ish key identifying this area within this window."""
    win_idx = list(bpy.context.window_manager.windows).index(window)
    # x,y of the area within the screen is stable until user drags splits
    return f"{win_idx}:{area.x},{area.y}:{area.type}"

def _resolve_area(context, area_key):
    """Try to find the area matching area_key; fall back to any VIEW_3D."""
    wm = context.window_manager
    
    # First try to match the stored key
    if area_key:
        try:
            win_idx_str, coords, area_type = area_key.split(":")
            win_idx = int(win_idx_str)
            x_str, y_str = coords.split(",")
            x, y = int(x_str), int(y_str)
            
            if 0 <= win_idx < len(wm.windows):
                window = wm.windows[win_idx]
                for area in window.screen.areas:
                    if (area.type == area_type 
                        and area.x == x 
                        and area.y == y):
                        return area
        except (ValueError, IndexError):
            pass  # malformed or stale key
    
    # Fallback: first VIEW_3D in any window
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return area
    return None

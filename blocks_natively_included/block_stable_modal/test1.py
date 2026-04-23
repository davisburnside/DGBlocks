from __future__ import annotations
import bpy
from dataclasses import dataclass, field
from typing import Callable, Optional

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_data_structures import Abstract_Feature_Wrapper, Abstract_BL_and_RTC_Data_Syncronizer, Abstract_Datawrapper_Instance_Manager
from ...addon_helper_funcs import should_draw_delevoper_panel, get_self_block_module
from ...my_addon_config import addon_name, addon_title

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
from .block_constants import Block_RTC_Members

# ---------------------------------------------------------------------------
# MIRRORED DATA STRUCTURES OF FEATURE
# ---------------------------------------------------------------------------

@dataclass
class RTC_Modal_Instance:

    # Mirrored fields of DGBLOCKS_PG_Hook_Reference
    uid:str
    label: str
    includes_timer: bool
    timer_interval: Optional[float]

    # Not present in mirror
    created_timestamp: int
    last_event_timestamp: int # updates on timer or key/mouse events
    should_die: bool
    _op_ref: Optional[object]

    def __post_init__(self):
        if self.includes_timer and self.timer_interval <= 0:
            raise ValueError(f"Modal {self.uid} has invalid/0 timer interval")

class BL_Modal_Instance(bpy.types.PropertyGroup):

    # Mirrored fields of RTC_Modal_Instance
    uid: bpy.props.StringProperty() # type: ignore
    label: bpy.props.StringProperty() # type: ignore
    includes_timer: bpy.props.BoolProperty() # type: ignore
    timer_interval: bpy.props.FloatProperty() # type: ignore

#=================================================================================
# MODULE MAIN FEATURE WRAPPER CLASS
#=================================================================================

class Wrapper_Modals_Manager(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
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

        return modal_instance

    @classmethod
    def destroy_instance(cls, uid: str) -> None:
        
        # Get instance to remove
        _, modal_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = Block_RTC_Members.MODALS_CACHE, 
            uniqueness_field = "uid", 
            uniqueness_field_value = uid,
        )

        # Flag the modal associated with the instance to be stopped. Modal Finish/Cancel can only occur during a modal event, and not from this function
        if modal_instance._op_ref is None:
            raise Exception(f"Modal {uid} has no associated ")
        else:
            modal_instance._op_ref._exit_requested = True
            
        # Remove from registry
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key = Block_RTC_Members.MODALS_CACHE, 
            uniqueness_field = "uid", 
            uniqueness_field_value = uid,
        )

# ---------------------------------------------------------------------------
# OPERATORS AND UI FOR FEATURE INTERACTION
# ---------------------------------------------------------------------------

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
        layout.prop(self, "autostart")

    def execute(self, context):
        interval = self.timer_interval if self.timer_interval > 0.0 else None
        try:
            Wrapper_Modals_Manager.create_instance(
                uid = self.uid,
                bl_idname = self.bl_idname_prop,
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
        row.label(text="", icon='HIDE_OFF' if item.running else 'HIDE_ON')
        row.label(text=item.label)
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
            context.scene.dgblocks_modal_props, "modal_stack_items",
            context.scene.dgblocks_modal_props, "modal_stack_active_index",
            rows=max(2, len(context.scene.dgblocks_modal_props.modal_stack_items))
        )
        layout.operator("modal_stack.add", icon='ADD') 

# =============================================================================
# PRIVATE MODULE API — should not be used outside this file
# =============================================================================

def print_current_modals():
    for op in bpy.context.window_manager.operators:
        print("==========\n", op.bl_idname)      # e.g. 'TRANSFORM_OT_translate'
        print(op.name)           # human label
        print(op.properties)     # operator property values at time of execution

def add_modal_op_to_blender_stack(modal_instance):
    #TODO implement this. modal_instance._op_ref needs to be assigned.
    pass
from __future__ import annotations
import bpy
from dataclasses import dataclass, field
from typing import Callable, Optional
from bpy.props import StringProperty, IntProperty, CollectionProperty, BoolProperty


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
from .block_constants import Block_RTC_Members, Block_Logger_Definitions

# ---------------------------------------------------------------------------
# Callbacks & Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModalEntry:
    uid:            str
    bl_idname:      str
    label:          str
    on_event:       Optional[Callable]  = field(default=None, repr=False)
    on_timer:       Optional[Callable]  = field(default=None, repr=False)
    on_start:       Optional[Callable]  = field(default=None, repr=False)
    on_kill:        Optional[Callable]  = field(default=None, repr=False)
    timer_interval: Optional[float]     = field(default=None)
    running:        bool                = field(default=False)
    _op_ref:        Optional[object]    = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.timer_interval is not None and self.on_timer is None:
            raise ValueError(f"Modal {self.uid!r} has timer_interval but no on_timer.")

class ModalStackItem(bpy.types.PropertyGroup):
    uid:     StringProperty()
    label:   StringProperty()
    running: BoolProperty()


# ---------------------------------------------------------------------------
# Stack — all logic, no data
# ---------------------------------------------------------------------------

class Wrapper_Modals_Manager(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        return True


    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------
    
    # --- Instance creation --------------------------------------------------

    @classmethod
    def create_instance(
        cls,
        uid:            str,
        bl_idname:      str,
        label:          str                = "",
        on_event:       Optional[Callable] = None,
        on_timer:       Optional[Callable] = None,
        on_start:       Optional[Callable] = None,
        on_kill:        Optional[Callable] = None,
        timer_interval: Optional[float]    = None,
        autostart:      bool               = False,
        context:        Optional[object]   = None,
    ) -> ModalEntry:
        """
        Create, register, and optionally start a new managed modal.

        Callbacks:
            on_start / on_kill  ->  (entry, context)
            on_timer            ->  (entry, context)
            on_event            ->  (entry, context, event) -> set | None
        """

        entry = ModalEntry(
            uid            = uid,
            bl_idname      = bl_idname,
            label          = label or uid,
            on_event       = on_event,
            on_timer       = on_timer,
            on_start       = on_start,
            on_kill        = on_kill,
            timer_interval = timer_interval,
        )

        Wrapper_Runtime_Cache.add_unique_instance_to_registry_list(Block_RTC_Members.MODALS_CACHE, "uid", entry)

        if autostart:
            if context is None:
                raise ValueError("context is required when autostart=True")
            cls.start(uid, context)

        return entry


    # --------------------------------------------------------------
    # Funcs specific to this class
    # --------------------------------------------------------------

    @classmethod
    def start(cls, uid: str, context) -> None:
        _, entry = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.MODALS_CACHE, "uid", uid)
        if entry.running:
            return
        # getattr(bpy.ops, entry.bl_idname.replace(".", "_"))(
        #     'INVOKE_DEFAULT', modal_uid=uid
        # )
        space, name = entry.bl_idname.split(".", 1)
        getattr(getattr(bpy.ops, space), name)('INVOKE_DEFAULT', modal_uid=uid)


    @classmethod
    def stop(cls, uid: str) -> None:
        _, entry = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.MODALS_CACHE, "uid", uid)
        if entry.running and entry._op_ref is not None:
            entry._op_ref._exit_requested = True

    # @classmethod
    # def stop_all(cls) -> None:
    #     for entry in cls.entries():
    #         if entry.running:
    #             cls.stop(entry.uid)

    # --- Delete -------------------------------------------------------------

    @classmethod
    def destroy_instance(cls, uid: str) -> None:
        
        # Stop modal
        _, modal_instance = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
            member_key = Block_RTC_Members.MODALS_CACHE, 
            uniqueness_field = "uid", 
            uniqueness_field_value = uid,
        )
        if modal_instance.running:
            cls.stop(uid)
            
        # Remove from registry
        Wrapper_Runtime_Cache.destroy_unique_instance_from_registry_list(
            member_key = Block_RTC_Members.MODALS_CACHE, 
            uniqueness_field = "uid", 
            uniqueness_field_value = uid,
        )

    # --- Operator callbacks -------------------------------------------------

    @classmethod
    def _notify_started(cls, uid: str, op_instance) -> None:
        entry         = cls._require(uid)
        entry.running = True
        entry._op_ref = op_instance
        if entry.on_start:
            entry.on_start(entry, bpy.context)

    @classmethod
    def _notify_stopped(cls, uid: str) -> None:
        entry         = cls._require(uid)
        entry.running = False
        entry._op_ref = None
        if entry.on_kill:
            entry.on_kill(entry, bpy.context)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _sync_ui_list(context) -> None:
    pass
    # items = context.scene.modal_stack_items
    # items.clear()
    # for entry in Wrapper_Modals_Manager.entries():
    #     item         = items.add()
    #     item.uid     = entry.uid
    #     item.label   = entry.label
    #     item.running = entry.running


class MODAL_OT_Toggle(bpy.types.Operator):
    bl_idname = "modal_stack.toggle"
    bl_label  = "Toggle Modal"
    uid: StringProperty()

    def execute(self, context):
        entry = Wrapper_Modals_Manager.get(self.uid)
        if entry is None:
            return {'CANCELLED'}
        Wrapper_Modals_Manager.stop(self.uid) if entry.running else Wrapper_Modals_Manager.start(self.uid, context)
        return {'FINISHED'}

class MODAL_OT_Add(bpy.types.Operator):
    """Add a new modal to the stack with default parameters."""
    bl_idname = "modal_stack.add"
    bl_label  = "Add Modal"

    # Editable in the operator redo panel / F9
    uid:            StringProperty(name="UID",       default="")
    bl_idname_prop: StringProperty(name="Operator",  default="wm.my_modal")
    label:          StringProperty(name="Label",     default="New Modal")
    timer_interval: bpy.props.FloatProperty(
                        name="Timer Interval",
                        default=0.0,
                        min=0.0,
                        description="0 = no timer"
                    )
    autostart:      BoolProperty(name="Autostart",   default=True)

    def invoke(self, context, event):
        # Auto-generate a uid if not provided
        if not self.uid:
            import uuid
            self.uid = "modal_" + uuid.uuid4().hex[:6]
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "uid")
        layout.prop(self, "bl_idname_prop")
        layout.prop(self, "label")
        layout.prop(self, "timer_interval")
        layout.prop(self, "autostart")

    def execute(self, context):
        interval = self.timer_interval if self.timer_interval > 0.0 else None
        try:
            Wrapper_Modals_Manager.create_instance(
                uid            = self.uid,
                bl_idname      = self.bl_idname_prop,
                label          = self.label,
                timer_interval = interval,
                autostart      = self.autostart,
                context        = context if self.autostart else None,
            )
        except (KeyError, ValueError) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

class MODAL_OT_Delete(bpy.types.Operator):
    bl_idname = "modal_stack.delete"
    bl_label  = "Delete Modal"
    uid: StringProperty()

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
        toggle = row.operator(
            "modal_stack.toggle",
            text="Stop" if item.running else "Start",
            icon='PAUSE'  if item.running else 'PLAY'
        )
        toggle.uid = item.uid
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
            context.scene, "modal_stack_items",
            context.scene, "modal_stack_active_index",
            rows=max(2, len(context.scene.modal_stack_items))
        )
        layout.operator("modal_stack.add", icon='ADD')   # ← add this line

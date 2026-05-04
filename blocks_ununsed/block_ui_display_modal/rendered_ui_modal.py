from enum import Enum
import logging
import traceback
from typing import Callable, Optional

import bpy
from bpy.app.handlers import persistent
import math
import os
from math import cos, sin, acos, pi, degrees
import time
import struct
import bpy
import bmesh

import gpu
import blf
import mathutils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix, Euler
from bpy_extras.view3d_utils import location_3d_to_region_2d

from ..blocks_natively_included._block_core.core_block_constants import addon_name
from ..blocks_natively_included._block_core.core_feature_logs import get_logger
from ..addon_config import Documentation_URLs
from ..blocks_natively_included._block_core.core_helper_uilayouts import force_redraw_ui, create_ui_box_with_header, uilayout_draw_block_panel_header
from .shader_wrapper import Basic_Builtin_Shader_Names, DGBlocks_Shader_Wrapper, Shader_Types
from .draw_functions.my_draw_funcs_2d import draw_simple_box
from .draw_functions.shared_helper_functions import config_gpu_for_occluded_3d_draw

# =============================================================================
# VARIABLES
# =============================================================================

# Loggers are instanciated during addon register event
logger_ui: Optional[logging.Logger] = None
logger_lifecycle: Optional[logging.Logger] = None

# =============================================================================
# CONFIGURATION - Define your draw logic here
# =============================================================================

def my_2d_draw_callback(cls, context):
    
    if context.scene.dgblocks_display_modal_props.enable_example_display_1:
        shader_wrapper = cls.get_shader_wrapper_by_id_from_modal_registry("example shader 1")
        draw_simple_box(context, shader_wrapper)

def my_3d_draw_callback(cls, context):
    
    config_gpu_for_occluded_3d_draw()

def my_shader_controller_update_callback(self, context):
    """
    This function is an update-callback for certain Scene.dgblocks_display_modal_props properties
    The DGBlocks template uses boolean properties to toggle shader creation & destruction
    This function is just to serve as a demo. In your own addon, you would likely use different events to control shaders
    """

    # Example 1 uses a single basic POST_PIXEL Shader
    example_1_shader_name = "example shader 1"
    if self.enable_example_display_1:
        create_basic_builtin_shader_if_absent(
                buitlin_shader_choice = Basic_Builtin_Shader_Names.UNIFORM_COLOR,
                shader_type = Shader_Types.TRIS,
                shader_id = example_1_shader_name)
    if not self.enable_example_display_1:
        remove_shader_wrapper_from_modal_registry_by_name(example_1_shader_name)
                              
    # Example 2 uses a multiple basic POST_PIXEL Shaders, all with the same shader group.
    # They can be decativated
    # shader_example_2_ids = ["Example Shader 2A", "Example Shader 2A"]
    # shader_example_2_group_id = "Shader Group 2"
    # if self.enable_example_display_2:
    #     create_basic_builtin_shader_if_absent(
    #             buitlin_shader_choice = Basic_Builtin_Shader_Names.POLYLINE_SMOOTH_COLOR,
    #             shader_type = Shader_Types.LINES,
    #             shader_id = shader_example_2_ids[0],
    #             shader_group_id = shader_example_2_group_id)
    #     create_basic_builtin_shader_if_absent(
    #             buitlin_shader_choice = Basic_Builtin_Shader_Names.POLYLINE_SMOOTH_COLOR,
    #             shader_type = Shader_Types.LINES,
    #             shader_id = shader_example_2_ids[1],
    #             shader_group_id = shader_example_2_group_id)
    # if not self.enable_example_display_1:
    #     remove_shader_wrapper_from_modal_registry_by_group_name(shader_example_2_group_id)

# =============================================================================
# PUBLIC API - Accessible by other modules in this addon
# =============================================================================

def create_basic_builtin_shader_if_absent(
        buitlin_shader_choice: Basic_Builtin_Shader_Names, 
        shader_type: Shader_Types, 
        shader_id: str, 
        shader_group_id: Optional[str] = None):
    
    # Will have no result if the shader already exists
    
    global logger_ui
    
    # Validate name uniqueness
    _, active_shader_names = get_active_shaders_of_display_modal()
    if shader_id in active_shader_names:
        logger_ui.debug("Shader with name {shader_id} already exists, skipping recreation")
        return
    
    DGBLOCKS_OT_DisplayModal.create_builtin_shader(
            buitlin_shader_choice, 
            shader_type, 
            shader_id, 
            shader_group_id)
    
    logger_ui.debug(f"Created Shader wrapper {shader_id}")
    logger_ui.debug(f"Existing Shaders {shader_id}")
    
def remove_shader_wrapper_from_modal_registry_by_name(name):
    
    DGBLOCKS_OT_DisplayModal.remove_shader_wrapper_from_modal_registry(by_shader_id = name, by_shader_group_id = None)

def remove_shader_wrapper_from_modal_registry_by_group_name(name):
    
    DGBLOCKS_OT_DisplayModal.remove_shader_wrapper_from_modal_registry(by_shader_id = None, by_shader_group_id = name)

def remove_all_shaders():
    
    DGBLOCKS_OT_DisplayModal.clear_all_shader_wrappers_from_modal_registry()
    
def get_active_shaders_of_display_modal():
    
    active_shaders = DGBLOCKS_OT_DisplayModal.get_all_shader_wrappers_from_modal_registry()
    active_shader_ids = [s.shader_unique_id for s in active_shaders]
    return active_shaders, active_shader_ids

#================================================================
# MODAL OPERATOR - he main focus of this package, owns the drawing callback functions & modal timer, handles mouse/key events
# its modal(...) function is called both on mouse/key events & timer updates
#================================================================

class DGBLOCKS_OT_DisplayModal(bpy.types.Operator):
    bl_idname = "dgblocks.display_modal"
    bl_label = "Advanced Display Modal"
    
    #================================================================
    # CLASS VARIABLES - These should always be accessed via class, not instance
    # Example: DGBLOCKS_OT_DisplayModal._instance_running or cls._instance_running
    #================================================================
    
    # Used by the Modal's should-stop / should-start logic
    # The modal will be automatically restarted if it dies while _instance_running is True
    # If the modal dies unexpectedly, it likely due to an Exception in modal(...) or draw-callback functions
    _instance_running: bool = False
    
    # Cache draw handler functions for the modal lifespan
    # Will be populated with draw_callback_2d & draw_callback_3d fucntions after Modal starts
    _cached_2d_draw_callback: Optional[Callable] = None
    _cached_3d_draw_callback : Optional[Callable] = None

    # DGBLOCKS_OT_DisplayModal holds ownership of all the Shaders that it draws
    _shader_registry: list = []
    
    #================================================================
    # STANDARD FUNCTIONS - expected in a bpy.types.Operator. These execute for the instance (not class) of DGBLOCKS_OT_DisplayModal
    #================================================================

    def invoke(self, context, event):
        
        if DGBLOCKS_OT_DisplayModal._instance_running:
            return {'CANCELLED'}
        DGBLOCKS_OT_DisplayModal._instance_running = True
        
        self.mouse_x = event.mouse_region_x
        self.mouse_y = event.mouse_region_y
        
        # Create draw handlers & link them to callback functions
        # These will exist while the display modal is active
        DGBLOCKS_OT_DisplayModal._cached_2d_draw_callback = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_2d, (context,), 'WINDOW', 'POST_PIXEL')
        DGBLOCKS_OT_DisplayModal._cached_3d_draw_callback = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context,), 'WINDOW', 'POST_VIEW')
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        
        # Kill modal if marked as inactive
        if not context.scene.dgblocks_display_modal_props.myaddon_display_active:
            DGBLOCKS_OT_DisplayModal.kill_display_modal(context)
            return {'CANCELLED'}
        
        # Update mouse position every event
        self.mouse_x = event.mouse_region_x
        self.mouse_y = event.mouse_region_y
        
        # Force redraw for animation
        # context.area.tag_redraw()
        
        # if event.type == 'MOUSEMOVE':
        #     pass  # Already updated above
        
        return {'PASS_THROUGH'}

    #================================================================
    # CUSTOM FUNCTIONS - they do not exist inside bpy.types.Operator
    # Since there is only intended to be one Display Modal used in an addon, class (not instance) methods are used
    #================================================================
    
    @classmethod
    def draw_callback_2d(cls, context):
        
        # 2D (POST_PIXEL) Draw callback for 3D Viewport
        
        try:
            my_2d_draw_callback(cls, context)
            
        except Exception as e:
            traceback.print_exc()
            if context.scene.dgblocks_display_modal_props.should_kill_modal_upon_display_error:
                cls.kill_display_modal(context)

    @classmethod
    def draw_callback_3d(cls, context):
        
        # 3D (POST_VIEW) Draw callback for 3D Viewport
        
        try:
            my_3d_draw_callback(cls, context)

        except Exception as e:
            traceback.print_exc()
            if context.scene.dgblocks_display_modal_props.should_kill_modal_upon_display_error:
                DGBLOCKS_OT_DisplayModal.kill_display_modal(context)

    @classmethod
    def is_running(cls) -> bool:
        return cls._instance_running

    @classmethod
    def kill_display_modal(cls, context):
        
        DGBLOCKS_OT_DisplayModal._instance_running = False
        if DGBLOCKS_OT_DisplayModal._cached_2d_draw_callback is not None:
            bpy.types.SpaceView3D.draw_handler_remove(DGBLOCKS_OT_DisplayModal._cached_2d_draw_callback, 'WINDOW')
            DGBLOCKS_OT_DisplayModal._cached_2d_draw_callback = None
        if DGBLOCKS_OT_DisplayModal._cached_3d_draw_callback is not None:
            bpy.types.SpaceView3D.draw_handler_remove(DGBLOCKS_OT_DisplayModal._cached_3d_draw_callback, 'WINDOW')
            DGBLOCKS_OT_DisplayModal._cached_3d_draw_callback = None
        
        force_redraw_ui(context)
    
    @classmethod
    def create_builtin_shader(
            cls,
            buitlin_shader_choice: Basic_Builtin_Shader_Names, 
            shader_type: Shader_Types, 
            shader_id: str, 
            shader_group_id: str | None):
        
        global logger_ui
        global _shader_registry
    
        # Raise Exception if the shader already exists
        shader_wrapper = cls.get_shader_wrapper_by_id_from_modal_registry(shader_id) 
        if shader_wrapper is not None:
            raise Exception("Shader '{shader_id}' already exists")
        
        # Create shader & add to registry
        logger_ui.debug(f"Creating Bulitin Shader Wrapper id = {shader_id}, group = {shader_group_id}")
        new_shader = DGBlocks_Shader_Wrapper(
            builtin_shader_name = buitlin_shader_choice, 
            shader_type = shader_type, 
            shader_unique_id = shader_id,
            shader_group_id = shader_group_id)
        if new_shader is None:
            raise Exception("Error creating shader '{shader_id}' (null after creation)")
        else:
            cls._shader_registry.append(new_shader)
        
    @classmethod
    def get_all_shader_wrappers_from_modal_registry(cls) -> list[DGBlocks_Shader_Wrapper]:
        
        global _shader_registry
        return cls._shader_registry
    
    @classmethod
    def get_shader_wrapper_by_id_from_modal_registry(cls, by_shader_group_id: str) -> DGBlocks_Shader_Wrapper:
        
        global logger_ui
        global _shader_registry
        shader_wrappers = [w for w in cls._shader_registry if w.shader_unique_id == by_shader_group_id]
        if len(shader_wrappers) == 0:
            logger_ui.debug("No Shader Wrapper exists with id = {shader_id}")
            return None
        else: # This assumes that id uniqueness is still enforced at shader creation
            return shader_wrappers[0]
    
    @classmethod
    def remove_shader_wrapper_from_modal_registry(cls, by_shader_id: str | None, by_shader_group_id: str | None):
        
        global logger_ui
        global _shader_registry
        shaders_to_remove = []
        active_shaders = cls.get_all_shader_wrappers_from_modal_registry()
        active_shader_ids = [s.shader_unique_id for s in active_shaders]
        
        if by_shader_id is None and by_shader_group_id is None:
            logger_ui.debug(f"by_shader_id and by_shader_group_id are both empty. This remove_shader_wrapper_from_modal_registry call does nothing")
        
        if by_shader_group_id is not None: 
            shaders_of_group = [s for s in active_shaders if s.shader_group_id == by_shader_group_id]
            shaders_to_remove.extend(shaders_of_group)
        
        if by_shader_id is not None and by_shader_id in active_shader_ids:
            list_idx = active_shader_ids.index(by_shader_id)
            shader = active_shaders[list_idx]
            shaders_to_remove.append(shader)
        
        # Clear GPU references  & remove from registry
        for shader in shaders_to_remove:
            logger_ui.debug(f"Removing Shader Wrapper {shader.shader_unique_id}, group = {shader.shader_group_id}")
            shader._batch = None
            shader._shader = None
            shader._texture = None
            cls._shader_registry.remove(shader)
    
    @classmethod
    def clear_all_shader_wrappers_from_modal_registry(cls):
        
        global _shader_registry
        for shader in cls._shader_registry[:]:
            DGBLOCKS_OT_DisplayModal.remove_shader_wrapper_from_modal_registry(shader)
        cls._shader_registry.clear()
    
#================================================================
# UI - Panel for Modal Display & Shader toggles
#================================================================

class DGBLOCKS_PT_Modal_Display(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_Modal_Display"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_name
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        
        is_modal_active = bpy.context.scene.dgblocks_display_modal_props.myaddon_display_active
        label_text = "Modal Display"
        label_icon = "CHECKBOX_HLT" if is_modal_active else "CHECKBOX_DEHLT"
        uilayout_draw_block_panel_header(context, self.layout, label_text, Documentation_URLs.MY_PLACEHOLDER_URL_2, label_icon)
    
    def draw(self, context):
        display_props = bpy.context.scene.dgblocks_display_modal_props
        layout = self.layout
        
        layout.prop(display_props, "myaddon_display_active", toggle=True)
        if display_props.myaddon_display_active:
            
            box = create_ui_box_with_header(context, layout, "General Settings")
            box.prop(display_props, "should_be_activated_after_startup", toggle=True)
            
            box = create_ui_box_with_header(context, layout, "Simple 2D Shaders")
            box.prop(display_props, "enable_example_display_1", toggle=True)
            
#================================================================
# MODULE DATA STORAGE - Saves modal status into Scene
#================================================================

def update_display_switch(self, context):
    
    is_active = context.scene.dgblocks_display_modal_props.myaddon_display_active
    is_running = DGBLOCKS_OT_DisplayModal.is_running()

    if is_active and not is_running: # Modal needs startup
        
        logger = get_logger("ui")
        logger.info("Restarting DGBlocks Display Modal")
        bpy.ops.dgblocks.display_modal('INVOKE_DEFAULT')
        
    if not is_active and is_running: # Modal needs stopped
        DGBLOCKS_OT_DisplayModal.kill_display_modal(context)

class DGBLOCKS_DISPLAY_MODAL_PROPS(bpy.types.PropertyGroup):
    
    myaddon_display_active: bpy.props.BoolProperty(
        name="Toggle UI Display Modal",
        description="Toggle UI Display Modal",
        default=False,
        update=update_display_switch) # type: ignore
    should_be_activated_after_startup: bpy.props.BoolProperty(default = True, name = "Modal should run at startup") # type: ignore
    should_kill_modal_upon_display_error: bpy.props.BoolProperty(default = False, name = "Modal should end on render error") # type: ignore
    
    enable_example_display_1: bpy.props.BoolProperty(default = True, name = "Red Square", update = my_shader_controller_update_callback) # type: ignore
    enable_example_display_2: bpy.props.BoolProperty(default = True, name = "t2", update = my_shader_controller_update_callback) # type: ignore
    enable_example_display_3: bpy.props.BoolProperty(default = True, name = "t3", update = my_shader_controller_update_callback) # type: ignore

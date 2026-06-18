
import random
import sys
import bpy
from .custom_shaders.helpers import populate_points, populate_boundary_edges  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_helpers.ui import ui_draw_block_panel_header
from ...addon_helpers.generic_tools import force_redraw_ui

from ...native_blocks.block_timers.data_structures import Timer_Definition
from ...native_blocks.block_mesh_extract.data_structures import ALL_MET_ATTRS, MET, Mesh_Extract_Target
from ...native_blocks.block_mesh_extract.callbacks import cb_face_face_neighbors
from ...native_blocks.block_mesh_extract.feature_mesh_extract import Wrapper_Mesh_Extract

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_declarations import Block_Loggers
from .shader_declarations import FLATYPUS_SHADER_DEFS
from .mesh_extract_helpers import compute_coplanar_boundaries, compute_coplanar_groups

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

def _cb_show_boundary_edges_changed(self, context):
    """
    Fired when the user toggles 'show_boundary_edges'.
    If turned on: push geometry from the most recent extract (if available) and redraw.
    If turned off: clear the shader geometry and redraw.
    """
    from ...native_blocks.block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager

    shader = Wrapper_Shader_Manager.get_shader("FLATYPUS_BOUNDARY_EDGES")
    if shader is None:
        return  # Drawing not enabled; nothing to do.

    if self.show_boundary_edges:
        instance = Wrapper_Mesh_Extract.get_instance("Cube")
        if instance:
            populate_boundary_edges(instance)
    else:
        shader.set_points([])
        shader.set_colors([])

    force_redraw_ui(context)


# ==============================================================================================================================
# BL PROPERTY GROUPS
# ==============================================================================================================================

class DGBLOCKS_PG_Flatypus_Props(bpy.types.PropertyGroup):
    """Scene-level property group for block_flatypus_modes_manager."""
    show_boundary_edges: bpy.props.BoolProperty(  # type: ignore
        name="Show Boundary Edges",
        description="Draw coplanar-group boundary edges in the viewport",
        default=False,
        update=_cb_show_boundary_edges_changed,
    )


# ==============================================================================================================================
# HOOK SUBSCRIBERS
# Top-level functions — auto-discovered by Wrapper_Hooks at registration time.
# ==============================================================================================================================

def hook_get_shader_definitions():

    return FLATYPUS_SHADER_DEFS

def timer_call(aa):

    num = random.randint(0, 50)
    if num > 40:
        raise Exception(f"Exception_{num}")
    print(aa)


def hook_before_first_draw():

    populate_points()

    # If the toggle is already on when drawing is first enabled, push boundary data
    props = bpy.context.scene.dgblocks_flatypus_props
    if props.show_boundary_edges:
        instance = Wrapper_Mesh_Extract.get_instance("Cube")
        if instance:
            populate_boundary_edges(instance)


def hook_get_mesh_extract_targets():

    def _cb_planarity_groups(instance):
        ffi, ffo = instance.custom_attribute_arrays["face_face_neighbors"]
        computed_data = compute_coplanar_groups(
            face_normals                 = instance.face_normal,
            face_areas                   = instance.face_area,
            face_face_neighbor_indices   = ffi,
            face_face_neighbor_offsets   = ffo,
            vertex_co                    = instance.vertex_co,
            face_loop_start              = instance.face_loop_start,
            face_loop_total              = instance.face_loop_total,
            corner_vertex_index          = instance.corner_vertex_index,
            tolerance_deg                = 0.3,
            min_area                     = 0.001,
            self_planarity_threshold     = 0.3,
        )
        return computed_data

    def _cb_planarity_boundaries(instance):
        group_ids = instance.custom_attribute_arrays["face_planar_groups"]
        ffi, ffo = instance.custom_attribute_arrays["face_face_neighbors"]

        data = compute_coplanar_boundaries(
            group_ids                    = group_ids,
            face_face_neighbor_indices   = ffi,
            face_face_neighbor_offsets   = ffo,
            edge_vertices                = instance.edge_vertices,
            face_loop_start              = instance.face_loop_start,
            face_loop_total              = instance.face_loop_total,
            corner_vertex_index          = instance.corner_vertex_index,
            n_faces                      = instance.face_normal.shape[0],
        )
        return data

    return [
        Mesh_Extract_Target(
            object_name = "Cube",
            read_attributes = ALL_MET_ATTRS,
            callbacks = {
                "face_face_neighbors":         cb_face_face_neighbors,
                "face_planar_groups":          _cb_planarity_groups,
                "planar_group_boundary_edges": _cb_planarity_boundaries,
            },
        ),
    ]

def hook_mesh_extract_ready(object_names):
    """
    Called after mesh extraction completes.
    If the boundary-edge overlay is toggled on, push updated geometry to the shader
    and force the viewport to redraw.
    """
    props = bpy.context.scene.dgblocks_flatypus_props
    if not props.show_boundary_edges:
        return

    if "Cube" not in object_names:
        return

    instance = Wrapper_Mesh_Extract.get_instance("Cube")
    if instance:
        populate_boundary_edges(instance)
        force_redraw_ui(bpy.context)


# ==============================================================================================================================
# UI PANEL
# ==============================================================================================================================

class DGBLOCKS_PT_Assembly_Mode_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "DGBLOCKS_PT_Assembly_Mode_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = addon_title
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 0

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            "FLT-mode-debug",
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name="TOOL_SETTINGS",
        )

    def draw(self, context):
        layout = self.layout
        drawing_props = context.scene.dgblocks_onscreen_drawing_props
        flatypus_props = context.scene.dgblocks_flatypus_props

        layout.prop(
            drawing_props,
            "enable_drawing",
            toggle=True,
        )

        row = layout.row()
        row.enabled = drawing_props.enable_drawing
        row.prop(
            flatypus_props,
            "show_boundary_edges",
            toggle=True,
        )


# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS
# ==============================================================================================================================

def register_block_props():
    bpy.types.Scene.dgblocks_flatypus_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Flatypus_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_flatypus_props"):
        del bpy.types.Scene.dgblocks_flatypus_props


# ==============================================================================================================================
# BLOCK DECLARATION
# ==============================================================================================================================

_BLOCK_DECLARATION = Block_Declaration(
    block_module=sys.modules[__name__],
    block_id="block-flatypus-assembly-mode",
    block_dependencies=[
        "block-core",
        "block-onscreen-draw",
        "block-timers",
        "block-mesh-extract",
    ],
    block_bpy_classes=[
        DGBLOCKS_PG_Flatypus_Props,
        DGBLOCKS_PT_Assembly_Mode_Panel,
    ],
    block_loggers=Block_Loggers,
)

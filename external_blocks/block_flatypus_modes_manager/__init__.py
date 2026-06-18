
import random
import sys
import bpy
from .custom_shaders.helpers import populate_points  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config.static_settings import Documentation_URLs, addon_title
from ...addon_helpers.data_structures import Block_Declaration
from ...addon_helpers.ui import ui_draw_block_panel_header

from ...native_blocks.block_timers.data_structures import Timer_Definition
from ...native_blocks.block_mesh_extract.data_structures import ALL_MET_ATTRS, MET, MET_Attr_Declaration, Mesh_Extract_Callback, Mesh_Extract_Target

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .common_declarations import Block_Loggers
from .shader_declarations import FLATYPUS_SHADER_DEFS
from .mesh_extract_helpers import compute_coplanar_boundaries, compute_coplanar_groups

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

# def hook_get_timer_definitions():

#     return [
#         Timer_Definition(
#             timer_uid = "A-timer",
#             frequency = 0.5,
#             callback = timer_call,
#         ),
#         Timer_Definition(
#             timer_uid = "B-timer",
#             frequency = 0.5,
#             callback = timer_call,
#         ),
#         Timer_Definition(
#             timer_uid = "C-timer",
#             frequency = 0.3,
#             callback = timer_call,
#         )
#     ]


def hook_before_first_draw():

    populate_points()

def hook_get_mesh_extract_targets():

    def _cb_planarity_groups(instance, tolerance_deg, min_area, self_planarity_threshold):
        computed_data = compute_coplanar_groups(
            face_normals                 = instance.face_normal,
            face_areas                   = instance.face_area,
            face_face_neighbor_indices   = instance.face_face_neighbor_indices,
            face_face_neighbor_offsets   = instance.face_face_neighbor_offsets,
            vertex_co                    = instance.vertex_co,
            face_loop_start              = instance.face_loop_start,
            face_loop_total              = instance.face_loop_total,
            corner_vertex_index          = instance.corner_vertex_index,
            tolerance_deg                = tolerance_deg,
            min_area                     = min_area,
            self_planarity_threshold     = self_planarity_threshold,
        )

        instance.custom_domain_data["coplanar_group_id"] = computed_data
        return computed_data

    def _cb_planarity_boundaries(instance):
        group_ids = instance.custom_domain_data.get("coplanar_group_id")
        if group_ids is None:
            return
        instance.custom_domain_data["coplanar_boundaries"] = compute_coplanar_boundaries(
            group_ids                    = group_ids,
            face_face_neighbor_indices   = instance.face_face_neighbor_indices,
            face_face_neighbor_offsets   = instance.face_face_neighbor_offsets,
            edge_vertices                = instance.edge_vertices,
            face_loop_start              = instance.face_loop_start,
            face_loop_total              = instance.face_loop_total,
            corner_vertex_index          = instance.corner_vertex_index,
            n_faces                      = instance.face_normal.shape[0],
        )



    _PLANARITY_GROUPS_CB = Mesh_Extract_Callback(
        uid                 = "FLT_COPLANAR_GROUPS",
        callback            = _cb_planarity_groups,
        required_attributes = [
            MET.FACE.NORMAL, MET.FACE.AREA,
            MET.FACE.FACE_NEIGHBORS,
            MET.VERTEX.CO,
            MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL,
            MET.CORNER.VERTEX_INDEX,
        ],
        params = {
            "tolerance_deg":            1.0,
            "min_area":                 0.0001,
            "self_planarity_threshold": 0.001,
        },
    )

    _PLANARITY_BOUNDARIES_CB = Mesh_Extract_Callback(
        uid                 = "FLT_COPLANAR_BOUNDARIES",
        callback            = _cb_planarity_boundaries,
        required_attributes = [
            MET.FACE.FACE_NEIGHBORS,
            MET.EDGE.VERTICES,
            MET.FACE.LOOP_START, MET.FACE.LOOP_TOTAL,
            MET.CORNER.VERTEX_INDEX,
        ],

    )

    
    return [
        Mesh_Extract_Target(
            object_name = "Cube",
            read_attributes = ALL_MET_ATTRS,
            # custom_attributes = [
            #     (MET.VERTEX, "custom-Attr-FL"),
            #     (MET.FACE, "Custom-attr-VEC") 
            # ],
            callbacks = [
                _PLANARITY_GROUPS_CB,
                _PLANARITY_BOUNDARIES_CB,   # must run after groups
            ],
        ),
    ]

def hook_mesh_extract_ready(object_names):
    print("ready", object_names)


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
        layout.prop(
            context.scene.dgblocks_onscreen_drawing_props,
            "enable_drawing",
            toggle=True,
        )


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
    ],
    block_bpy_classes=[
        DGBLOCKS_PT_Assembly_Mode_Panel,
    ],
    block_loggers=Block_Loggers,
)


import bpy
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix, Euler
from bpy_extras.view3d_utils import location_3d_to_region_2d
import gpu
import blf

def config_gpu_for_occluded_3d_draw():
    
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(True)
    
def config_gpu_for_unoccluded_3d_draw():
    
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    gpu.state.depth_mask_set(False)

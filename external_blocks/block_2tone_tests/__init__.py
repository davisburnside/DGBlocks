"""
Terminator Point Cloud — Blender 5.0 addon
-------------------------------------------
Registers a POST_VIEW draw handler that, each viewport redraw:

  1. Reads the live viewport backbuffer (realtime compositor output)
  2. Draws two GPU offscreen passes against the target mesh:
       - Mask pass    : 1 where mesh pixel, 0 elsewhere
       - World pos pass: RGB = world XYZ (float32 framebuffer)
  3. Auto-detects the two toon tones from masked pixels
  4. Edge-detects the terminator boundary
  5. Looks up world positions at terminator pixels
  6. Writes result to global numpy array:
       vpbake_terminator_points  — shape (N, 3), float32, world space

Feed vpbake_terminator_points into your own curve-fit / draw logic.
The array is replaced every redraw. Check vpbake_terminator_points is
not None before using it.
"""



import bpy
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.props import PointerProperty, IntProperty, BoolProperty, StringProperty
from bpy.types import Panel, Operator, PropertyGroup


# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.generic_helpers import get_self_block_module, clear_console
from ...my_addon_config import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ...blocks_natively_included import _block_core
from ...blocks_natively_included._block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from ...blocks_natively_included._block_core.core_features.feature_hooks import Wrapper_Hooks
from ...blocks_natively_included._block_core.core_features.feature_block_manager import Wrapper_Block_Management
from ...blocks_natively_included._block_core.core_features.feature_runtime_cache  import Wrapper_Runtime_Cache
from ...addon_helpers.ui_drawing_helpers import ui_draw_block_panel_header

from ...blocks_natively_included.block_onscreen_drawing.constants import Block_RTC_Members as Onscreen_Draw_Block_RTC_Members
from ...blocks_natively_included.block_onscreen_drawing.feature_draw_handler_manager import Wrapper_Draw_Handlers

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID = "block-2tone-test1" 
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [
    "block-core",
    "block-onscreen-drawing"
] 


# ---------------------------------------------------------------------------
# Global output — your draw logic reads this
# ---------------------------------------------------------------------------


vpbake_terminator_points = None   # numpy (N, 3) float32, world space, or None
 
 
# ---------------------------------------------------------------------------
# GLSL shaders
# ---------------------------------------------------------------------------
 
# --- Mask shader: outputs 1.0 in R where mesh covers this pixel
_MASK_VERT = """
in vec3 position;
uniform mat4 viewProjectionMatrix;
 
void main() {
    gl_Position = viewProjectionMatrix * vec4(position, 1.0);
}
"""
_MASK_FRAG = """
out vec4 fragColor;
void main() {
    fragColor = vec4(1.0, 0.0, 0.0, 1.0);
}
"""
 
# --- World position shader: outputs world XYZ in RGB
_WPOS_VERT = """
in vec3 position;
uniform mat4 viewProjectionMatrix;
out vec3 worldPos;
 
void main() {
    worldPos    = position;   /* 'position' is already in world space */
    gl_Position = viewProjectionMatrix * vec4(position, 1.0);
}
"""
_WPOS_FRAG = """
in vec3 worldPos;
out vec4 fragColor;
 
void main() {
    fragColor = vec4(worldPos, 1.0);
}
"""
 
 
# ---------------------------------------------------------------------------
# GPU helpers
# ---------------------------------------------------------------------------
 
def _make_offscreen(w, h):
    """Create a float32 RGBA offscreen buffer."""
    return gpu.types.GPUOffScreen(w, h, format='RGBA32F')
 
 
def _get_view_projection_matrix(context):
    """Return the 4×4 view-projection matrix from the active 3D viewport."""
    r3d = context.space_data.region_3d
    return r3d.perspective_matrix   # already view * projection
 
 
def _draw_mesh_offscreen(offscreen, mesh_batch, shader, vp_matrix, w, h):
    """
    Draw mesh_batch into offscreen using shader.
    Sets viewProjectionMatrix uniform.
    Returns (H, W, 4) float32 numpy array read back from the framebuffer.
    """
    with offscreen.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0))
 
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)
 
        shader.bind()
        shader.uniform_float("viewProjectionMatrix", vp_matrix)
        mesh_batch.draw(shader)
 
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)
 
        # Read back — foreach_ equivalent for gpu.Buffer
        buf = fb.read_color(0, 0, w, h, 4, 0, 'FLOAT')
 
    # buf is a gpu.types.Buffer; convert via numpy without a Python loop
    arr = np.array(buf, dtype=np.float32)   # copies once, vectorised
    arr = arr.reshape(h, w, 4)
    # Framebuffer origin is bottom-left; numpy convention matches, no flip needed
    return arr
 
 
def _read_viewport_backbuffer(context, w, h):
    """
    Read the current viewport color backbuffer (POST_VIEW = scene drawn,
    UI not yet drawn).  Returns (H, W, 4) float32 numpy array.
    """
    fb = gpu.state.active_framebuffer_get()
    buf = fb.read_color(0, 0, w, h, 4, 0, 'FLOAT')
    arr = np.array(buf, dtype=np.float32).reshape(h, w, 4)
    return arr
 
 
def _build_mesh_batch(obj, mask_shader, wpos_shader):
    """
    Extract evaluated world-space vertex positions and triangle indices
    from obj, build two GPUBatches (one per shader).
 
    Returns (mask_batch, wpos_batch) or (None, None) on failure.
    """
    import bpy
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj  = obj.evaluated_get(depsgraph)
 
    try:
        mesh = eval_obj.to_mesh()
    except Exception as e:
        print(f"[Terminator] to_mesh() failed: {e}")
        return None, None
 
    mesh.calc_loop_triangles()
 
    n_verts = len(mesh.vertices)
    n_tris  = len(mesh.loop_triangles)
 
    if n_verts == 0 or n_tris == 0:
        eval_obj.to_mesh_clear()
        return None, None
 
    # --- Vertex positions in world space (foreach_get) ---
    verts_local = np.empty(n_verts * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", verts_local)
    verts_local = verts_local.reshape(n_verts, 3)
 
    # Apply world matrix via numpy (no Python vertex loop)
    mat = np.array(obj.matrix_world, dtype=np.float32)   # (4,4)
    ones = np.ones((n_verts, 1), dtype=np.float32)
    verts_h = np.hstack([verts_local, ones])              # (N, 4)
    verts_world = (mat @ verts_h.T).T[:, :3]             # (N, 3)
 
    # --- Triangle indices (foreach_get) ---
    indices_flat = np.empty(n_tris * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", indices_flat)
    indices = indices_flat.reshape(n_tris, 3).tolist()
 
    eval_obj.to_mesh_clear()
 
    pos_list = verts_world.tolist()
 
    mask_batch = batch_for_shader(mask_shader, 'TRIS',
                                  {"position": pos_list},
                                  indices=indices)
    wpos_batch = batch_for_shader(wpos_shader, 'TRIS',
                                  {"position": pos_list},
                                  indices=indices)
    return mask_batch, wpos_batch
 
 
# ---------------------------------------------------------------------------
# Terminator detection
# ---------------------------------------------------------------------------
 
def _detect_terminator(color_buf, mask_buf, world_buf, min_edge_pixels=10, dbg=False):
    """
    Given:
      color_buf  (H, W, 4) float32 — viewport backbuffer (realtime compositor)
      mask_buf   (H, W, 4) float32 — mesh mask (R channel = 1 where mesh)
      world_buf  (H, W, 4) float32 — world XYZ in RGB channels
 
    Returns (N, 3) float32 world-space points on the terminator, or None.
    """
    H, W = color_buf.shape[:2]
 
    # --- Build mesh mask (bool) ---
    mesh_mask = mask_buf[:, :, 0] > 0.5   # (H, W) bool
 
    if not np.any(mesh_mask):
        if dbg: print("[Terminator] detect: mask is empty — mesh not visible or offscreen draw failed")
        return None
 
    # --- Auto-detect two tones from masked pixels ---
    lum = (color_buf[:, :, 0] * 0.2126 +
           color_buf[:, :, 1] * 0.7152 +
           color_buf[:, :, 2] * 0.0722)   # (H, W)
 
    masked_lum = lum[mesh_mask]
    if dbg:
        print(f"[Terminator] detect: masked pixels={masked_lum.size} "
              f"lum range {masked_lum.min():.4f} – {masked_lum.max():.4f}")
 
    if masked_lum.size < 2:
        if dbg: print("[Terminator] detect: too few masked pixels")
        return None
 
    lo_seed = masked_lum.min()
    hi_seed = masked_lum.max()
    if hi_seed - lo_seed < 1e-4:
        if dbg: print(f"[Terminator] detect: surface appears uniform (range={hi_seed-lo_seed:.6f}) — is realtime compositor active and toon shader on?")
        return None
 
    lo, hi = lo_seed, hi_seed
    for _ in range(3):
        mid   = (lo + hi) * 0.5
        lo_px = masked_lum[masked_lum <= mid]
        hi_px = masked_lum[masked_lum >  mid]
        if lo_px.size == 0 or hi_px.size == 0:
            if dbg: print("[Terminator] detect: k-means degenerate split")
            return None
        lo = lo_px.mean()
        hi = hi_px.mean()
 
    threshold = (lo + hi) * 0.5
    if dbg: print(f"[Terminator] detect: tones lo={lo:.4f} hi={hi:.4f} threshold={threshold:.4f}")
 
    # --- Binary tone map ---
    tone = (lum > threshold) & mesh_mask
 
    # --- Edge detect: 4-neighbour boundary within mesh ---
    edge = np.zeros((H, W), dtype=bool)
    for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
        nb_tone = np.roll(np.roll(tone,      dy, axis=0), dx, axis=1)
        nb_mask = np.roll(np.roll(mesh_mask, dy, axis=0), dx, axis=1)
        edge |= (mesh_mask & nb_mask & (tone != nb_tone))
 
    n_edge = int(np.sum(edge))
    if dbg: print(f"[Terminator] detect: edge pixels={n_edge} (min={min_edge_pixels})")
 
    if n_edge == 0:
        if dbg: print("[Terminator] detect: no edge pixels — tone split may be wrong")
        return None
    if n_edge < min_edge_pixels:
        if dbg: print(f"[Terminator] detect: edge below min threshold")
        return None
 
    world_xyz = world_buf[:, :, :3]
    points = world_xyz[edge]
 
    return points.astype(np.float32)
 
 
# ---------------------------------------------------------------------------
# Draw handler
# ---------------------------------------------------------------------------
 
# Module-level shader instances (created once on register)
_mask_shader = None
_wpos_shader = None
_handler_ref = None
 
 
_dbg_frame = 0   # throttle prints to every N handler calls
 
def _terminator_draw_handler():
    """
    Called by Blender every viewport redraw at POST_VIEW.
    Runs the full pipeline and updates vpbake_terminator_points.
    """
    global vpbake_terminator_points, _dbg_frame
    _dbg_frame += 1
    dbg = (_dbg_frame % 30 == 1)   # print every 30 calls (~1/sec at 30fps)
 
    try:
        _terminator_draw_handler_inner(dbg)
    except Exception as e:
        import traceback
        print(f"[Terminator] EXCEPTION in handler:\n{traceback.format_exc()}")
 
 
def _terminator_draw_handler_inner(dbg=False):
    global vpbake_terminator_points
 
    context = bpy.context
    if context is None:
        if dbg: print("[Terminator] no context")
        return
 
    scene    = context.scene
    settings = getattr(scene, 'terminator_settings', None)
    if settings is None or not settings.active:
        return
 
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        if dbg: print(f"[Terminator] no active mesh (active={context.active_object})")
        return
 
    area   = context.area
    region = context.region
    if area is None or region is None:
        if dbg: print(f"[Terminator] no area/region (area={area}, region={region})")
        return
    if area.type != 'VIEW_3D':
        if dbg: print(f"[Terminator] area is {area.type}, not VIEW_3D")
        return
 
    w, h = region.width, region.height
    if w <= 0 or h <= 0:
        if dbg: print(f"[Terminator] bad region size {w}x{h}")
        return
 
    if dbg: print(f"[Terminator] handler running — obj={obj.name} region={w}x{h}")
 
    # --- Build mesh GPU batches ---
    mask_batch, wpos_batch = _build_mesh_batch(obj, _mask_shader, _wpos_shader)
    if mask_batch is None:
        if dbg: print("[Terminator] batch build failed")
        return
    if dbg: print("[Terminator] batches built ok")
 
    vp_matrix = _get_view_projection_matrix(context)
 
    # --- Offscreen passes ---
    try:
        mask_offscreen = _make_offscreen(w, h)
        wpos_offscreen = _make_offscreen(w, h)
    except Exception as e:
        print(f"[Terminator] Offscreen creation failed: {e}")
        return
 
    if dbg: print("[Terminator] offscreens created ok")
 
    try:
        mask_buf = _draw_mesh_offscreen(
            mask_offscreen, mask_batch, _mask_shader, vp_matrix, w, h)
        wpos_buf = _draw_mesh_offscreen(
            wpos_offscreen, wpos_batch, _wpos_shader, vp_matrix, w, h)
    except Exception as e:
        import traceback
        print(f"[Terminator] offscreen draw failed:\n{traceback.format_exc()}")
        return
    finally:
        mask_offscreen.free()
        wpos_offscreen.free()
 
    if dbg:
        mask_coverage = np.sum(mask_buf[:, :, 0] > 0.5)
        print(f"[Terminator] mask pixels: {mask_coverage} / {w*h}")
        print(f"[Terminator] wpos range X: {wpos_buf[:,:,0].min():.3f} – {wpos_buf[:,:,0].max():.3f}")
 
    # --- Read viewport backbuffer ---
    try:
        color_buf = _read_viewport_backbuffer(context, w, h)
    except Exception as e:
        print(f"[Terminator] backbuffer read failed: {e}")
        return
 
    if dbg:
        print(f"[Terminator] color_buf shape={color_buf.shape} "
              f"min={color_buf.min():.3f} max={color_buf.max():.3f}")
 
    # --- Detect terminator ---
    points = _detect_terminator(
        color_buf, mask_buf, wpos_buf,
        min_edge_pixels=settings.min_edge_pixels,
        dbg=dbg,
    )
 
    vpbake_terminator_points = points
 
    if dbg:
        print(f"[Terminator] points={'None' if points is None else len(points)}")
 
 
# ---------------------------------------------------------------------------
# Property group
# ---------------------------------------------------------------------------
 
class TerminatorSettings(PropertyGroup):
    active: BoolProperty(
        name="Active",
        default=False,
        description="Enable terminator capture each viewport redraw",
    )
    min_edge_pixels: IntProperty(
        name="Min Edge Pixels",
        default=10,
        min=1,
        description="Ignore terminator detections with fewer than this many pixels (noise filter)",
    )
 
 
# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
 
class TERM_OT_start(Operator):
    bl_idname  = "terminator.start"
    bl_label   = "Start Capture"
    bl_description = "Register POST_VIEW handler — terminator captured each redraw"
 
    def execute(self, context):
        context.scene.terminator_settings.active = True
        # Force a redraw so the handler fires immediately
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        self.report({'INFO'}, "Terminator capture active.")
        return {'FINISHED'}
 
 
class TERM_OT_stop(Operator):
    bl_idname  = "terminator.stop"
    bl_label   = "Stop Capture"
    bl_description = "Stop updating the terminator point cloud"
 
    def execute(self, context):
        global vpbake_terminator_points
        context.scene.terminator_settings.active = False
        vpbake_terminator_points = None
        self.report({'INFO'}, "Terminator capture stopped.")
        return {'FINISHED'}
 
 
# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
 
class TERM_PT_panel(Panel):
    bl_label       = "Terminator"
    bl_idname      = "TERM_PT_panel"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "Terminator"
 
    def draw(self, context):
        layout   = context.layout
        settings = context.scene.terminator_settings
        obj      = context.active_object
 
        # Object status
        col = layout.column(align=True)
        if obj and obj.type == 'MESH':
            col.label(text=obj.name, icon='MESH_DATA')
        else:
            col.label(text="Select a mesh", icon='ERROR')
 
        layout.separator()
        layout.prop(settings, "min_edge_pixels")
        layout.separator()
 
        # Start / stop
        if not settings.active:
            layout.operator("terminator.start", icon='PLAY')
        else:
            layout.operator("terminator.stop", icon='PAUSE')
            # Live readout
            pts = vpbake_terminator_points
            if pts is not None:
                layout.label(text=f"Points this frame: {len(pts)}", icon='PARTICLE_POINT')
            else:
                layout.label(text="No terminator detected", icon='INFO')
 
        layout.separator()
        layout.label(text="Output global:", icon='SCRIPT')
        layout.label(text="  vpbake_terminator_points")
        layout.label(text="  shape (N, 3) float32 world space")
 
 
# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
 
classes = (
    TerminatorSettings,
    TERM_OT_start,
    TERM_OT_stop,
    TERM_PT_panel,
)

# def register():
#     global _mask_shader, _wpos_shader, _handler_ref

#     for cls in classes:
#         bpy.utils.register_class(cls)

#     bpy.types.Scene.terminator_settings = PointerProperty(type=TerminatorSettings)

#     # Compile shaders once
#     _mask_shader = gpu.types.GPUShader(_MASK_VERT, _MASK_FRAG)
#     _wpos_shader = gpu.types.GPUShader(_WPOS_VERT, _WPOS_FRAG)

#     # Register persistent draw handler
#     _handler_ref = bpy.types.SpaceView3D.draw_handler_add(
#         _terminator_draw_handler,
#         (),
#         'WINDOW',
#         'POST_VIEW',
#     )
#     print("[Terminator] Handler registered.")


# def unregister():
#     global _mask_shader, _wpos_shader, _handler_ref, vpbake_terminator_points

#     if _handler_ref is not None:
#         bpy.types.SpaceView3D.draw_handler_remove(_handler_ref, 'WINDOW')
#         _handler_ref = None

#     _mask_shader = None
#     _wpos_shader = None
#     vpbake_terminator_points = None

#     for cls in reversed(classes):
#         bpy.utils.unregister_class(cls)

#     del bpy.types.Scene.terminator_settings
#     print("[Terminator] Unregistered.")


# if __name__ == "__main__":
#     register()
    

def register_block():

    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    # Register all block classes & components
    block_module = get_self_block_module(block_manager_wrapper = Wrapper_Block_Management) # returns this __init__.py file
    Wrapper_Block_Management.create_instance(
        block_module = block_module,
        block_bpy_types_classes = classes,
    )
    
    global _mask_shader, _wpos_shader, _handler_ref
   
    bpy.types.Scene.terminator_settings = PointerProperty(type=TerminatorSettings)
    # Compile shaders once
    _mask_shader = gpu.types.GPUShader(_MASK_VERT, _MASK_FRAG)
    _wpos_shader = gpu.types.GPUShader(_WPOS_VERT, _WPOS_FRAG)
    # Register persistent draw handler
    _handler_ref = bpy.types.SpaceView3D.draw_handler_add(
        _terminator_draw_handler,
        (),
        'WINDOW',
        'POST_VIEW',
    )
    print("[Terminator] Handler registered.")

    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(_BLOCK_ID)
    
    global _mask_shader, _wpos_shader, _handler_ref, vpbake_terminator_points
    if _handler_ref is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler_ref, 'WINDOW')
        _handler_ref = None
    _mask_shader = None
    _wpos_shader = None
    vpbake_terminator_points = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.terminator_settings
    print("[Terminator] Unregistered.")

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")


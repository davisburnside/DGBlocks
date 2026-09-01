

import sys
import random
import math
import numpy as np
import bpy

from .. import block_core 
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from .common_declarations import Block_RTC_Members
from .feature_shader_manager import Wrapper_Shader_Manager
from .data_structures import Shader_Declaration
from .BL_drawing_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Shader_Types
from .animations.engine import get_timer_definitions_from_animations
from .helpers import set_draw_geometry_occluded
from .builtin_shaders_and_effects.custom_shader_billboard2D import Billboard_Shader, _billboard_uid_for_image
from .builtin_shaders_and_effects.custom_shader_polyline_dash import Polyline_Dash_Shader
from .builtin_shaders_and_effects.custom_shader_polyline_annotated import Polyline_Annotated_Shader
from .builtin_shaders_and_effects.custom_shader_textbox_demo import Textbox_Demo_Shader
from .builtin_shaders_and_effects.custom_shader_stripe import Stripe_Shader
from .builtin_shaders_and_effects.demo_props import (
    _EXAMPLE_ANNOTATED_UID,
    DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_TEXTBOX, DEMO_ID_STRIPE, DEMO_ID_REGION_BOUNDS,
    DEMO_ID_ANNOTATED,
    ATTR_DASHED_PHASE, ATTR_DASHED_COUNT, ATTR_STRIPE_PHASE,
    _EXAMPLE_LINEDASH_UID, _EXAMPLE_TEXTBOX_UID, _EXAMPLE_STRIPE_UID,
    _create_region_boundary_shader_declarations,
    _polyline_from_ring, _radial_ring,
    _resolve_demo_shader_uid, _activate_demo_animation, ensure_demo_rows,
    ensure_default_textbox_lines,
    get_demo_row, demo_is_animatable,
)


def _demo_shown(props, demo_id):
    """True when the demo's common settings row has its show_shader (eye) toggle on."""
    row = get_demo_row(props, demo_id)
    return row is not None and row.show_shader


# Called from self
def _hook_get_shader_declarations():

    props = bpy.context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    shader_defs = []

    image = debug_props.show_img_2Dbillboard
    if _demo_shown(props, DEMO_ID_BILLBOARD) and image is not None and debug_props.billboard_count > 0:
        shader_defs.append(Billboard_Shader.create_declaration(image)) # More dynamic than the other Declarations, requires an Image 

    if _demo_shown(props, DEMO_ID_DASHED):
        shader_defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_LINEDASH_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_VIEW,
                custom_shader_class=Polyline_Dash_Shader,
            )
        )

    if _demo_shown(props, DEMO_ID_TEXTBOX) and len(props.textbox_lines) > 0:
        shader_defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_TEXTBOX_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_PIXEL,
                custom_shader_class=Textbox_Demo_Shader,
            )
        )

    # Stripe holdout: 3D TRIs rendered at viewport points, but with a screen-locked 2D stripe
    # pattern computed in the fragment shader from window-space pixels (gl_FragCoord).
    if _demo_shown(props, DEMO_ID_STRIPE):
        shader_defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_STRIPE_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_VIEW,
                custom_shader_class=Stripe_Shader,
            )
        )
    
    # Annotated smooth-color polyline demo with z-boost and arrowheads
    if _demo_shown(props, DEMO_ID_ANNOTATED):
        shader_defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_ANNOTATED_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_VIEW,
                custom_shader_class=Polyline_Annotated_Shader,
                builtin_shader_before_draw= set_draw_geometry_occluded
            )
        )

    if _demo_shown(props, DEMO_ID_REGION_BOUNDS):
        shader_defs.extend(_create_region_boundary_shader_declarations(props))

    # Example demo shaders are independent of viewport debugging.
    return shader_defs

# Called from self
def _hook_before_first_draw():
    """
    Push (re)generated geometry / parameters into the live example shaders. Runs on every
    rebuild — so every example-property edit re-randomizes the billboards and re-applies the
    dashed-line and textbox parameters.
    """
    props = bpy.context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props

    # --- Billboards: random location / size / color around the origin ---
    image = debug_props.show_img_2Dbillboard
    if image is not None and debug_props.billboard_count > 0:
        shader = Wrapper_Shader_Manager.get_shader(_billboard_uid_for_image(image))
        if shader is not None:
            count = debug_props.billboard_count
            loc_spread = debug_props.billboard_location_spread
            size = debug_props.billboard_default_size
            size_spread = debug_props.billboard_size_spread
            color_spread = debug_props.billboard_color_spread

            points = []
            colors = []
            sizes = []
            for _ in range(count):
                # Default location is always (0, 0, 0); location_spread jitters around it.
                points.append((
                    random.uniform(-loc_spread, loc_spread),
                    random.uniform(-loc_spread, loc_spread),
                    random.uniform(-loc_spread, loc_spread),
                ))
                sizes.append(max(0.0, size + random.uniform(-size_spread, size_spread)))
                # color_spread=0 -> all white; ->1 -> fully random RGB. Alpha stays opaque.
                base = 1.0 - color_spread
                colors.append((
                    base + random.uniform(0.0, color_spread),
                    base + random.uniform(0.0, color_spread),
                    base + random.uniform(0.0, color_spread),
                    1.0,
                ))
            shader.set_points(points)
            shader.set_colors(colors)
            shader.set_billboard_sizes(sizes)

    # --- Dashed polyline: a base square loop, PLUS N radially-symmetric ring clusters ---
    if _demo_shown(props, DEMO_ID_DASHED):
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_LINEDASH_UID)
        if shader is not None:
            dash_row = get_demo_row(props, DEMO_ID_DASHED)

            # Base shape: a square loop on the XY plane, as segment endpoint PAIRS.
            corners = [(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)]
            polyline = _polyline_from_ring(corners)

            # count disjointed ring clusters, each an empty (n+1)-vert radially
            # symmetric polygon, stacked at increasing Z above the base shape. This proves the
            # polyline shader handles disjointed line clusters within a single batch.
            count_attr = dash_row.get_attr(ATTR_DASHED_COUNT) if dash_row else None
            cluster_count = count_attr.get_value() if count_attr else 0
            n_sides = len(corners)  # radial symmetry uses the base shape's vertex count
            for c in range(cluster_count):
                z = (c + 1) * 1.5
                n_sides += 1
                ring = _radial_ring(radius=2.0, n_sides=n_sides, z=z)
                polyline.extend(_polyline_from_ring(ring))
            shader.set_polyline(polyline)
            shader.set_line_thickness(debug_props.linedash_thickness)
            shader.set_dash_width(debug_props.linedash_dash_width)
            shader.set_dash_ratio(debug_props.linedash_dash_ratio)
            shader.set_dash_colors(
                tuple(debug_props.linedash_color),
                tuple(debug_props.linedash_color2),
            )
            phase_attr = dash_row.get_attr(ATTR_DASHED_PHASE) if dash_row else None
            if phase_attr is not None:
                shader.set_phase(phase_attr.get_value())

    # --- Text boxes: user-authored lines + spawn point ---
    if props.textbox_lines:
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_TEXTBOX_UID)
        if shader is not None:
            bg_top = tuple(debug_props.textbox_bg_color_top) if debug_props.textbox_bg_enabled else None
            bg_bottom = tuple(debug_props.textbox_bg_color_bottom) if debug_props.textbox_bg_enabled else None

            shader.clear_lines()
            for line in props.textbox_lines:
                shader.add_line(
                    line.text,
                    font_size=line.font_size,
                    alignment=line.alignment,
                    max_char_count=line.max_char_count,
                    min_padding=line.get_padding_value(),
                    text_color=tuple(line.text_color),
                    outline_enabled=line.outline_enabled,
                    outline_color=tuple(line.outline_color),
                    outline_spread=int(line.outline_spread),
                    outline_offset=(line.outline_offset_x, line.outline_offset_y),
                    bg_color_top=bg_top,
                    bg_color_bottom=bg_bottom,
                )
            shader.set_spawn_point(debug_props.textbox_spawn_point)
            shader.set_textbox_offsets(debug_props.textbox_x_offset, debug_props.textbox_y_offset)

    # --- Stripe holdout: a unit cube of TRIs whose stripe pattern stays screen-locked ---
    if _demo_shown(props, DEMO_ID_STRIPE):
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_STRIPE_UID)
        if shader is not None:
            row = get_demo_row(props, DEMO_ID_STRIPE)
            scale = row.scale if row is not None else 1.0
            corners = [
                (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                (-1, -1,  1), (1, -1,  1), (1, 1,  1), (-1, 1,  1),
            ]
            points = np.asarray(corners, dtype=np.float32) * np.float32(scale)
            indices = [
                (0, 1, 2), (0, 2, 3),   # back
                (4, 6, 5), (4, 7, 6),   # front
                (0, 4, 5), (0, 5, 1),   # bottom
                (2, 6, 7), (2, 7, 3),   # top
                (0, 3, 7), (0, 7, 4),   # left
                (1, 5, 6), (1, 6, 2),   # right
            ]
            shader.set_points(points)
            shader.set_indices(indices)
            shader.set_stripe_angle(math.radians(debug_props.stripe_angle))
            shader.set_stripe_width(debug_props.stripe_width)
            shader.set_stripe_colors(
                tuple(debug_props.stripe_color1),
                tuple(debug_props.stripe_color2),
            )
            phase_attr = row.get_attr(ATTR_STRIPE_PHASE) if row is not None else None
            if phase_attr is not None:
                shader.set_phase(phase_attr.get_value())

    # --- Annotated smooth-color polyline: 3 random clusters, 2-8 points each ---
    if _demo_shown(props, DEMO_ID_ANNOTATED):
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_ANNOTATED_UID)
        if shader is not None:
            ann_row = get_demo_row(props, DEMO_ID_ANNOTATED)
            ann_scale = ann_row.scale if ann_row is not None else 1.0

            clusters_points = []
            clusters_colors = []
            for _c in range(3):
                n = random.randint(2, 8)
                cluster_pts = [
                    (random.uniform(-3.0, 3.0) * ann_scale,
                     random.uniform(-3.0, 3.0) * ann_scale,
                     random.uniform(-2.0, 2.0) * ann_scale)
                    for _ in range(n)
                ]
                cluster_cols = [
                    (random.uniform(0.0, 1.0), random.uniform(0.0, 1.0),
                     random.uniform(0.0, 1.0), 1.0)
                    for _ in range(n)
                ]
                clusters_points.append(cluster_pts)
                clusters_colors.append(cluster_cols)

            shader.set_polyline_clusters(clusters_points, clusters_colors)
            shader.set_line_thickness(debug_props.annotated_line_thickness)
            shader.set_viewport_z_boost(debug_props.annotated_z_boost)
            shader.set_arrow_length_px(debug_props.annotated_arrow_length_px)
            shader.set_arrow_angle(debug_props.annotated_arrow_angle)

    # Re-attach demo animations for every animating demo. Called from hook_before_first_draw so demo animations survive a rebuild (undo/redo, eye toggles, prop edits
    for row in props.demo_settings:
        if not row.is_animating or not demo_is_animatable(row.demo_id):
            continue
        uid = _resolve_demo_shader_uid(row.demo_id, props)
        if uid is None:
            continue
        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
        if shader is not None:
            _activate_demo_animation(row.demo_id, row, shader)

# Called from block_modal_events
def _hook_get_timer_definitions():
    """
    Subscribed to block_timers' hook_get_timer_definitions.
    Returns one Timer_Definition per unique framerate across all shader-owned
    animations. block_timers creates one bpy.app.timer per definition returned here.
    """
    return get_timer_definitions_from_animations()

# Called from block_core
def _hook_post_startup():
    props = bpy.context.scene.dgblocks_onscreen_drawing_props
    ensure_demo_rows(props)
    ensure_default_textbox_lines(props)


import sys
import random
import bpy

# --------------------------------------------------------------
# Addon-level imports
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events
from ...addon_config.static_settings import Documentation_URLs, addon_title

# --------------------------------------------------------------
# Inter-block imports
from .. import block_core  # noqa: F401 — ensures block_core is loaded first
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_helpers.constants import Core_Block_Loggers, Core_Runtime_Cache_Members # type: ignore
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist, ui_draw_subpanel

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .feature_shader_manager import Wrapper_Shader_Manager
from .data_structures import Shader_Declaration
from .BL_drawing_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Builtin_Shader_Names, Shader_Types
from .helpers import _clear_all_shaders, _rebuild_all_shaders
from .animations.engine import get_timer_definitions_from_animations
from .builtin_shaders_and_effects.custom_shader_billboard2D import Billboard_Shader
from .builtin_shaders_and_effects.custom_shader_polyline_dash import Polyline_Dash_Shader
from .builtin_shaders_and_effects.custom_shader_textbox_demo import Textbox_Demo_Shader
from .demo_shader_settings import (
    DGBLOCKS_PG_Demo_Shader_Attribute,
    DGBLOCKS_PG_Demo_Shader_Common,
    DGBLOCKS_PG_Debug_Shader_Region_Toggles,
    DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_TEXTBOX,
    ATTR_DASHED_PHASE, ATTR_DASHED_COUNT,
    DEBUG_DRAW_REGION_TYPES, _EXAMPLE_LINEDASH_UID, _EXAMPLE_TEXTBOX_UID,
    _billboard_uid_for_image, ensure_demo_rows, get_demo_row,
    region_type_is_enabled, reapply_active_demo_animations,
    demo_is_animatable, demo_label,
)

cache_key_shaders = Block_RTC_Members.SHADERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS
cache_key_shared_uilist_declarations = Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS

# Optional foreign RTC member owned by block_modal_events (NOT a dependency). Read defensively
# via get_cache(): it returns None when that block is absent or its modal router is idle. We
# keep the key as a named constant rather than importing the foreign enum, since importing a
# non-dependency block is forbidden.
_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE = "USER_INPUT_CAPTURE"

# ==============================================================================================================================
# BL PROPERTY UPDATE CALLBACKS

def _cb_enable_drawing_changed(self, context):
    """
    Fired when the enable_drawing scene property changes.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.SHADERS):
        return

    event = Enum_Sync_Events.PROPERTY_UPDATE
    if context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
        _rebuild_all_shaders(event)
    else:
        _clear_all_shaders()


def _cb_example_shader_props_changed(self, context):
    """
    Fired when any of the example-shader properties change (viewport debugging toggle, the
    billboard image/count/spreads, the linedash controls, or the textbox count).

    While drawing is enabled, this rebuilds the whole shader set. Because a rebuild re-fires
    both hook_get_shader_definitions AND hook_before_first_draw, every property edit both
    re-declares the affected example shaders and re-generates their (randomized) geometry —
    which is exactly the "re-randomize on every update" behaviour the billboard example wants.
    """
    if context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
        _rebuild_all_shaders(Enum_Sync_Events.PROPERTY_UPDATE)

# ==============================================================================================================================
# BL PROPERTY GROUPS

class DGBLOCKS_PG_Debug_Shader_Example_Props(bpy.types.PropertyGroup):

    # 2D image billboard example
    show_img_2Dbillboard: bpy.props.PointerProperty(name="Billboard Image", type=bpy.types.Image, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_count: bpy.props.IntProperty(name="Count", default=12, min=0, max=500, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_default_size: bpy.props.FloatProperty(name="Size", default=0.5, min=0.0, soft_max=5.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_size_spread: bpy.props.FloatProperty(name="Size Spread", default=0.25, min=0.0, soft_max=5.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_location_spread: bpy.props.FloatProperty(name="Location Spread", default=3.0, min=0.0, soft_max=50.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_color_spread: bpy.props.FloatProperty(name="Color Spread", default=1.0, min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore

    # Dashed polyline (Metal-safe thickness) example
    show_linedash: bpy.props.BoolProperty(name="Dashed Polyline", update=_cb_example_shader_props_changed)  # type: ignore
    linedash_thickness: bpy.props.FloatProperty(name="Line Thickness", default=6.0, min=1.0, soft_max=40.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_dash_width: bpy.props.FloatProperty(name="Dash Width", default=20.0, min=1.0, soft_max=200.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_dash_ratio: bpy.props.FloatProperty(name="Dash Gap Ratio", default=0.5, min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_color: bpy.props.FloatVectorProperty(name="Dash Color", subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_color2: bpy.props.FloatVectorProperty(name="Gap Color", subtype="COLOR", size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore

    # Multi Text box example
    show_textbox_count: bpy.props.IntProperty(name="Text Boxes", default=0, min=0, max=20, update=_cb_example_shader_props_changed)  # type: ignore
    textbox_spawn_point: bpy.props.EnumProperty(  # type: ignore
        name="Spawn Point",
        description="Which region corner the text boxes anchor to (or the mouse, if a block_modal_event instance is active)",
        items=[
            ("TOP_LEFT",     "Top Left",     ""),
            ("TOP_RIGHT",    "Top Right",    ""),
            ("BOTTOM_LEFT",  "Bottom Left",  ""),
            ("BOTTOM_RIGHT", "Bottom Right", ""),
            ("MOUSE",        "At Mouse",     ""),
        ],
        default="TOP_LEFT",
        update=_cb_example_shader_props_changed,
    )

    # Viewport region debugging
    # Region_toggles holds one checkbox per drawable Draw_Region_Type; unchecking one disables that border type for all areas.
    draw_region_boundaries: bpy.props.BoolProperty(name="Draw Region Boundaries", update = _cb_example_shader_props_changed)  # type: ignore
    region_toggles: bpy.props.PointerProperty(type=DGBLOCKS_PG_Debug_Shader_Region_Toggles)  # type: ignore

class DGBLOCKS_PG_Shader_Mirror_Row(bpy.types.PropertyGroup):
    """
    One persistent row per live Shader_Instance.
    Stores only the uid key and read-only draw-location display fields
    (space / region / phase). This exists purely to back a UIList; it never drives RTC.

    is_enabled is RTC-only (on Shader_Instance) and is toggled through
    DGBLOCKS_OT_Toggle_Shader, which does not touch the undo stack.
    Populated and maintained by Wrapper_Shader_Manager._update_BL_with_mirrored_RTC_data().
    """
    shader_uid:  bpy.props.StringProperty()  # type: ignore
    draw_space:  bpy.props.StringProperty()  # type: ignore
    draw_region: bpy.props.StringProperty()  # type: ignore
    draw_phase:  bpy.props.StringProperty()  # type: ignore


class DGBLOCKS_PG_Onscreen_Drawing_Props(bpy.types.PropertyGroup):
    """
    Scene-level property group for block_onscreen_drawing.
    Stored on bpy.types.Scene.dgblocks_onscreen_drawing_props.
    """
    enable_drawing: bpy.props.BoolProperty(name="Enable Drawing", default=False, update=_cb_enable_drawing_changed) # type: ignore

    debug_props: bpy.props.PointerProperty(type = DGBLOCKS_PG_Debug_Shader_Example_Props) # type: ignore
    debug_show_examples: bpy.props.BoolProperty(name="Show Shader Examples", default=False) # type: ignore
    # Unified per-demo settings (task 4): one DGBLOCKS_PG_Demo_Shader_Common row per demo,
    # keyed by demo_id, each carrying show_shader / is_animating / animation_fps / scale plus a
    # nested CollectionProperty of shader-unique attributes. Seeded by ensure_demo_rows().
    demo_settings: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Demo_Shader_Common)  # type: ignore
    shader_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

_DEBUG_BORDER_COLOR = (1.0, 0.0, 1.0, 1.0)          # Magenta — normal
_DEBUG_BORDER_COLOR_HOVER = (0.0, 1.0, 0.2, 1.0)     # Green — mouse is over this region


def _mouse_capture_available() -> bool:
    """
    True when the optional foreign USER_INPUT_CAPTURE RTC member reports a live mouse position
    (task 8). Used to enable/disable the text-box 'At Mouse' spawn option. Never raises: returns
    False when block_modal_events is absent or its modal router is idle.
    """
    capture = Wrapper_Runtime_Cache.get_cache(_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE)
    if capture is None:
        return False
    mx = getattr(capture, "mouse_x", None)
    my = getattr(capture, "mouse_y", None)
    return bool(mx) and bool(my)


def _mouse_is_over_current_region() -> bool:
    """
    True if the optional foreign USER_INPUT_CAPTURE RTC member reports a mouse position
    that lies inside the region currently being drawn. Returns False (never raises) when
    the member is absent, idle, or the mouse is in a different window.
    """
    capture = Wrapper_Runtime_Cache.get_cache(_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE)
    if capture is None:
        return False

    mouse_x = getattr(capture, "mouse_x", None)
    mouse_y = getattr(capture, "mouse_y", None)
    # Fields are None when idle; the request specifies both must be > 0.
    if not mouse_x or not mouse_y or mouse_x <= 0 or mouse_y <= 0:
        return False

    # A mouse can jump between Blender windows; disambiguate by window pointer when known.
    window = bpy.context.window
    capture_window_id = getattr(capture, "window_id", None)
    if capture_window_id is not None and window is not None:
        if capture_window_id != window.as_pointer():
            return False

    region = bpy.context.region
    if region is None:
        return False

    # region.x / region.y are window-space; mouse_x / mouse_y are window-space too.
    return (region.x <= mouse_x <= region.x + region.width
            and region.y <= mouse_y <= region.y + region.height)


def _debug_region_before_draw(shader_instance):
    region = bpy.context.region
    if region is None:
        return

    w, h = region.width, region.height
    last_dim = getattr(shader_instance, "_last_debug_dim", None)

    # Update points if dimensions have changed
    if last_dim != (w, h):
        points = [
            (1, 1), (w - 2, 1),
            (w - 2, 1), (w - 2, h - 2),
            (w - 2, h - 2), (1, h - 2),
            (1, h - 2), (1, 1)
        ]
        shader_instance.set_points(points)
        shader_instance._last_debug_dim = (w, h)

    color = _DEBUG_BORDER_COLOR_HOVER if _mouse_is_over_current_region() else _DEBUG_BORDER_COLOR
    shader_instance.set_uniform("color", color)


def hook_get_shader_definitions():
    """
    Adds a debug bounding box for every region of every area of every open window, when
    draw_region_boundaries is checked.

    Rather than hardcoding a space/region list, we walk the live window manager so that only
    real, currently-valid (space, region) combinations are declared — this covers all editor
    types across all windows and picks up regions like TOOL_HEADER automatically. Each unique
    (space_type, region_type) yields one Shader_Declaration; the single draw handler Blender
    registers per space type then draws that border in every matching area/window.
    """

    props = bpy.context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props

    returned_shader_definitions = []

    # Region-border debug shaders are governed ONLY by draw_region_boundaries (task 7:
    # it must not gate the example shaders — those have their own per-demo show_shader flags).
    if debug_props.draw_region_boundaries:
        returned_shader_definitions.extend(_get_debug_border_definitions(props))

    # Example demo shaders are independent of viewport debugging.
    returned_shader_definitions.extend(_get_example_shader_definitions(props))
    return returned_shader_definitions


def _get_debug_border_definitions(props):
    """
    One border Shader_Declaration per unique (space, region) across all open windows, skipping
    any region type whose checkbox is unchecked (task 7). Walking the live window manager keeps
    us to real, currently-valid combos and picks up regions like TOOL_HEADER automatically.
    """
    region_toggles = props.debug_props.region_toggles
    seen_combos: set = set()
    defs = []

    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            # Map Blender's area.type / region.type strings onto our enums. Skip anything we
            # don't model (both enums use uppercase name==value members).
            try:
                space = Draw_Space_Types[area.type]
            except KeyError:
                continue
            for region in area.regions:
                try:
                    region_enum = Draw_Region_Type[region.type]
                except KeyError:
                    continue
                # Per-region-type toggle (task 7): unchecking disables it for all areas.
                if not region_type_is_enabled(region_toggles, region_enum.name):
                    continue
                # Regions with zero size (collapsed) can't host a meaningful border.
                if region.width <= 0 or region.height <= 0:
                    continue
                combo = (space, region_enum)
                if combo in seen_combos:
                    continue
                seen_combos.add(combo)
                defs.append(
                    Shader_Declaration(
                        shader_uid=f"DEBUG_REGION_BORDER_{space.name}_{region_enum.value}",
                        shader_type=Shader_Types.LINES,
                        space=space,
                        region=region_enum,
                        phase=Draw_Phase_type.POST_PIXEL,
                        builtin_shader_name=Builtin_Shader_Names.UNIFORM_COLOR,
                        builtin_shader_before_draw=_debug_region_before_draw,
                    )
                )

    return defs


def _get_example_shader_definitions(props):
    """
    Declarations for the three example shaders (billboard / dashed polyline / text boxes).

    All three are custom Shader_Instance subclasses drawn in VIEW_3D/WINDOW. Each is declared
    only while its per-demo show_shader eye toggle is on AND its controlling property indicates
    it should be visible — a hidden demo, a missing billboard image, an unchecked dash toggle,
    or a zero textbox count simply omits the declaration (how "disabled" is expressed to the
    pull-based manager). Toggling show_shader repolls, so hiding a demo removes its shader.
    """
    defs = []
    debug_props = props.debug_props

    # Ensure the per-demo rows exist even if the panel hasn't drawn yet (e.g. repoll on load).
    ensure_demo_rows(props)

    def _demo_shown(demo_id):
        row = get_demo_row(props, demo_id)
        return row is not None and row.show_shader

    image = debug_props.show_img_2Dbillboard
    if _demo_shown(DEMO_ID_BILLBOARD) and image is not None and debug_props.billboard_count > 0:
        defs.append(
            Shader_Declaration(
                shader_uid=_billboard_uid_for_image(image),
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_VIEW,
                custom_shader_class=Billboard_Shader,
                custom_shader_kwargs={"image_name": image.name},
            )
        )

    if _demo_shown(DEMO_ID_DASHED) and debug_props.show_linedash:
        defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_LINEDASH_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_VIEW,
                custom_shader_class=Polyline_Dash_Shader,
            )
        )

    if _demo_shown(DEMO_ID_TEXTBOX) and debug_props.show_textbox_count > 0:
        defs.append(
            Shader_Declaration(
                shader_uid=_EXAMPLE_TEXTBOX_UID,
                shader_type=Shader_Types.TRIS,
                space=Draw_Space_Types.VIEW_3D,
                region=Draw_Region_Type.WINDOW,
                phase=Draw_Phase_type.POST_PIXEL,
                custom_shader_class=Textbox_Demo_Shader,
            )
        )

    return defs


def hook_before_first_draw():
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
    if debug_props.show_linedash:
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_LINEDASH_UID)
        if shader is not None:
            dash_row = get_demo_row(props, DEMO_ID_DASHED)

            # Base shape: a square loop on the XY plane, as segment endpoint PAIRS.
            corners = [(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)]
            polyline = _polyline_from_ring(corners)

            # Task 2: `count` disjointed ring clusters, each an empty (n+1)-vert radially
            # symmetric polygon, stacked at increasing Z above the base shape. This proves the
            # polyline shader handles disjointed line clusters within a single batch.
            count_attr = dash_row.get_attr(ATTR_DASHED_COUNT) if dash_row else None
            cluster_count = count_attr.get_value() if count_attr else 0
            n_sides = len(corners)  # radial symmetry uses the base shape's vertex count
            for c in range(cluster_count):
                z = (c + 1) * 1.5
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
            # Task 2: phase (0..1, hard-capped in set_phase) from the demo's unique attribute.
            phase_attr = dash_row.get_attr(ATTR_DASHED_PHASE) if dash_row else None
            if phase_attr is not None:
                shader.set_phase(phase_attr.get_value())

    # --- Text boxes (task 8): count + spawn point ---
    if debug_props.show_textbox_count > 0:
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_TEXTBOX_UID)
        if shader is not None:
            shader.set_textbox_count(debug_props.show_textbox_count)
            shader.set_spawn_point(debug_props.textbox_spawn_point)

    # Re-apply any active demo animations AFTER geometry is pushed, so start_state=None
    # auto-captures real values (task 3). RTC-only; never writes Blender property values.
    reapply_active_demo_animations(props)


def _polyline_from_ring(ring):
    """Convert a closed ring of points into a flat list of segment endpoint PAIRS."""
    out = []
    n = len(ring)
    for i in range(n):
        out.append(ring[i])
        out.append(ring[(i + 1) % n])
    return out


def _radial_ring(radius, n_sides, z):
    """A radially-symmetric closed polygon of n_sides vertices at height z (XY plane)."""
    import math
    return [
        (radius * math.cos(2 * math.pi * i / n_sides),
         radius * math.sin(2 * math.pi * i / n_sides),
         z)
        for i in range(n_sides)
    ]


def hook_get_timer_definitions():
    """
    Subscribed to block_timers' hook_get_timer_definitions.
    Returns one Timer_Definition per unique framerate across all shader-owned
    animations. block_timers creates one bpy.app.timer per definition returned here.
    """
    return get_timer_definitions_from_animations()

def hook_post_startup():
    ensure_demo_rows(bpy.context.scene.dgblocks_onscreen_drawing_props)

# ==============================================================================================================================
# UI 

class DGBLOCKS_OT_Toggle_Shader(bpy.types.Operator):
    """Toggle a shader's visibility. is_enabled is RTC-only, so this must NOT enter the undo stack."""
    bl_idname = "dgblocks.toggle_shader"
    bl_label = "Toggle Shader"
    # INTERNAL hides it from search; omitting REGISTER/UNDO keeps it off the undo stack.
    bl_options = {"INTERNAL"}

    shader_uid: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        shader = Wrapper_Shader_Manager.get_shader(self.shader_uid)
        if shader is None:
            self.report({"WARNING"}, f"Shader '{self.shader_uid}' not found")
            return {"CANCELLED"}
        shader.is_enabled = not shader.is_enabled
        # Nudge the viewport so the border color / visibility change is drawn immediately.
        if context.area is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


class DGBLOCKS_OT_Toggle_Demo_Animation(bpy.types.Operator):
    """
    Toggle a demo shader's infinite-loop animation (task 3). Flips the demo row's is_animating
    BoolProperty, whose update callback applies/cancels the animation on the RTC Shader_Instance.
    RTC-only — no Blender shader values are written, so this stays off the undo stack.
    """
    bl_idname = "dgblocks.toggle_demo_animation"
    bl_label = "Toggle Demo Animation"
    bl_options = {"INTERNAL"}

    demo_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        props = context.scene.dgblocks_onscreen_drawing_props
        row = get_demo_row(props, self.demo_id)
        if row is None:
            self.report({"WARNING"}, f"Demo '{self.demo_id}' not found")
            return {"CANCELLED"}
        # Flipping is_animating fires its update callback (apply/cancel the animation).
        row.is_animating = not row.is_animating
        if context.area is not None:
            context.area.tag_redraw()
        return {"FINISHED"}


def _ui_draw_demo_header_eye(header_row, context, demo_id):
    """
    Draw the 'eye' existence toggle on a demo subpanel header (task 5). Bound to the demo's
    show_shader prop; toggling it fires cb_rebuild_shaders -> repoll, so a hidden demo is
    implicitly removed from the shader list.
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    row = get_demo_row(props, demo_id)
    if row is None:
        return
    eye_icon = "HIDE_OFF" if row.show_shader else "HIDE_ON"
    header_row.prop(row, "show_shader", text="", icon=eye_icon, emboss=False)


def _ui_draw_demo_grid(container, data, prop_names, columns=0):
    """Width-sensitive grid of props (task 6). columns=0 = auto-flow to available width."""
    grid = container.grid_flow(row_major=True, columns=columns, even_columns=True, align=True)
    for name in prop_names:
        grid.prop(data, name)
    return grid


def _ui_draw_demo_animation_controls(container, context, demo_id):
    """
    Shared 'Animate' toggle + FPS slider (tasks 3/4). Only shown for animatable demos. While
    animating, the demo's other props are drawn read-only (handled by the caller).
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    row_data = get_demo_row(props, demo_id)
    if row_data is None or not demo_is_animatable(demo_id):
        return
    anim_row = container.row(align=True)
    op = anim_row.operator(
        DGBLOCKS_OT_Toggle_Demo_Animation.bl_idname,
        text="Stop Animation" if row_data.is_animating else "Animate",
        icon="PAUSE" if row_data.is_animating else "PLAY",
        depress=row_data.is_animating,
    )
    op.demo_id = demo_id
    if row_data.is_animating:
        # Task 4: FPS slider (capped at 60 by the property definition).
        container.prop(row_data, "animation_fps", slider=True)

def _ui_draw_billboard_body(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_BILLBOARD)
    animating = bool(row and row.is_animating)

    container.prop(debug_props, "show_img_2Dbillboard")
    sub = container.column()
    # Read-only while animating (task 3) or when no image is set.
    sub.enabled = (debug_props.show_img_2Dbillboard is not None) and not animating
    _ui_draw_demo_grid(sub, debug_props, [
        "billboard_count", "billboard_default_size", "billboard_size_spread",
        "billboard_location_spread", "billboard_color_spread",
    ])
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_BILLBOARD)


def _ui_draw_dashed_body(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    row = get_demo_row(props, DEMO_ID_DASHED)
    animating = bool(row and row.is_animating)

    container.prop(debug_props, "show_linedash", toggle=True)
    sub = container.column()
    sub.enabled = debug_props.show_linedash and not animating
    _ui_draw_demo_grid(sub, debug_props, [
        "linedash_thickness", "linedash_dash_width", "linedash_dash_ratio",
        "linedash_color", "linedash_color2",
    ])
    # Task 2: unique attributes (phase 0..1, cluster count) drawn generically from the row.
    if row is not None:
        attr_grid = sub.grid_flow(row_major=True, columns=0, even_columns=True, align=True)
        for attr in row.unique_attributes:
            value_field = "int_value" if attr.value_kind == "INT" else "float_value"
            attr_grid.prop(attr, value_field, text=attr.display_name)
    _ui_draw_demo_animation_controls(container, context, DEMO_ID_DASHED)


def _ui_draw_textbox_body(context, container):
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props

    container.prop(debug_props, "show_textbox_count")
    # Task 8: spawn-point radio. The MOUSE option needs a live block_modal_event instance.
    container.label(text="Spawn Point:")
    container.prop(debug_props, "textbox_spawn_point", expand=True)
    if not _mouse_capture_available():
        info = container.column()
        info.enabled = False
        info.label(text="'At Mouse' needs an active block_modal_event", icon="INFO")
        info.label(text="instance for mouse/key capture.")


# Maps each demo to (label, icon, body-draw fn) so the panel iterates generically.
_DEMO_SUBPANELS = [
    (DEMO_ID_BILLBOARD, "2D Image Billboard", "IMAGE_DATA", _ui_draw_billboard_body),
    (DEMO_ID_DASHED,    "Dashed Polyline",    "IPO_LINEAR",  _ui_draw_dashed_body),
    (DEMO_ID_TEXTBOX,   "Text Boxes",         "SMALL_CAPS",  _ui_draw_textbox_body),
]


def _ui_draw_viewport_debug_body(context, container):
    """draw_region_boundaries + the per-region-type checkbox grid (task 7)."""
    props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = props.debug_props
    container.prop(debug_props, "draw_region_boundaries", toggle=True)
    region_box = container.column()
    region_box.enabled = debug_props.draw_region_boundaries
    region_box.label(text="Region Types:")
    grid = region_box.grid_flow(row_major=True, columns=0, even_columns=True, align=True)
    for rt in DEBUG_DRAW_REGION_TYPES:
        grid.prop(props.debug_props.region_toggles, f"region_{rt}")


def _ui_draw_shader_examples_subpanel(context, container):
    """
    Contents of the 'Shader Examples' subpanel: one nested sub-subpanel per demo shader (task 5),
    each with an eye existence toggle on its header, plus the viewport-debug sub-subpanel.
    Only enabled while drawing is on.
    """
    drawing_props = context.scene.dgblocks_onscreen_drawing_props

    col = container.column()
    col.enabled = drawing_props.enable_drawing

    for demo_id, label, icon, body_fn in _DEMO_SUBPANELS:
        header, body = ui_draw_subpanel(
            context, col, f"onscreen_demo_{demo_id}", "", body_fn,
        )
        # Header: eye toggle + label + icon.
        _ui_draw_demo_header_eye(header, context, demo_id)
        header.label(text=label, icon=icon)

    # Viewport region debugging as its own sub-subpanel.
    ui_draw_subpanel(
        context, col, "onscreen_viewport_debug", "Viewport Region Debugging",
        _ui_draw_viewport_debug_body,
    )



class DGBLOCKS_PT_Debug_Drawing_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_Debug_Drawing_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title

    
    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout,
            _BLOCK_DECLARATION.block_id,
            block_declaration = _BLOCK_DECLARATION,
        )

    def draw(self, context):
        layout = self.layout
        drawing_props = context.scene.dgblocks_onscreen_drawing_props

        # Idempotently seed the per-demo settings rows (safe to call from draw).
        # ensure_demo_rows(drawing_props)

        # Master enable / disable toggle
        layout.prop(drawing_props, "enable_drawing", toggle=True)

        # Example / debug shaders grouped under a collapsible subpanel. Each demo is now its own
        # nested sub-subpanel with an eye toggle; per-demo animation toggles replace the old
        # "Sample Animations" button.
        ui_draw_subpanel(
            context, layout, "onscreen_shader_examples", "Shader Examples",
            _ui_draw_shader_examples_subpanel,
        )

        if not drawing_props.shader_mirror:
            layout.label(text="No active shaders", icon="INFO")
        else:
            draw_shared_uilist(context, layout, "shader_mirror")

# ==============================================================================================================================
# BLOCK REGISTRATION HELPERS

def register_block_props():
    bpy.types.Scene.dgblocks_onscreen_drawing_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Onscreen_Drawing_Props)


def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_onscreen_drawing_props"):
        del bpy.types.Scene.dgblocks_onscreen_drawing_props

# ==============================================================================================================================
# REQUIRED

_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-onscreen-draw",
    block_dependencies = ["block-core", "block-timers"],
    block_bpy_classes = [
        # Nested PropertyGroups must register before the groups that point to them.
        DGBLOCKS_PG_Demo_Shader_Attribute,
        DGBLOCKS_PG_Demo_Shader_Common,
        DGBLOCKS_PG_Debug_Shader_Region_Toggles,
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Debug_Shader_Example_Props,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_OT_Toggle_Shader,
        DGBLOCKS_OT_Toggle_Demo_Animation,
        DGBLOCKS_PT_Debug_Drawing_Panel,
    ],
    block_feature_wrapper_classes = [Wrapper_Shader_Manager],
    block_hook_sources = Block_Hook_Sources,
    block_RTC_members = Block_RTC_Members,
    block_data_mirrors = Block_Data_Mirrors,
    block_loggers = Block_Loggers,
    block_uilist_configs = Block_UIList_Configs,
    icon = "FILE_3D",
    documentation_url = Documentation_URLs.MY_PLACEHOLDER_URL_2,
)

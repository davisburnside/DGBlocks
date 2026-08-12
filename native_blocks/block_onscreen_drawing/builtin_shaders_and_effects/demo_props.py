"""
Dedicated module for the built-in demo shaders' UI settings and their infinite-loop
demo animations.

WHY THIS MODULE EXISTS
----------------------
The block ships a handful of example shaders (billboard / dashed polyline / text boxes).
Each one now gets:

  * a unified per-demo settings row (DGBLOCKS_PG_Demo_Shader_Common) holding options common
    to ALL shaders (show_shader, is_animating, animation_fps, scale) plus a nested
    CollectionProperty of shader-UNIQUE attributes (DGBLOCKS_PG_Demo_Shader_Attribute), e.g.
    the dashed shader's `phase` and cluster `count`.
  * an optional infinite-loop demo animation that lerps a MIX of things (batch geometry,
    per-vertex colors, the dashed phase) purely on the RTC Shader_Instance — never writing
    back to Blender property values.

All new PropertyGroups and the animation apply/cancel logic live here so `__init__.py`
stays focused on hooks, the panel, and block declaration. New demos only need a new entry
in `_DEMO_DEFS` plus an animation recipe in `_activate_demo_animation`.
"""

import bpy
import numpy as np


# Addon-level imports
from ....addon_helpers.data_structures import Enum_Sync_Events
from ....addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist, ui_draw_subpanel

# Inter-block imports
from ...block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ...block_core.core_features.loggers.feature_wrapper import get_logger
from ...block_timers.feature_timer_manager import Wrapper_Timer_Manager

# Intra-block imports
from ..common_declarations import Block_Loggers, Block_RTC_Members
from ..data_structures import Shader_Declaration
from ..helpers import _mouse_is_over_current_region, _rebuild_all_shaders
from ..animations.constants import ANIM_DATA_TYPE_BATCH, ANIM_LOOP_PING_PONG, ANIM_LOOP_REPEAT
from ..animations.data_structures import Animation_Declaration
from ..animations.engine import suppress_timer_rebuilds
from ..BL_drawing_structures import Builtin_Shader_Names, Draw_Phase_type, Draw_Region_Type, Draw_Space_Types, Shader_Types
from .custom_shader_billboard2D import _billboard_uid_for_image


# =============================================================================================================================
# CONSTANTS 
# ==============================================================================================================================

DEMO_ID_BILLBOARD = "billboard"
DEMO_ID_DASHED    = "dashed"
DEMO_ID_TEXTBOX   = "textbox"
DEMO_ID_STRIPE    = "stripe"

_EXAMPLE_LINEDASH_UID         = "EXAMPLE_POLYLINE_DASH"
_EXAMPLE_TEXTBOX_UID          = "EXAMPLE_TEXTBOX_DEMO"
_EXAMPLE_STRIPE_UID           = "EXAMPLE_STRIPE_PATTERN"

# Unique-attribute keys (nested per-demo CollectionProperty rows).
ATTR_DASHED_PHASE = "phase"
ATTR_DASHED_COUNT = "count"

# Region types that can host a debug border. Unchecking one disables it for all areas.
DEBUG_DRAW_REGION_TYPES = [
    "WINDOW", "HEADER", "TOOL_HEADER", "UI", "TOOLS",
    "FOOTER", "HUD", "PREVIEW", "CHANNELS", "NAVIGATION_BAR",
]

# Which demos support the infinite-loop demo animation (task 3: "animate some, not all").
_ANIMATABLE_DEMOS = {DEMO_ID_BILLBOARD, DEMO_ID_DASHED}

# Animation uids applied per demo, so we can cancel exactly what we added.
_DEMO_ANIMATION_UIDS = {
    DEMO_ID_DASHED:    ["DEMO_DASH_PHASE", "DEMO_DASH_COLOR", "DEMO_DASH_POINTS"],
    DEMO_ID_BILLBOARD: ["DEMO_BB_COLOR", "DEMO_BB_POINTS", "DEMO_BB_SIZE"],
}

_DEBUG_BORDER_COLOR = (1.0, 0.0, 1.0, 1.0)          # Magenta — normal
_DEBUG_BORDER_COLOR_HOVER = (0.0, 1.0, 0.2, 1.0)     # Green — mouse is over this region

# ==============================================================================================================================
# ROW SEEDING / LOOKUP
# ==============================================================================================================================

# Default demo rows seeded once per scene. New demos: add an entry here.
_DEMO_DEFS = [
    {"demo_id": DEMO_ID_BILLBOARD, "label": "2D Image Billboard", "attrs": []},
    {"demo_id": DEMO_ID_DASHED, "label": "Dashed Polyline", "attrs": [
        {"attr_key": ATTR_DASHED_PHASE, "display_name": "Phase",
         "value_kind": "FLOAT", "float_value": 0.0},
        {"attr_key": ATTR_DASHED_COUNT, "display_name": "Cluster Count",
         "value_kind": "INT", "int_value": 0},
    ]},
    {"demo_id": DEMO_ID_TEXTBOX, "label": "Text Boxes", "attrs": []},
    {"demo_id": DEMO_ID_STRIPE, "label": "Stripe Holdout", "attrs": []},
]
def ensure_demo_rows(props) -> None:
    """
    Idempotently seed one DGBLOCKS_PG_Demo_Shader_Common row per known demo, with its default
    unique attributes. Safe to call repeatedly; only missing rows are added.
    """
    existing = {row.demo_id for row in props.demo_settings}
    for ddef in _DEMO_DEFS:
        if ddef["demo_id"] in existing:
            continue
        row = props.demo_settings.add()
        row.demo_id = ddef["demo_id"]
        row.show_shader = True
        for adef in ddef["attrs"]:
            attr = row.unique_attributes.add()
            attr.attr_key = adef["attr_key"]
            attr.display_name = adef["display_name"]
            attr.value_kind = adef["value_kind"]
            if adef["value_kind"] == "INT":
                attr.int_value = adef.get("int_value", 0)
            else:
                attr.float_value = adef.get("float_value", 0.0)


def get_demo_row(props, demo_id):
    for row in props.demo_settings:
        if row.demo_id == demo_id:
            return row
    return None


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


def _create_region_boundary_shader_declarations(props):
    """
    One border Shader_Declaration per unique (space, region) across all open windows, skipping
    any region type whose checkbox is unchecked (task 7). Walking the live window manager keeps
    us to real, currently-valid combos and picks up regions like TOOL_HEADER automatically.
    """
    region_boundary_toggles = props.debug_props.region_boundary_toggles
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
                if not region_type_is_enabled(region_boundary_toggles, region_enum.name):
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


def region_type_is_enabled(region_boundary_toggles, region_type_name: str) -> bool:
    """True if the given Draw_Region_Type name is checked (defaults True if unmodelled)."""
    return bool(getattr(region_boundary_toggles, f"region_{region_type_name}", True))





# ==============================================================================================================================
# PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

def _cb_demo_props_changed(self, context):
    """
    Fired when any of the example-shader properties change (viewport debugging toggle, the
    billboard image/count/spreads, the linedash controls, or the textbox count).

    While drawing is enabled, this rebuilds the whole shader set. Because a rebuild re-fires
    both hook_get_shader_declarations AND hook_before_first_draw, every property edit both
    re-declares the affected example shaders and re-generates their (randomized) geometry —
    which is exactly the "re-randomize on every update" behaviour the billboard example wants.
    """
    if context.scene.dgblocks_onscreen_drawing_props.enable_drawing:
        _rebuild_all_shaders(Enum_Sync_Events.PROPERTY_UPDATE)


def cb_rebuild_shaders(self, context):
    """
    Shared update callback for any demo/region property whose change should re-declare the
    live shader set. While drawing is enabled this reconciles (re-firing both hooks), which is
    also how per-demo `show_shader` eye toggles add/remove shaders from the pull-based set.
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    if props.enable_drawing:
        _rebuild_all_shaders(Enum_Sync_Events.PROPERTY_UPDATE)


def _cb_demo_is_animating_changed(self, context):
    """Apply or cancel the demo's infinite-loop animation (RTC-only) when the toggle flips."""
    props = context.scene.dgblocks_onscreen_drawing_props
    if not props.enable_drawing:
        return
    sync_demo_animation(self, context)


def _cb_demo_fps_changed(self, context):
    """Re-apply the animation with the new framerate if it is currently running."""
    props = context.scene.dgblocks_onscreen_drawing_props
    if props.enable_drawing and self.is_animating:
        sync_demo_animation(self, context)

# ==============================================================================================================================
# PROPERTY GROUPS
# ==============================================================================================================================

# Inject one BoolProperty per drawable region type. Done before bpy registration reads
# __annotations__, so the properties are recognised on the class.
class DGBLOCKS_PG_Debug_Shader_Region_Toggles(bpy.types.PropertyGroup):
    """Per-region-type on/off checkboxes for the viewport-debug border shaders."""
    pass
DGBLOCKS_PG_Debug_Shader_Region_Toggles.__annotations__ = {}
for _rt in DEBUG_DRAW_REGION_TYPES:
    DGBLOCKS_PG_Debug_Shader_Region_Toggles.__annotations__[f"region_{_rt}"] = bpy.props.BoolProperty(
        name=_rt.replace("_", " ").title(),
        default=True,
        update=cb_rebuild_shaders,
    )
del _rt


class DGBLOCKS_PG_Demo_Shader_Attribute(bpy.types.PropertyGroup):
    """
    One shader-UNIQUE attribute (e.g. the dashed shader's `phase` or cluster `count`).
    A generic float/int carrier so future demos can add their own knobs without new classes.

    NOTE: `float_value` is natively clamped to 0..1 (task 2: phase is capped outside that
    range). Future float attrs needing other ranges would read a stored bound instead.
    """
    attr_key:     bpy.props.StringProperty()  # type: ignore
    display_name: bpy.props.StringProperty()  # type: ignore
    value_kind:   bpy.props.EnumProperty(  # type: ignore
        items=[("FLOAT", "Float", ""), ("INT", "Int", "")],
        default="FLOAT",
    )
    float_value:  bpy.props.FloatProperty(name="Value", min=0.0, max=1.0, update=cb_rebuild_shaders)  # type: ignore
    int_value:    bpy.props.IntProperty(name="Value", min=0, max=64, update=cb_rebuild_shaders)  # type: ignore

    def get_value(self):
        return self.int_value if self.value_kind == "INT" else self.float_value


class DGBLOCKS_PG_Demo_Shader_Common(bpy.types.PropertyGroup):
    """
    Unified per-demo settings row. Options here are common to ALL shaders; anything unique to
    one shader lives in the nested `unique_attributes` collection.
    """
    demo_id:       bpy.props.StringProperty()  # type: ignore
    show_shader:   bpy.props.BoolProperty(  # type: ignore
        name="Show Shader", default=True, update=cb_rebuild_shaders,
        description="Whether this demo shader exists at all (eye toggle). Off = removed from the shader list",
    )
    is_animating:  bpy.props.BoolProperty(  # type: ignore
        name="Animate", default=False, update=_cb_demo_is_animating_changed,
        description="Run an infinite-loop demo animation",
    )
    animation_fps: bpy.props.IntProperty(  # type: ignore
        name="Animation FPS", default=30, min=1, max=60, update=_cb_demo_fps_changed,
        description="Ticks per second for this demo's animation",
    )
    scale:         bpy.props.FloatProperty(  # type: ignore
        name="Scale", default=1.0, min=0.01, soft_max=10.0, update=cb_rebuild_shaders,
        description="Uniform scale applied to this demo's generated geometry",
    )
    unique_attributes: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Demo_Shader_Attribute)  # type: ignore

    def get_attr(self, attr_key):
        for a in self.unique_attributes:
            if a.attr_key == attr_key:
                return a
        return None


class DGBLOCKS_PG_Debug_Shader_Example_Props(bpy.types.PropertyGroup):

    # 2D image billboard example
    show_img_2Dbillboard: bpy.props.PointerProperty(name="Billboard Image", type=bpy.types.Image, update=_cb_demo_props_changed)  # type: ignore
    billboard_count: bpy.props.IntProperty(name="Count", default=12, min=0, max=500, update=_cb_demo_props_changed)  # type: ignore
    billboard_default_size: bpy.props.FloatProperty(name="Size", default=0.5, min=0.0, soft_max=5.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_size_spread: bpy.props.FloatProperty(name="Size Spread", default=0.25, min=0.0, soft_max=5.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_location_spread: bpy.props.FloatProperty(name="Location Spread", default=3.0, min=0.0, soft_max=50.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_color_spread: bpy.props.FloatProperty(name="Color Spread", default=1.0, min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Dashed polyline (Metal-safe thickness) example
    show_linedash: bpy.props.BoolProperty(name="Dashed Polyline", update=_cb_demo_props_changed)  # type: ignore
    linedash_thickness: bpy.props.FloatProperty(name="Line Thickness", default=6.0, min=1.0, soft_max=40.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_dash_width: bpy.props.FloatProperty(name="Dash Width", default=20.0, min=1.0, soft_max=200.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_dash_ratio: bpy.props.FloatProperty(name="Dash Gap Ratio", default=0.5, min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_color: bpy.props.FloatVectorProperty(name="Dash Color", subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_color2: bpy.props.FloatVectorProperty(name="Gap Color", subtype="COLOR", size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Multi Text box example
    show_textbox_count: bpy.props.IntProperty(name="Text Boxes", default=0, min=0, max=20, update=_cb_demo_props_changed)  # type: ignore
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
        update=_cb_demo_props_changed,
    )

    # Stripe holdout example (screen-locked 2D stripe pattern rendered over 3D TRIs)
    show_stripes: bpy.props.BoolProperty(name="Stripe Holdout", update=_cb_demo_props_changed)  # type: ignore
    stripe_angle: bpy.props.FloatProperty(name="Stripe Angle", default=0.0, min=0.0, max=360.0, soft_min=0.0, soft_max=360.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_width: bpy.props.FloatProperty(name="Stripe Width", default=40.0, min=2.0, soft_max=200.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_color1: bpy.props.FloatVectorProperty(name="Stripe Color 1", subtype="COLOR", size=4, default=(1.0, 0.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_color2: bpy.props.FloatVectorProperty(name="Stripe Color 2", subtype="COLOR", size=4, default=(0.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Viewport region debugging
    # Region_toggles holds one checkbox per drawable Draw_Region_Type; unchecking one disables that border type for all areas.
    show_region_boundaries: bpy.props.BoolProperty(name="Draw Region Boundaries", update = _cb_demo_props_changed)  # type: ignore
    region_boundary_toggles: bpy.props.PointerProperty(type=DGBLOCKS_PG_Debug_Shader_Region_Toggles)  # type: ignore

# ==============================================================================================================================
# Demo Animations Control
# ==============================================================================================================================

def _resolve_demo_shader_uid(demo_id, props):
    debug_props = props.debug_props
    if demo_id == DEMO_ID_BILLBOARD:
        image = debug_props.show_img_2Dbillboard
        return _billboard_uid_for_image(image) if image is not None else None
    if demo_id == DEMO_ID_DASHED:
        return _EXAMPLE_LINEDASH_UID
    if demo_id == DEMO_ID_TEXTBOX:
        return _EXAMPLE_TEXTBOX_UID
    if demo_id == DEMO_ID_STRIPE:
        return _EXAMPLE_STRIPE_UID
    return None


def _activate_demo_animation(demo_id, common_row, shader) -> None:
    """
    Attach the demo's infinite-loop animation(s) to the live Shader_Instance. Uses
    set_animation() (upsert, preserves phase) so it is idempotent across rebuilds.
    """
    
    def _handle_demo_dashed_line():
        # phase scroll (batch attr `_phase`, read as a uniform in _shader_draw)
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_DASH_PHASE",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_phase",
            start_state=0.0, end_state=1.0,
            duration=1.5, framerate=fps,
            loop_mode=ANIM_LOOP_REPEAT, loop_count=0,
        ))
        # color pulse toward a dimmed variant of the current dash color
        start_col = np.asarray(shader._color, dtype=np.float32)
        end_col = start_col.copy()
        end_col[:3] *= 0.15
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_DASH_COLOR",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_color",
            start_state=start_col, end_state=end_col,
            duration=1.0, framerate=fps,
            loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
        ))
        # geometry "reform" — gentle pulse of the polyline points
        pts = getattr(shader, "_points", None)
        if pts is not None and len(pts):
            end_pts = np.asarray(pts, dtype=np.float32) * np.float32(1.15)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_DASH_POINTS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_points",
                end_state=end_pts, duration=1.2, framerate=fps,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
    
    def _handle_demo_billboard_image():
        
        colors = getattr(shader, "_colors", None)
        if colors is not None and len(colors):
            end_colors = np.asarray(colors, dtype=np.float32).copy()
            end_colors[:, :3] *= 0.3
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_BB_COLOR",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_colors",
                end_state=end_colors, duration=1.0, framerate=fps,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        pts = getattr(shader, "_points", None)
        if pts is not None and len(pts):
            end_pts = np.asarray(pts, dtype=np.float32) * np.float32(1.2)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_BB_POINTS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_points",
                end_state=end_pts, duration=1.5, framerate=fps,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        sizes = getattr(shader, "_sizes", None)
        if sizes is not None and len(sizes):
            end_sizes = np.asarray(sizes, dtype=np.float32) * np.float32(1.5)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_BB_SIZE",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_sizes",
                end_state=end_sizes, duration=1.0, framerate=fps,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
                        
    logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
    fps = float(common_row.animation_fps)

    with suppress_timer_rebuilds():
        if demo_id == DEMO_ID_DASHED:
            _handle_demo_dashed_line()

        elif demo_id == DEMO_ID_BILLBOARD:
            _handle_demo_billboard_image()

    logger.debug(f"Applied demo animation(s) for '{demo_id}' @ {fps}Hz")
    Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)


def _cancel_demo_animation(demo_id, shader) -> None:
    for uid in _DEMO_ANIMATION_UIDS.get(demo_id, []):
        if shader.has_animation(uid):
            shader.cancel_animation(uid, revert=True)


def sync_demo_animation(common_row, context) -> None:
    """Apply or cancel the demo animation to match `common_row.is_animating`."""
    demo_id = common_row.demo_id
    if not demo_is_animatable(demo_id):
        return
    props = context.scene.dgblocks_onscreen_drawing_props
    uid = _resolve_demo_shader_uid(demo_id, props)
    if uid is None:
        return
    _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
    if shader is None:
        return
    if common_row.is_animating:
        _activate_demo_animation(demo_id, common_row, shader)
    else:
        _cancel_demo_animation(demo_id, shader)


def demo_is_animatable(demo_id: str) -> bool:
    return demo_id in _ANIMATABLE_DEMOS

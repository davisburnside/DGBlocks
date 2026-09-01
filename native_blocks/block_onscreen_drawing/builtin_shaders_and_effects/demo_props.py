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
from ..animations.constants import ANIM_DATA_TYPE_BATCH, ANIM_EASE_LINEAR, ANIM_EASING_UI_ITEMS, ANIM_LOOP_PING_PONG, ANIM_LOOP_REPEAT
from ..animations.data_structures import Animation_Declaration
from ..animations.engine import suppress_timer_rebuilds
from ..BL_drawing_structures import Builtin_Shader_Names, Draw_Phase_type, Draw_Region_Type, Draw_Space_Types, Shader_Types
from .custom_shader_billboard2D import _billboard_uid_for_image


# =============================================================================================================================
# CONSTANTS 
# ==============================================================================================================================

DEMO_ID_BILLBOARD = "billboard"
DEMO_ID_DASHED = "dashed"
DEMO_ID_TEXTBOX = "textbox"
DEMO_ID_STRIPE = "stripe"
DEMO_ID_REGION_BOUNDS = "region_bounds"
DEMO_ID_ANNOTATED = "annotated_lines"

_EXAMPLE_LINEDASH_UID = "EXAMPLE_POLYLINE_DASH"
_EXAMPLE_TEXTBOX_UID = "EXAMPLE_TEXTBOX_DEMO"
_EXAMPLE_STRIPE_UID = "EXAMPLE_STRIPE_PATTERN"
_EXAMPLE_ANNOTATED_UID = "EXAMPLE_ANNOTATED_LINES"

# Unique-attribute keys (nested per-demo CollectionProperty rows).
ATTR_DASHED_PHASE = "phase"
ATTR_DASHED_COUNT = "count"
ATTR_STRIPE_PHASE = "phase"

# Region types that can host a debug border. Unchecking one disables it for all areas.
DEBUG_DRAW_REGION_TYPES = [
    "WINDOW", "HEADER", "TOOL_HEADER", "UI", "TOOLS",
    "FOOTER", "HUD", "PREVIEW", "CHANNELS", "NAVIGATION_BAR",
]

# Which demos support the infinite-loop demo animation (task 3: "animate some, not all").
_ANIMATABLE_DEMOS = {DEMO_ID_BILLBOARD, DEMO_ID_DASHED, DEMO_ID_STRIPE, DEMO_ID_ANNOTATED}

# Animation uids applied per demo, so we can cancel exactly what we added.
_DEMO_ANIMATION_UIDS = {
    DEMO_ID_DASHED:    ["DEMO_DASH_PHASE", "DEMO_DASH_COLOR", "DEMO_DASH_POINTS"],
    DEMO_ID_BILLBOARD: ["DEMO_BB_COLOR", "DEMO_BB_POINTS", "DEMO_BB_SIZE"],
    DEMO_ID_STRIPE:    ["DEMO_STRIPE_PHASE"],
    DEMO_ID_ANNOTATED: ["DEMO_ANN_POINTS", "DEMO_ANN_COLORS", "DEMO_ANN_Z_BOOST",
                        "DEMO_ANN_ARROW_LENGTH", "DEMO_ANN_ARROW_ANGLE"],
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
    {"demo_id": DEMO_ID_STRIPE, "label": "Stripe Holdout", "attrs": [
        {"attr_key": ATTR_STRIPE_PHASE, "display_name": "Phase",
         "value_kind": "FLOAT", "float_value": 0.0},
    ]},
    {"demo_id": DEMO_ID_ANNOTATED, "label": "Annotated Lines", "attrs": []},
    {"demo_id": DEMO_ID_TEXTBOX, "label": "Text Boxes", "attrs": []},
    {"demo_id": DEMO_ID_REGION_BOUNDS, "label": "Region Boundaries", "attrs": []},
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


# Seeded once, ever (guarded by props.textbox_lines_seeded), so deleting them all later doesn't
# bring them back — this is a first-run example, not a managed default set like _DEMO_DEFS.
_DEFAULT_TEXTBOX_LINES = [
    {"text": "This is a row with small text", "font_size": 12},
    {"text": "Another row, much much much much longer, with limited row chars, so you can see word-wrap in action",
     "max_char_count": 40},
    {"text": "Center-aligned, larger, colored title", "font_size": 20, "alignment": "center",
     "text_color": (0.35, 0.7, 1.0, 1.0)},
    {"text": "Right-aligned, with an outline", "alignment": "right",
     "outline_enabled": True, "outline_color": (0.0, 0.0, 0.0, 1.0)},
]


def ensure_default_textbox_lines(props) -> None:
    """Seed a few example rows into textbox_lines exactly once (first run only)."""
    if props.textbox_lines_seeded:
        return
    props.textbox_lines_seeded = True
    for line_def in _DEFAULT_TEXTBOX_LINES:
        row = props.textbox_lines.add()
        row.text = line_def["text"]
        row.font_size = line_def.get("font_size", 14)
        row.alignment = line_def.get("alignment", "left")
        row.max_char_count = line_def.get("max_char_count", 80)
        if "text_color" in line_def:
            row.text_color = line_def["text_color"]
        if "outline_enabled" in line_def:
            row.outline_enabled = line_def["outline_enabled"]
        if "outline_color" in line_def:
            row.outline_color = line_def["outline_color"]


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


def _cb_builtin_animation_easing_changed(self, context):
    """
    Re-apply every currently-running demo animation so the new global timing function takes
    effect immediately. set_animation() upserts in place, preserving each animation's phase.
    """
    props = context.scene.dgblocks_onscreen_drawing_props
    if not props.enable_drawing:
        return
    for row in props.demo_settings:
        if row.is_animating:
            sync_demo_animation(row, context)

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


class DGBLOCKS_PG_Textbox_Line_Row(bpy.types.PropertyGroup):
    """
    One user-authored line for the Text Boxes demo. Rows are drawn in order via
    Textbox_Demo_Shader.add_line() from _hook_before_first_draw — this PropertyGroup owns
    every add_line() parameter that is feasible to expose as a UI control.
    """
    text: bpy.props.StringProperty(  # type: ignore
        name="Text", default="Text", update=_cb_demo_props_changed,
    )
    font_size: bpy.props.IntProperty(  # type: ignore
        name="Font Size", default=14, min=6, max=200, update=_cb_demo_props_changed,
    )
    alignment: bpy.props.EnumProperty(  # type: ignore
        name="Alignment",
        items=[
            ("left",       "Left",       ""),
            ("center",     "Center",     ""),
            ("right",      "Right",      ""),
            ("left-soft",  "Left Soft",  "Aligns with the previous line's content start"),
            ("right-soft", "Right Soft", "Aligns with the previous line's content end"),
        ],
        default="left",
        update=_cb_demo_props_changed,
    )
    max_char_count: bpy.props.IntProperty(  # type: ignore
        name="Wrap Width", description="Max characters before word-wrap (0 = never wrap)",
        default=80, min=0, max=500, update=_cb_demo_props_changed,
    )
    padding_mode: bpy.props.EnumProperty(  # type: ignore
        name="Padding",
        description="How many independent padding values this line's padding is split into",
        items=[
            ("SIMPLE", "Simple",              "One value, applied to every side"),
            ("XY",     "Horizontal / Vertical", "Separate horizontal and vertical values"),
            ("ALL",    "Top / Right / Bottom / Left", "Independent value per side"),
        ],
        default="SIMPLE",
        update=_cb_demo_props_changed,
    )
    padding_simple: bpy.props.FloatProperty(name="All Sides", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_horizontal: bpy.props.FloatProperty(name="Horizontal", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_vertical: bpy.props.FloatProperty(name="Vertical", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_top: bpy.props.FloatProperty(name="Top", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_right: bpy.props.FloatProperty(name="Right", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_bottom: bpy.props.FloatProperty(name="Bottom", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    padding_left: bpy.props.FloatProperty(name="Left", default=5.0, min=0.0, max=100.0, update=_cb_demo_props_changed)  # type: ignore
    text_color: bpy.props.FloatVectorProperty(  # type: ignore
        name="Text Color", subtype="COLOR", size=4,
        default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed,
    )
    outline_enabled: bpy.props.BoolProperty(  # type: ignore
        name="Outline", default=False, update=_cb_demo_props_changed,
        description="Soft BLF shadow approximating a text outline (or a drop-shadow, via the offset controls)",
    )
    outline_color: bpy.props.FloatVectorProperty(  # type: ignore
        name="Outline Color", subtype="COLOR", size=4,
        default=(0.0, 0.0, 0.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed,
    )
    outline_spread: bpy.props.EnumProperty(  # type: ignore
        name="Spread",
        description="blf.shadow()'s blur kernel — Blender only supports these 3 fixed sizes",
        items=[
            ("0", "Sharp", "No blur — a crisp 1px shadow"),
            ("3", "Soft",  "3x3 blur"),
            ("5", "Wide",  "5x5 blur"),
        ],
        default="5",
        update=_cb_demo_props_changed,
    )
    outline_offset_x: bpy.props.IntProperty(  # type: ignore
        name="Offset X", description="0 = symmetric outline; non-zero reads as a drop-shadow",
        default=0, min=-20, max=20, update=_cb_demo_props_changed,
    )
    outline_offset_y: bpy.props.IntProperty(  # type: ignore
        name="Offset Y", description="0 = symmetric outline; non-zero reads as a drop-shadow",
        default=0, min=-20, max=20, update=_cb_demo_props_changed,
    )

    def get_padding_value(self):
        """
        The value shape simple_textbox._normalize_padding_value() expects: a scalar, a
        (vertical, horizontal) 2-tuple, or a (top, right, bottom, left) 4-tuple — selected by
        padding_mode.
        """
        if self.padding_mode == "XY":
            return (self.padding_vertical, self.padding_horizontal)
        if self.padding_mode == "ALL":
            return (self.padding_top, self.padding_right, self.padding_bottom, self.padding_left)
        return self.padding_simple


class DGBLOCKS_PG_Debug_Shader_Example_Props(bpy.types.PropertyGroup):

    # Global timing function applied to every builtin/demo animation (task: single scene
    # property controlling the easing of all builtin animations).
    builtin_animation_easing: bpy.props.EnumProperty(  # type: ignore
        name="Timing Function",
        description="Easing curve applied to every builtin demo animation",
        items=[(value, label, desc) for value, label, desc in ANIM_EASING_UI_ITEMS],
        default=ANIM_EASE_LINEAR,
        update=_cb_builtin_animation_easing_changed,
    )

    # 2D image billboard example
    show_img_2Dbillboard: bpy.props.PointerProperty(name="Billboard Image", type=bpy.types.Image, update=_cb_demo_props_changed)  # type: ignore
    billboard_count: bpy.props.IntProperty(name="Count", default=12, min=0, max=500, update=_cb_demo_props_changed)  # type: ignore
    billboard_default_size: bpy.props.FloatProperty(name="Size", default=0.5, min=0.0, soft_max=5.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_size_spread: bpy.props.FloatProperty(name="Size Spread", default=0.25, min=0.0, soft_max=5.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_location_spread: bpy.props.FloatProperty(name="Location Spread", default=3.0, min=0.0, soft_max=50.0, update=_cb_demo_props_changed)  # type: ignore
    billboard_color_spread: bpy.props.FloatProperty(name="Color Spread", default=1.0, min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Dashed polyline (Metal-safe thickness) example
    linedash_thickness: bpy.props.FloatProperty(name="Line Thickness", default=6.0, min=1.0, soft_max=40.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_dash_width: bpy.props.FloatProperty(name="Dash Width", default=20.0, min=1.0, soft_max=200.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_dash_ratio: bpy.props.FloatProperty(name="Dash Gap Ratio", default=0.5, min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_color: bpy.props.FloatVectorProperty(name="Dash Color", subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    linedash_color2: bpy.props.FloatVectorProperty(name="Gap Color", subtype="COLOR", size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Multi Text box example
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
    textbox_x_offset: bpy.props.FloatProperty(name="X Offset", description="Pixels to shift the boxes from the spawn anchor, away from its corner", default=0.0, min=-500.0, max=500.0, update=_cb_demo_props_changed)  # type: ignore
    textbox_y_offset: bpy.props.FloatProperty(name="Y Offset", description="Pixels to shift the boxes from the spawn anchor, away from its corner", default=0.0, min=-500.0, max=500.0, update=_cb_demo_props_changed)  # type: ignore
    textbox_mouse_capture_active: bpy.props.BoolProperty(  # type: ignore
        name="Textbox Mouse Capture Active", default=False,
        description="Whether block_onscreen_drawing currently owns a lightweight block_modal_event "
                     "listener, kept alive only to populate a live cursor position for 'At Mouse'",
    )
    textbox_bg_enabled: bpy.props.BoolProperty(name="Background", default=False, update=_cb_demo_props_changed)  # type: ignore
    textbox_bg_color_top: bpy.props.FloatVectorProperty(name="Background Top", subtype="COLOR", size=4, default=(0.0, 0.0, 0.0, 0.7), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    textbox_bg_color_bottom: bpy.props.FloatVectorProperty(name="Background Bottom", subtype="COLOR", size=4, default=(0.2, 0.2, 0.2, 0.7), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Stripe holdout example (screen-locked 2D stripe pattern rendered over 3D TRIs)
    stripe_angle: bpy.props.FloatProperty(name="Stripe Angle", default=0.0, min=0.0, max=360.0, soft_min=0.0, soft_max=360.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_width: bpy.props.FloatProperty(name="Stripe Width", default=40.0, min=2.0, soft_max=200.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_color1: bpy.props.FloatVectorProperty(name="Stripe Color 1", subtype="COLOR", size=4, default=(1.0, 0.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore
    stripe_color2: bpy.props.FloatVectorProperty(name="Stripe Color 2", subtype="COLOR", size=4, default=(0.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_demo_props_changed)  # type: ignore

    # Annotated smooth-color polyline (with z-boost + arrowheads) example
    annotated_line_thickness: bpy.props.FloatProperty(name="Line Thickness", default=6.0, min=1.0, soft_max=40.0, update=_cb_demo_props_changed)  # type: ignore
    annotated_arrow_length_px: bpy.props.FloatProperty(name="Arrow Length", default=15.0, min=0.0, soft_max=50.0, update=_cb_demo_props_changed)  # type: ignore
    annotated_arrow_angle: bpy.props.FloatProperty(name="Arrow Angle", default=30.0, min=0.0, max=90.0, update=_cb_demo_props_changed)  # type: ignore
    annotated_z_boost: bpy.props.FloatProperty(name="Z Boost", default=0.001, min=-0.01, max=0.01, update=_cb_demo_props_changed)  # type: ignore

    # Viewport region debugging
    # Region_toggles holds one checkbox per drawable Draw_Region_Type; unchecking one disables that border type for all areas.
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
    if demo_id == DEMO_ID_ANNOTATED:
        return _EXAMPLE_ANNOTATED_UID
    return None


def _activate_demo_animation(demo_id, common_row, shader, easing) -> None:
    """
    Attach the demo's infinite-loop animation(s) to the live Shader_Instance. Uses
    set_animation() (upsert, preserves phase) so it is idempotent across rebuilds.
    `easing` is the scene-wide timing function (debug_props.builtin_animation_easing),
    applied to every declaration below.
    """

    def _handle_demo_dashed_line():
        # phase scroll (batch attr `_phase`, read as a uniform in _shader_draw)
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_DASH_PHASE",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_phase",
            start_state=0.0, end_state=1.0,
            duration=1.5, framerate=fps, easing=easing,
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
            duration=1.0, framerate=fps, easing=easing,
            loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
        ))
        # geometry "reform" — gentle pulse of the polyline points
        pts = getattr(shader, "_points", None)
        if pts is not None and len(pts):
            end_pts = np.asarray(pts, dtype=np.float32) * np.float32(1.15)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_DASH_POINTS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_points",
                end_state=end_pts, duration=1.2, framerate=fps, easing=easing,
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
                end_state=end_colors, duration=1.0, framerate=fps, easing=easing,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        pts = getattr(shader, "_points", None)
        if pts is not None and len(pts):
            end_pts = np.asarray(pts, dtype=np.float32) * np.float32(1.2)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_BB_POINTS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_points",
                end_state=end_pts, duration=1.5, framerate=fps, easing=easing,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        sizes = getattr(shader, "_sizes", None)
        if sizes is not None and len(sizes):
            end_sizes = np.asarray(sizes, dtype=np.float32) * np.float32(1.5)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_BB_SIZE",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_sizes",
                end_state=end_sizes, duration=1.0, framerate=fps, easing=easing,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
                        
    def _handle_demo_stripe():
        # phase scroll — animates only the stripe `_phase` (read as a uniform in _shader_draw),
        # making the screen-locked bands crawl along the stripe direction.
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_STRIPE_PHASE",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_phase",
            start_state=0.0, end_state=1.0,
            duration=2.0, framerate=fps, easing=easing,
            loop_mode=ANIM_LOOP_REPEAT, loop_count=0,
        ))

    def _handle_demo_annotated_lines():
        # Points: gentle pulsing scale of the cluster positions
        pts = getattr(shader, "_points", None)
        if pts is not None and len(pts):
            end_pts = np.asarray(pts, dtype=np.float32) * np.float32(1.1)
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_ANN_POINTS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_points",
                end_state=end_pts, duration=1.5, framerate=fps, easing=easing,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        # Colors: pulse toward a dimmer variant
        colors = getattr(shader, "_colors", None)
        if colors is not None and len(colors):
            end_colors = np.asarray(colors, dtype=np.float32).copy()
            end_colors[:, :3] *= 0.3
            shader.set_animation(Animation_Declaration(
                animation_uid="DEMO_ANN_COLORS",
                data_type=ANIM_DATA_TYPE_BATCH, data_name="_colors",
                end_state=end_colors, duration=1.0, framerate=fps, easing=easing,
                loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
            ))
        # viewport_z_boost: oscillates so lines pop over / sink behind the mesh
        z_start = shader._viewport_z_boost
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_ANN_Z_BOOST",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_viewport_z_boost",
            start_state=z_start, end_state=z_start + 0.003,
            duration=2.0, framerate=fps, easing=easing,
            loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
        ))
        # arrow_length_px: oscillates between current value and 0 (arrows fade)
        al_start = shader._arrow_length_px
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_ANN_ARROW_LENGTH",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_arrow_length_px",
            start_state=al_start, end_state=0.0,
            duration=1.5, framerate=fps, easing=easing,
            loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
        ))
        # arrow_angle: oscillates 15 deg <-> 45 deg
        shader.set_animation(Animation_Declaration(
            animation_uid="DEMO_ANN_ARROW_ANGLE",
            data_type=ANIM_DATA_TYPE_BATCH, data_name="_arrow_angle",
            start_state=15.0, end_state=45.0,
            duration=3.0, framerate=fps, easing=easing,
            loop_mode=ANIM_LOOP_PING_PONG, loop_count=0,
        ))

    logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
    fps = float(common_row.animation_fps)

    with suppress_timer_rebuilds():
        if demo_id == DEMO_ID_DASHED:
            _handle_demo_dashed_line()

        elif demo_id == DEMO_ID_BILLBOARD:
            _handle_demo_billboard_image()

        elif demo_id == DEMO_ID_STRIPE:
            _handle_demo_stripe()

        elif demo_id == DEMO_ID_ANNOTATED:
            _handle_demo_annotated_lines()

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
        _activate_demo_animation(demo_id, common_row, shader, props.debug_props.builtin_animation_easing)
    else:
        _cancel_demo_animation(demo_id, shader)


def demo_is_animatable(demo_id: str) -> bool:
    return demo_id in _ANIMATABLE_DEMOS

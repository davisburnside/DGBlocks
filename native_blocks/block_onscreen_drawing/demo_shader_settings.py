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
in `_DEMO_DEFS` plus an animation recipe in `_apply_demo_animation`.
"""

import bpy
import numpy as np


# Addon-level imports
from ...addon_helpers.data_structures import Enum_Sync_Events

# Inter-block imports
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager

# Intra-block imports
from .common_declarations import Block_Loggers, Block_RTC_Members
from .helpers import _rebuild_all_shaders
from .animations.constants import ANIM_DATA_TYPE_BATCH, ANIM_LOOP_PING_PONG, ANIM_LOOP_REPEAT
from .animations.data_structures import Animation_Declaration
from .animations.engine import suppress_timer_rebuilds

# ==============================================================================================================================
# CONSTANTS — demo ids, shader uids, unique-attribute keys, drawable region types
# ==============================================================================================================================

DEMO_ID_BILLBOARD = "billboard"
DEMO_ID_DASHED    = "dashed"
DEMO_ID_TEXTBOX   = "textbox"

# The billboard uid embeds the image name so swapping images forces a fresh Shader_Instance
# (and therefore a fresh GPU texture), since _can_reuse_shader() ignores custom_shader_kwargs.
_EXAMPLE_BILLBOARD_UID_PREFIX = "EXAMPLE_BILLBOARD_2D"
_EXAMPLE_LINEDASH_UID         = "EXAMPLE_POLYLINE_DASH"
_EXAMPLE_TEXTBOX_UID          = "EXAMPLE_TEXTBOX_DEMO"


def _billboard_uid_for_image(image) -> str:
    """Stable per-image billboard uid so swapping the image forces a fresh texture/instance."""
    return f"{_EXAMPLE_BILLBOARD_UID_PREFIX}_{image.name}"


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
]

_DEMO_LABELS = {d["demo_id"]: d["label"] for d in _DEMO_DEFS}


def demo_is_animatable(demo_id: str) -> bool:
    return demo_id in _ANIMATABLE_DEMOS



# ==============================================================================================================================
# PROPERTY UPDATE CALLBACKS
# ==============================================================================================================================

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


class DGBLOCKS_PG_Debug_Shader_Region_Toggles(bpy.types.PropertyGroup):
    """Per-region-type on/off checkboxes for the viewport-debug border shaders."""
    pass


# Inject one BoolProperty per drawable region type. Done before bpy registration reads
# __annotations__, so the properties are recognised on the class.
DGBLOCKS_PG_Debug_Shader_Region_Toggles.__annotations__ = {}
for _rt in DEBUG_DRAW_REGION_TYPES:
    DGBLOCKS_PG_Debug_Shader_Region_Toggles.__annotations__[f"region_{_rt}"] = bpy.props.BoolProperty(
        name=_rt.replace("_", " ").title(),
        default=True,
        update=cb_rebuild_shaders,
    )
del _rt


def region_type_is_enabled(region_toggles, region_type_name: str) -> bool:
    """True if the given Draw_Region_Type name is checked (defaults True if unmodelled)."""
    return bool(getattr(region_toggles, f"region_{region_type_name}", True))

def demo_label(demo_id: str) -> str:
    return _DEMO_LABELS.get(demo_id, demo_id)

# ==============================================================================================================================
# ROW SEEDING / LOOKUP
# ==============================================================================================================================

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

# ==============================================================================================================================
# DEMO ANIMATIONS (RTC-only)
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
    return None


def _apply_demo_animation(demo_id, common_row, shader) -> None:
    """
    Attach the demo's infinite-loop animation(s) to the live Shader_Instance. Uses
    set_animation() (upsert, preserves phase) so it is idempotent across rebuilds. All lerps
    write only to RTC shader state; Blender property values are never touched.
    """
    logger = get_logger(Block_Loggers.ANIMATION_LIFECYCLE)
    fps = float(common_row.animation_fps)

    with suppress_timer_rebuilds():
        if demo_id == DEMO_ID_DASHED:
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

        elif demo_id == DEMO_ID_BILLBOARD:
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
        _apply_demo_animation(demo_id, common_row, shader)
    else:
        _cancel_demo_animation(demo_id, shader)


def reapply_active_demo_animations(props) -> None:
    """
    Re-attach demo animations for every animating demo. Called from hook_before_first_draw so
    demo animations survive a rebuild (undo/redo, eye toggles, prop edits).
    """
    for row in props.demo_settings:
        if not row.is_animating or not demo_is_animatable(row.demo_id):
            continue
        uid = _resolve_demo_shader_uid(row.demo_id, props)
        if uid is None:
            continue
        _, shader, _ = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(Block_RTC_Members.SHADERS, "shader_uid", uid)
        if shader is not None:
            _apply_demo_animation(row.demo_id, row, shader)


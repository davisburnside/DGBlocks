
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
from ..block_timers.feature_timer_manager import Wrapper_Timer_Manager
from ...addon_helpers.ui.helpers import ui_draw_block_panel_header, draw_shared_uilist, ui_draw_subpanel

# --------------------------------------------------------------
# Intra-block imports
from .common_declarations import Block_Data_Mirrors, Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_UIList_Configs
from .feature_shader_manager import Wrapper_Shader_Manager
from .data_structures import Shader_Declaration
from .BL_drawing_structures import Draw_Space_Types, Draw_Region_Type, Draw_Phase_type, Builtin_Shader_Names, Shader_Types
from .helpers import _clear_all_shaders, _rebuild_all_shaders
from .animations.constants import ANIM_DATA_TYPE_BATCH, ANIM_LOOP_PING_PONG
from .animations.data_structures import Animation_Declaration
from .animations.engine import get_timer_definitions_from_animations, suppress_timer_rebuilds
from .builtin_shaders_and_effects.custom_shader_billboard2D import Billboard_Shader
from .builtin_shaders_and_effects.custom_shader_polyline_dash import Polyline_Dash_Shader
from .builtin_shaders_and_effects.custom_shader_textbox_demo import Textbox_Demo_Shader

cache_key_shaders = Block_RTC_Members.SHADERS
cache_key_data_mirrors = Core_Runtime_Cache_Members.REGISTRY_ALL_DATA_MIRRORS
cache_key_shared_uilist_declarations = Core_Runtime_Cache_Members.SHARED_UILIST_CONFIGS

# Optional foreign RTC member owned by block_modal_events (NOT a dependency). Read defensively
# via get_cache(): it returns None when that block is absent or its modal router is idle. We
# keep the key as a named constant rather than importing the foreign enum, since importing a
# non-dependency block is forbidden.
_FOREIGN_RTC_KEY_USER_INPUT_CAPTURE = "USER_INPUT_CAPTURE"

# Example-shader uids. The billboard uid embeds the image name so that swapping images forces a
# fresh Shader_Instance (and therefore a fresh GPU texture), since _can_reuse_shader() does not
# compare custom_shader_kwargs.
_EXAMPLE_BILLBOARD_UID_PREFIX = "EXAMPLE_BILLBOARD_2D"
_EXAMPLE_LINEDASH_UID = "EXAMPLE_POLYLINE_DASH"
_EXAMPLE_TEXTBOX_UID = "EXAMPLE_TEXTBOX_DEMO"

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

    enable_viewport_debugging: bpy.props.BoolProperty(name="3D Viewport Debugging", update = _cb_example_shader_props_changed)  # type: ignore

    # --- 2D image billboard example ---
    # When no image is set the billboard shader is simply not declared (i.e. disabled).
    show_img_2Dbillboard: bpy.props.PointerProperty(name="Billboard Image", type=bpy.types.Image, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_count: bpy.props.IntProperty(name="Count", default=12, min=0, max=500, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_default_size: bpy.props.FloatProperty(name="Size", default=0.5, min=0.0, soft_max=5.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_size_spread: bpy.props.FloatProperty(name="Size Spread", default=0.25, min=0.0, soft_max=5.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_location_spread: bpy.props.FloatProperty(name="Location Spread", default=3.0, min=0.0, soft_max=50.0, update=_cb_example_shader_props_changed)  # type: ignore
    billboard_color_spread: bpy.props.FloatProperty(name="Color Spread", default=1.0, min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore

    # --- Dashed polyline (Metal-safe thickness) example ---
    show_linedash: bpy.props.BoolProperty(name="Dashed Polyline", update=_cb_example_shader_props_changed)  # type: ignore
    linedash_thickness: bpy.props.FloatProperty(name="Line Thickness", default=6.0, min=1.0, soft_max=40.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_dash_width: bpy.props.FloatProperty(name="Dash Width", default=20.0, min=1.0, soft_max=200.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_dash_ratio: bpy.props.FloatProperty(name="Dash Gap Ratio", default=0.5, min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_color: bpy.props.FloatVectorProperty(name="Dash Color", subtype="COLOR", size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore
    linedash_color2: bpy.props.FloatVectorProperty(name="Gap Color", subtype="COLOR", size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, update=_cb_example_shader_props_changed)  # type: ignore

    # --- Text box example ---
    show_textbox_count: bpy.props.IntProperty(name="Text Boxes", default=0, min=0, max=20, update=_cb_example_shader_props_changed)  # type: ignore

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
    enable_drawing: bpy.props.BoolProperty(name="Enable Drawing", default=False) # type: ignore
    
    debug_props: bpy.props.PointerProperty(type = DGBLOCKS_PG_Debug_Shader_Example_Props) # type: ignore
    debug_show_examples: bpy.props.BoolProperty(name="Show Shader Examples", default=False) # type: ignore
    shader_mirror: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Shader_Mirror_Row)  # type: ignore
    shader_mirror_selected_idx: bpy.props.IntProperty()  # type: ignore

# ==============================================================================================================================
# HOOK SUBSCRIBERS

_DEBUG_BORDER_COLOR = (1.0, 0.0, 1.0, 1.0)          # Magenta — normal
_DEBUG_BORDER_COLOR_HOVER = (0.0, 1.0, 0.2, 1.0)     # Green — mouse is over this region


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
    enable_viewport_debugging is checked.

    Rather than hardcoding a space/region list, we walk the live window manager so that only
    real, currently-valid (space, region) combinations are declared — this covers all editor
    types across all windows and picks up regions like TOOL_HEADER automatically. Each unique
    (space_type, region_type) yields one Shader_Declaration; the single draw handler Blender
    registers per space type then draws that border in every matching area/window.
    """

    props = bpy.context.scene.dgblocks_onscreen_drawing_props
    if not props.debug_props.enable_viewport_debugging:
        return []

    seen_combos: set = set()
    returned_shader_definitions = []

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
                # Regions with zero size (collapsed) can't host a meaningful border.
                if region.width <= 0 or region.height <= 0:
                    continue
                combo = (space, region_enum)
                if combo in seen_combos:
                    continue
                seen_combos.add(combo)
                returned_shader_definitions.append(
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

    returned_shader_definitions.extend(_get_example_shader_definitions(props))
    return returned_shader_definitions


def _billboard_uid_for_image(image) -> str:
    """Stable per-image billboard uid so swapping the image forces a fresh texture/instance."""
    return f"{_EXAMPLE_BILLBOARD_UID_PREFIX}_{image.name}"


def _get_example_shader_definitions(props):
    """
    Declarations for the three example shaders (billboard / dashed polyline / text boxes).

    All three are custom Shader_Instance subclasses drawn in VIEW_3D/WINDOW. Each is declared
    only while its controlling property indicates it should be visible — a missing billboard
    image, an unchecked dash toggle, or a zero textbox count simply omits the declaration, which
    is how "no image -> shader disabled" is expressed to the pull-based manager.
    """
    defs = []
    debug_props = props.debug_props

    image = debug_props.show_img_2Dbillboard
    if image is not None and debug_props.billboard_count > 0:
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

    if debug_props.show_linedash:
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

    if debug_props.show_textbox_count > 0:
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

    # --- Dashed polyline: a simple demo path + the user-controlled dash parameters ---
    if debug_props.show_linedash:
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_LINEDASH_UID)
        if shader is not None:
            # Flat list of segment endpoint PAIRS forming a square loop on the XY plane.
            corners = [(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)]
            polyline = []
            for i in range(len(corners)):
                polyline.append(corners[i])
                polyline.append(corners[(i + 1) % len(corners)])
            shader.set_polyline(polyline)
            shader.set_line_thickness(debug_props.linedash_thickness)
            shader.set_dash_width(debug_props.linedash_dash_width)
            shader.set_dash_ratio(debug_props.linedash_dash_ratio)
            shader.set_dash_colors(
                tuple(debug_props.linedash_color),
                tuple(debug_props.linedash_color2),
            )

    # --- Text boxes ---
    if debug_props.show_textbox_count > 0:
        shader = Wrapper_Shader_Manager.get_shader(_EXAMPLE_TEXTBOX_UID)
        if shader is not None:
            shader.set_textbox_count(debug_props.show_textbox_count)


def hook_get_timer_definitions():
    """
    Subscribed to block_timers' hook_get_timer_definitions.
    Returns one Timer_Definition per unique framerate across all shader-owned
    animations. block_timers creates one bpy.app.timer per definition returned here.
    """
    return get_timer_definitions_from_animations()

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


class DGBLOCKS_OT_Sample_Animations(bpy.types.Operator):
    """Add a simple looping 'jitter' animation to every enabled shader"""
    bl_idname = "dgblocks.sample_animations"
    bl_label = "Sample Animations"
    bl_options = {"REGISTER"}

    def execute(self, context):

        cached_shaders = Wrapper_Runtime_Cache.get_cache(cache_key_shaders) or []

        applied = 0
        skipped = 0
        with suppress_timer_rebuilds():
            for shader_instance in cached_shaders:
                if not shader_instance.is_enabled:
                    continue

                # A shader whose geometry has not been pushed yet has nothing to jitter.
                points = shader_instance._points
                if points is None or len(points) == 0:
                    skipped += 1
                    continue

                jittered_points = points.copy()
                jittered_points[:] += 1

                # Ping-pong so it reads as a jitter rather than a one-way drift, and
                # set_animation() so repeated clicks retarget instead of warning.
                shader_instance.set_animation(Animation_Declaration(
                    animation_uid = "SAMPLE_JITTER",
                    data_type     = ANIM_DATA_TYPE_BATCH,
                    data_name     = "_points",
                    end_state     = jittered_points,
                    duration      = 0.5,
                    framerate     = 30,
                    loop_mode     = ANIM_LOOP_PING_PONG,
                    loop_count    = 6,
                    revert_on_finish = True,
                ))
                applied += 1

        if applied:
            Wrapper_Timer_Manager.request_timer_rebuild(Enum_Sync_Events.PROPERTY_UPDATE)
            self.report({"INFO"}, f"Jitter added to {applied} shader(s)")
        else:
            self.report(
                {"WARNING"},
                f"No enabled shaders with geometry to animate ({skipped} had no points)",
            )

        return {"FINISHED"}


def _ui_draw_shader_examples_subpanel(context, container):
    """Contents of the 'Shader Examples' subpanel. Only enabled while drawing is on."""
    drawing_props = context.scene.dgblocks_onscreen_drawing_props
    debug_props = drawing_props.debug_props

    col = container.column()
    col.enabled = drawing_props.enable_drawing

    # Viewport region debugging
    col.prop(debug_props, "enable_viewport_debugging", toggle=True)

    # 2D image billboards
    box = col.box()
    box.label(text="2D Image Billboards", icon="IMAGE_DATA")
    box.prop(debug_props, "show_img_2Dbillboard")
    sub = box.column()
    sub.enabled = debug_props.show_img_2Dbillboard is not None
    sub.prop(debug_props, "billboard_count")
    sub.prop(debug_props, "billboard_default_size")
    sub.prop(debug_props, "billboard_size_spread")
    sub.prop(debug_props, "billboard_location_spread")
    sub.prop(debug_props, "billboard_color_spread")

    # Dashed polyline
    box = col.box()
    box.prop(debug_props, "show_linedash", toggle=True)
    sub = box.column()
    sub.enabled = debug_props.show_linedash
    sub.prop(debug_props, "linedash_thickness")
    sub.prop(debug_props, "linedash_dash_width")
    sub.prop(debug_props, "linedash_dash_ratio")
    sub.prop(debug_props, "linedash_color")
    sub.prop(debug_props, "linedash_color2")

    # Text boxes
    box = col.box()
    box.label(text="Text Boxes", icon="SMALL_CAPS")
    box.prop(debug_props, "show_textbox_count")


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

        # Master enable / disable toggle
        layout.prop(drawing_props, "enable_drawing", toggle=True)

        # Example / debug shaders grouped under a collapsible subpanel.
        ui_draw_subpanel(
            context, layout, "onscreen_shader_examples", "Shader Examples",
            _ui_draw_shader_examples_subpanel,
        )

        if not drawing_props.shader_mirror:
            layout.label(text="No active shaders", icon="INFO")
        else:
            row = layout.row()
            row.enabled = drawing_props.enable_drawing
            row.operator(DGBLOCKS_OT_Sample_Animations.bl_idname, icon="PLAY")
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
        DGBLOCKS_PG_Shader_Mirror_Row,
        DGBLOCKS_PG_Debug_Shader_Example_Props,
        DGBLOCKS_PG_Onscreen_Drawing_Props,
        DGBLOCKS_OT_Toggle_Shader,
        DGBLOCKS_OT_Sample_Animations,
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

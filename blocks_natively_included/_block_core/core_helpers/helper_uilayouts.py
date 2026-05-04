
import textwrap
import math
from datetime import datetime
import textwrap
import bpy # type: ignore
import blf # type: ignore

from .constants import Core_Runtime_Cache_Members
from ..core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from ..core_features.feature_hooks import _uilayout_draw_hooks_settings
from ..core_features.feature_block_manager import _uilayout_draw_block_manager_settings
from ..core_features.feature_logs import _uilayout_draw_logger_settings

def uilayout_template_columns_for_propertygroup(
        context:bpy.context, 
        container:bpy.types.UILayout, 
        property_owners:list[bpy.types.PropertyGroup], 
        property_names:list[str],
        property_titles:list[str]):
    
    if len(property_owners) != len(property_names) or len(property_names) != len(property_titles): # one prop_name per prop_owner
        raise Exception(f"List lengths must match: property_owners={len(property_owners)} property_names={len(property_names)} property_titles={len(property_titles)}")
    
    col = container.column(align=True)
    for idx, prop_owner in enumerate(property_owners):
        
        prop_name = property_names[idx]
        
        # 1. Create a split. factor=0.4 means the left side takes 40% width.
        # align=True connects the boxes, creating that vertical 'seam' line.
        split = col.split(factor=0.6, align=True)
        
        # 2. Left side: The Label
        # Use a nested row with alignment='RIGHT' to keep text against the line.
        left_side = split.row(align=True)
        left_side.alignment = 'RIGHT'
        left_side.label(text=property_titles[idx])
        
        # 3. Right side: The Property
        split.prop(prop_owner, prop_name, text="")

def draw_wrapped_text_v2(context, layout, text, font_id=0, padding=10):
    """
    Draw word-wrapped text in a Blender UI panel.
    Word pixel widths are cached in the addon runtime cache.

    Args:
        layout:    The UI layout to draw into.
        text:      The string to wrap and display.
        context:   Blender context (used to get region width and scale).
        font_id:   BLF font id (0 = default Blender UI font).
        padding:   Base pixel padding (will be scaled).
    """
    if context is None:
        context = bpy.context

    ui_scale = context.preferences.system.ui_scale
    dpi_fac = context.preferences.system.dpi / 72
    pixel_size = context.preferences.system.pixel_size
    scale = ui_scale * dpi_fac * pixel_size

    width_px = context.region.width if hasattr(context, 'region') else 300
    max_width = width_px - (padding * scale)

    for paragraph in text.split('\n'):
        if not paragraph.strip():
            layout.label(text='')
            continue
        for line in _wrap_text(paragraph, max_width, font_id, scale):
            layout.label(text=line)

# ==============================================================================================================================
# INTERNAL API - Only used inside this block
# ==============================================================================================================================

def uilayout_draw_core_block_settings(context:bpy.context, container:bpy.types.UILayout):
    
    core_scene_props = context.scene.dgblocks_core_props
    
    # General settings
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_core_general", default_closed=True)
    panel_header.label(text = "General")
    if panel_body is not None: 
        grid = panel_body.grid_flow(columns=2)
        grid.prop(core_scene_props, "addon_is_active")
        grid.prop(core_scene_props, "debug_mode_enabled")
        grid.prop(core_scene_props, "debug_log_all_RTC_BL_sync_actions")
        grid.prop(core_scene_props, "documentation_weblinks_enabled")
        op_rtc_clear = grid.operator("dgblocks.debug_force_reload_scipts", text = "Clear RTC")
        op_rtc_clear.target = "RTC"
        op_rtc_clear.action = "CLEAR"
        op_rtc_restore = grid.operator("dgblocks.debug_force_reload_scipts", text = "Restore RTC")
        op_rtc_restore.target = "RTC"
        op_rtc_restore.action = "RESTORE"
        
    
    # Draw management subpanels for blocks, hooks, & loggers
    _uilayout_draw_block_manager_settings(context, container)
    _uilayout_draw_hooks_settings(context, container)
    _uilayout_draw_logger_settings(context, container)

# --------------------------------------------------------------
# Used by draw_wrapped_text_v2
# --------------------------------------------------------------

def _ensure_word_widths(text, font_id=0, scale=1.0):
    """Ensure the word widths for a given string are computed and cached."""
    cache = Wrapper_Runtime_Cache.get_cache(Core_Runtime_Cache_Members.UI_WORDWRAP_WIDTHS)
    if cache is None:
        cache = {}
        Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.UI_WORDWRAP_WIDTHS, cache)

    if text not in cache:
        blf.size(font_id, 11 * scale)
        cache[text] = [blf.dimensions(font_id, w)[0] for w in text.split(' ')]
        Wrapper_Runtime_Cache.set_cache(Core_Runtime_Cache_Members.UI_WORDWRAP_WIDTHS, cache)

    return cache[text]

def _wrap_text(text, max_width, font_id=0, scale=1.0):
    """Word-wrap text using pre-cached word widths."""
    blf.size(font_id, 11 * scale)
    space_width, _ = blf.dimensions(font_id, ' ')

    words = text.split(' ')
    word_widths = _ensure_word_widths(text, font_id, scale)

    lines = []
    current_line_words = []
    current_width = 0.0

    for word, w_width in zip(words, word_widths):
        if current_line_words:
            new_width = current_width + space_width + w_width
        else:
            new_width = w_width

        if new_width <= max_width or not current_line_words:
            current_line_words.append(word)
            current_width = new_width
        else:
            lines.append(' '.join(current_line_words))
            current_line_words = [word]
            current_width = w_width

    if current_line_words:
        lines.append(' '.join(current_line_words))

    return lines


import textwrap
from enum import Enum
import math
from datetime import datetime
import textwrap
import bpy # type: ignore
import blf # type: ignore

from ....my_addon_config import (separator_width_factor,weblink_button_width_factor, min_width_for_weblink_btn_spawn)
from .constants import Core_Runtime_Cache_Members
from ..core_features.feature_runtime_cache import Wrapper_Runtime_Cache

#=================================================================================
# PUBLIC API - Usable by any block
#=================================================================================

def uilayout_draw_block_panel_header(context:bpy.context, container:bpy.types.UILayout, header_text:str, url_enum:Enum = None, icon_name:str = None):
    
    container.separator(factor = separator_width_factor, type = "LINE")
    container.use_property_split = False
    container.alignment="EXPAND"
    if icon_name is not None:
        container.label(text = "", icon = icon_name)
    container.label(text = header_text)
    row = container.row()
    row.alignment = 'RIGHT'
    if url_enum is not None and context.region.width > min_width_for_weblink_btn_spawn and context.scene.dgblocks_core_props.documentation_weblinks_enabled:
        row.separator(factor = separator_width_factor, type = "LINE")
        row.scale_x = weblink_button_width_factor
        op = row.operator("dgblocks.open_help_page", text="", icon = "QUESTION")
        op.web_documentation_url = url_enum.value

def uilayout_draw_block_body_header(context:bpy.context, container:bpy.types.UILayout, block_id: str):
    
    box = container.box()
    # box = container
    sep_factor = 0.2
    box.separator(type = "LINE", factor = sep_factor)
    row = box.row()
    row.alignment = "CENTER"
    row.label(text = block_id)
    box.separator(type = "LINE", factor = sep_factor)

def ui_box_with_header(context:bpy.context, container:bpy.types.UILayout, header_text:list[str], icon:str = None, separator_factor:float = 0.2, skip_box:bool = False):
    
    if isinstance(header_text, str):
        header_text = [header_text]
    if skip_box:
        self_container = container
    else:
        self_container = container.box()
    for idx, str_item in enumerate(header_text):
        row = self_container.row()
        row.alignment = "CENTER"
        row.scale_y = 0.7
        row.label(text = str_item)
        if icon is not None and idx == 0:
            row.label(text = "", icon = icon)
    
    if separator_factor > 0.0:
        self_container.separator(type="LINE", factor = separator_factor)
    return self_container

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

def draw_wrapped_text(context, layout, text, width_px=None, padding = 20):
    """Draw word-wrapped text in a Blender UI panel."""
    if context is None:
        context = bpy.context

    # UI scale factors
    ui_scale = context.preferences.system.ui_scale           # User preference (Interface → Resolution Scale)
    dpi_fac = context.preferences.system.dpi / 72            # System DPI factor
    pixel_size = context.preferences.system.pixel_size        # Pixel size multiplier (e.g. 2 on Retina)
    
    # Combined scale factor affecting text rendering
    scale = ui_scale * dpi_fac * pixel_size

    if width_px is None:
        if hasattr(context, 'region'):
            width_px = context.region.width
        else:
            width_px = 300

    scaled_padding = padding * scale
    max_width = width_px - scaled_padding

    lines = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            lines.append('')
            continue

        # ~7px per char at 1.0 scale
        char_width = 7 * scale
        chars_per_line = max(10, int(max_width / char_width))
        lines.extend(textwrap.wrap(paragraph, width=chars_per_line))

    for line in lines:
        layout.label(text=line)

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

def uilayout_section_separator(container, lines_count:int = 2, extra_space:float = 1):
    
    if extra_space > 0:
        container.separator(factor = extra_space)
    for _ in range(lines_count):
        container.separator(type="LINE", factor = 0.4)
    if extra_space > 0:
        container.separator(factor = extra_space)

#=================================================================================
# INTERNAL API - Only used inside this block
#=================================================================================

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

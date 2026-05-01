
import sys
from enum import Enum, StrEnum, auto
from typing import Optional
# This module can't import from any others in this addon

# =============================================================================
# REQUIRED UNIQUE VALUES - These must not conflict with any other addon
# =============================================================================

addon_name = "dgblock_basic_template" # Must match bl_info["name"], of main __init__.py. It is defined here to avoid circular dependencies
addon_title = "DGBlocks Template" # Text shown in the right-side panel of the 3D Viewport
addon_bl_type_prefix = "DGBLOCKS" # Must be uppercase. Used to name Blender-registered classes (Operators & Panels)

# =============================================================================
# REQUIRED ARBITRARY VALUES - These can be anything, but must exist
# =============================================================================

# Used when printing to console
base_linebreak_length = 20 

# Helpful for debugging. In most cases, this should be set to False before release
should_show_developer_ui_panels = True

# Allows/prevents __pycache__ folders from
should_allow_pycache = True
if should_allow_pycache:
    sys.dont_write_bytecode = True

default_disabled_icon = "CANCEL"

# Hotkeys Definitions
addon_hotkeys = [
    {
        "OP_NAME": "dgblocks.debug_force_reload_script", # Operator's bl_idname value
        "TYPE": "R",
        "CTRL": False,
        "ALT": False,
        "SHIFT": False
    }
]

# UI settings for the [?] button
min_width_for_weblink_btn_spawn = 140.0 # If a container is less than this pixel width, the help button will not spawn
weblink_button_width_factor = 1.0 # 2.0 will double button width, 0.5 will half...
separator_width_factor = 0.7 # controls width of vertical line + offset

# Documentation Links for the [?] button
class Documentation_URLs(StrEnum):
    MY_PLACEHOLDER_URL_1 = "https://www.google.com"
    MY_PLACEHOLDER_URL_2 = "https://www.yahoo.com"
    # ...


# Documentation Links for the [?] button
class Global_Tag_Ids(StrEnum):
    INVALID_BLOCK = auto()
    DISABLED_BLOCK = auto()
    # ...

# Format for all log messages
logger_format = f"- %(name)20s %(levelname)10s: %(message)s"

# =============================================================================
# NON-REQUIRED ARBITRARY VALUES - These can be anything, & may even be removed
# =============================================================================

# Define the code repository URL of this addon. 
# This is used in rare crash events, to direct the user to create an issue in github
my_addon_repository: Optional[str] = None #"https://github.com/dgblocks-core-template"

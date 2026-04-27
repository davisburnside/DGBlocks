"""
TEMPLATE: Fixed-List Feature Wrapper
=====================================
Copy this file and modify it for each fixed-list feature.

Architecture:
- A StrEnum defines all members at dev time (single source of truth)
- A @dataclass mirrors each member's state in the Runtime Cache (RTC)
- A PropertyGroup with hardcoded PointerProperties mirrors each member in Blender data
- Two-way sync functions keep BL and RTC in agreement
- A UI helper draws all members as label + toggle rows

Copy checklist:
  1. Rename the enum, dataclass, PropertyGroup, and wrapper class
  2. Replace member entries in the enum
  3. Update the PropertyGroup PointerProperties to match
  4. Update the RTC cache key
  5. Add any feature-specific fields to the dataclass + PropertyGroup
  6. Wire the PropertyGroup into your addon's scene/object props
  7. Wire the UI helper into your panel's draw()
"""

import bpy
from enum import auto
from dataclasses import dataclass, field
from typing import Optional

# --- Replace these with your actual imports ---
# from .your_cache_module import Wrapper_Runtime_Cache, Core_Runtime_Cache_Members
# from .your_logger_module import get_logger
# from .your_utils import is_bpy_ready


# =================================================================================
# CONSTANTS & ENUM — Single source of truth for all members
# =================================================================================

class Template_Feature_Members(StrEnum):
    """
    Every member of the fixed list. Add/remove entries here,
    then update the PropertyGroup and sync functions to match.
    
    The enum name IS the uid.
    The value tuple is (display_name, default_is_enabled).
    """
    MEMBER_ALPHA = ("Alpha Feature", False)
    MEMBER_BETA  = ("Beta Feature", False)
    MEMBER_GAMMA = ("Gamma Feature", True)

    def __new__(cls, display_name: str, default_enabled: bool):
        obj = str.__new__(cls, display_name)
        obj._value_ = display_name
        obj.display_name = display_name
        obj.default_enabled = default_enabled
        return obj


# RTC cache key — one flat dict, not a list
rtc_feature_key = "REGISTRY_TEMPLATE_FEATURE"  # Replace with Core_Runtime_Cache_Members.YOUR_KEY


# =================================================================================
# RTC DATA — @dataclass per member
# =================================================================================

@dataclass
class RTC_Template_Member:
    """
    Runtime state for a single fixed-list member.
    Add feature-specific fields here (they won't sync to BL
    unless you also add them to the PropertyGroup + sync funcs).
    """
    uid: str
    display_name: str
    is_enabled: bool = False


# =================================================================================
# BLENDER DATA — PropertyGroup with hardcoded PointerProperties
# =================================================================================

def _callback_member_toggled(self, context):
    """
    Fires when any member's is_enabled changes in BL data.
    Pushes the new value into RTC.
    """
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(rtc_feature_key):
        return
    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, True)

    all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)
    if all_members and self.uid in all_members:
        all_members[self.uid].is_enabled = self.is_enabled

    Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, False)


class TEMPLATE_PG_Member(bpy.types.PropertyGroup):
    """
    Single member's Blender-side data.
    Must contain the same syncable fields as RTC_Template_Member.
    """

    uid: bpy.props.StringProperty(
        name="UID",
        default="",
    )  # type: ignore

    display_name: bpy.props.StringProperty(
        name="Display Name",
        default="",
    )  # type: ignore

    is_enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=False,
        update=_callback_member_toggled,
    )  # type: ignore


class TEMPLATE_PG_Feature_Root(bpy.types.PropertyGroup):
    """
    Parent PropertyGroup with one named PointerProperty per member.
    Field names must match the enum member names exactly.

    Wire this into your addon's scene props, e.g.:
        bpy.types.Scene.my_feature = PointerProperty(type=TEMPLATE_PG_Feature_Root)
    """

    MEMBER_ALPHA: bpy.props.PointerProperty(type=TEMPLATE_PG_Member)  # type: ignore
    MEMBER_BETA:  bpy.props.PointerProperty(type=TEMPLATE_PG_Member)  # type: ignore
    MEMBER_GAMMA: bpy.props.PointerProperty(type=TEMPLATE_PG_Member)  # type: ignore


# =================================================================================
# WRAPPER CLASS
# =================================================================================

class Wrapper_Template_Feature:
    """
    Manages a fixed set of toggleable members with BL ↔ RTC sync.
    No instance creation/destruction — all members exist at dev time.
    """

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls) -> bool:
        """
        Called before bpy is available.
        Populates RTC with default state for every member.
        """
        initial_members = {}
        for member in Template_Feature_Members:
            initial_members[member.name] = RTC_Template_Member(
                uid=member.name,
                display_name=member.display_name,
                is_enabled=member.default_enabled,
            )

        Wrapper_Runtime_Cache.set_cache(rtc_feature_key, initial_members)
        return True

    @classmethod
    def init_post_bpy(cls) -> bool:
        """
        Called after bpy is available.
        BL data may contain saved values from a previous session.
        Pull BL → RTC so saved user prefs overwrite defaults.
        """
        cls.update_RTC_with_mirrored_BL_data()
        return True

    @classmethod
    def destroy_wrapper(cls) -> bool:
        """
        Called during addon unregister. Clean up RTC.
        """
        Wrapper_Runtime_Cache.remove_cache(rtc_feature_key)
        return True

    # ----------------------------------------------------------
    # Two-way sync
    # ----------------------------------------------------------

    @classmethod
    def _get_bl_root(cls) -> TEMPLATE_PG_Feature_Root:
        """
        Returns the parent PropertyGroup from the scene.
        Replace the attribute path with your actual wiring.
        """
        return bpy.context.scene.your_addon_props.template_feature

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls):
        """
        BL → RTC: Overwrites RTC state with whatever is saved in the .blend.
        Called on startup, file load, undo/redo (via your external handler).
        """
        Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, True)

        bl_root = cls._get_bl_root()
        all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)

        for member in Template_Feature_Members:
            bl_pg = getattr(bl_root, member.name, None)
            if bl_pg is None:
                continue
            if member.name in all_members:
                all_members[member.name].is_enabled = bl_pg.is_enabled
                # Sync additional fields here as needed

        Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, False)

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls):
        """
        RTC → BL: Pushes current RTC state into the PropertyGroup.
        Called when RTC is the authority (e.g. after programmatic changes).
        """
        Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, True)

        bl_root = cls._get_bl_root()
        all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)

        for member in Template_Feature_Members:
            rtc_entry = all_members.get(member.name)
            if rtc_entry is None:
                continue
            bl_pg = getattr(bl_root, member.name, None)
            if bl_pg is None:
                continue

            bl_pg.uid = rtc_entry.uid
            bl_pg.display_name = rtc_entry.display_name
            bl_pg.is_enabled = rtc_entry.is_enabled
            # Sync additional fields here as needed

        Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, False)

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    @classmethod
    def is_enabled(cls, member: Template_Feature_Members) -> bool:
        all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)
        if all_members is None or member.name not in all_members:
            return False
        return all_members[member.name].is_enabled

    @classmethod
    def set_enabled(cls, member: Template_Feature_Members, enabled: bool):
        """
        Programmatic toggle. Updates RTC then pushes to BL.
        """
        all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)
        if all_members is None or member.name not in all_members:
            return

        all_members[member.name].is_enabled = enabled

        if is_bpy_ready():
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, True)
            cls.update_BL_with_mirrored_RTC_data()
            Wrapper_Runtime_Cache.flag_cache_as_syncing(rtc_feature_key, False)

    @classmethod
    def get_member(cls, member: Template_Feature_Members) -> Optional[RTC_Template_Member]:
        all_members = Wrapper_Runtime_Cache.get_cache(rtc_feature_key)
        if all_members is None:
            return None
        return all_members.get(member.name)

    # ----------------------------------------------------------
    # UI Drawing Helper
    # ----------------------------------------------------------

    @classmethod
    def draw_panel(cls, layout: bpy.types.UILayout):
        """
        Draws all members as rows with a label and toggle.
        Call from your panel's draw():
            Wrapper_Template_Feature.draw_panel(layout)
        """
        bl_root = cls._get_bl_root()

        for member in Template_Feature_Members:
            bl_pg = getattr(bl_root, member.name, None)
            if bl_pg is None:
                continue

            row = layout.row(align=True)
            row.label(text=member.display_name)
            row.prop(bl_pg, "is_enabled", text="", toggle=True)


# =================================================================================
# REGISTRATION
# =================================================================================

classes_to_register = [
    TEMPLATE_PG_Member,
    TEMPLATE_PG_Feature_Root,
]

def register():
    for cls in classes_to_register:
        bpy.utils.register_class(cls)

    # Wire into your scene props — replace with your actual path
    # bpy.types.Scene.your_addon_props is assumed to already exist
    # Example if this is standalone:
    # bpy.types.Scene.template_feature = bpy.props.PointerProperty(type=TEMPLATE_PG_Feature_Root)

def unregister():
    # Example if standalone:
    # del bpy.types.Scene.template_feature

    for cls in reversed(classes_to_register):
        bpy.utils.unregister_class(cls)
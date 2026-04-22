"""
profile_manager.py
==================
Profile Management Feature Wrapper

ARCHITECTURE OVERVIEW
---------------------
A "category" IS a profile type. Registering a category means registering a
BL_BaseProfile subclass and binding it to a unique category_id. All profiles
within a category are homogeneous instances of that one subclass.

Storage layout on Scene or AddonPreferences:

    <storage_root>.profile_manager          : BL_ProfileContainer
        .categories                         : CollectionProperty(BL_CategoryEntry)
            [i]  BL_CategoryEntry
                     .category_id           : StringProperty   (unique, frozen after creation)
                     .display_name          : StringProperty
                     .active_profile_index  : IntProperty
                     .profiles              : CollectionProperty(<BL_BaseProfile subclass>)
                         [j]  <subclass instance>
                                  .profile_id   : StringProperty  (unique within category)
                                  .name         : StringProperty  (Blender auto-increments)
                                  .tags         : CollectionProperty(BL_ProfileTag)
                                      [k]  .name   : StringProperty (unique within profile)
                                           .tag_id : IntProperty   (unique within profile)
                                  ... caller-defined extra fields

RTC layout
----------
  "pm.categories"              -> dict[category_id -> BL_CategoryEntry]   (live BL references)
  "pm.profiles.<category_id>"  -> dict[profile_id  -> <profile subclass>] (live BL references)

Assumptions
-----------
  - Runtime_Cache, Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager
    are imported from your codebase. Stubs are provided below for review.
  - One BL_BaseProfile subclass per category (caller provides it at registration).
  - Storage target ("scene" | "preferences") is declared per-category.
  - Operator bl-idname prefix: "profile_manager"
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Optional, Type

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Context, Operator, PropertyGroup, UIList

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....addon_helper_funcs import sync_blender_propertygroup_and_raw_python
from ....my_addon_config import addon_name

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_runtime_cache import Wrapper_Runtime_Cache
from ..core_data.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager


log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# RTC KEY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_RTC_CATEGORIES_KEY = "pm.categories"


def _rtc_profiles_key(category_id: str) -> str:
    return f"pm.profiles.{category_id}"


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL CATEGORY REGISTRY
# Populated at registration time. Drives all dynamic PG patching.
# ─────────────────────────────────────────────────────────────────────────────

# shape: category_id -> {
#   "category_id":   str,
#   "display_name":  str,
#   "storage":       "scene" | "preferences",
#   "profile_type":  Type[BL_BaseProfile],
#   "addon_id":      str | None,   # required when storage == "preferences"
# }
_category_registry: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY GROUPS
# ─────────────────────────────────────────────────────────────────────────────

class BL_ProfileTag(PropertyGroup):
    """
    A lightweight label attached to a profile.
    'name' is inherited from PropertyGroup and auto-incremented by Blender.
    tag_id must be unique within its parent profile — enforced in logic.
    """
    tag_id: IntProperty(
        name="Tag ID",
        description="Unique integer identifier for this tag within its profile",
        default=0,
    )


class BL_BaseProfile(PropertyGroup):
    """
    Every caller-defined profile class must inherit from this.
    Callers add their own fields on the subclass; do NOT redeclare these.

    Example
    -------
    class MY_ShadingProfile(BL_BaseProfile):
        roughness: bpy.props.FloatProperty(name="Roughness", default=0.5)
        metallic:  bpy.props.FloatProperty(name="Metallic",  default=0.0)
    """
    # 'name' inherited — Blender auto-increments on collision ("Profile" → "Profile.001" …)
    profile_id: StringProperty(
        name="Profile ID",
        description="Unique identifier within this category. Auto-generated on creation.",
        default="",
    )
    tags: CollectionProperty(
        type=BL_ProfileTag,
        name="Tags",
    )
    active_tag_index: IntProperty(
        name="Active Tag Index",
        default=0,
        min=0,
    )


class BL_CategoryEntry(PropertyGroup):
    """
    One row in the top-level categories collection.

    The 'profiles' CollectionProperty is NOT declared here statically.
    It is patched onto this class dynamically by register_category() so that
    it can reference the caller's specific BL_BaseProfile subclass.
    That patch must happen BEFORE bpy.utils.register_class(BL_CategoryEntry).
    """
    category_id: StringProperty(
        name="Category ID",
        description="Frozen unique identifier matching the registered Python type",
        default="",
    )
    display_name: StringProperty(
        name="Display Name",
        default="",
    )
    storage_target: StringProperty(
        name="Storage Target",
        description="'scene' or 'preferences' — informational, set at registration",
        default="scene",
    )
    active_profile_index: IntProperty(
        name="Active Profile Index",
        default=0,
        min=0,
    )
    # 'profiles' is injected per-category — see _patch_category_entry_profiles()


class BL_ProfileContainer(PropertyGroup):
    """Attach one of these to bpy.types.Scene and/or your AddonPreferences."""
    categories: CollectionProperty(
        type=BL_CategoryEntry,
        name="Profile Categories",
    )


# ─────────────────────────────────────────────────────────────────────────────
# STORAGE ACCESS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_storage_root(storage: str, addon_id: Optional[str] = None):
    """Return the Blender ID that owns a BL_ProfileContainer."""
    if storage == "scene":
        return bpy.context.scene
    if storage == "preferences":
        if not addon_id:
            raise ValueError("addon_id is required when storage == 'preferences'")
        return bpy.context.preferences.addons[addon_id].preferences
    raise ValueError(f"Unknown storage target: '{storage!r}'")


def _get_container(storage: str, addon_id: Optional[str] = None) -> Optional[BL_ProfileContainer]:
    root = _get_storage_root(storage, addon_id)
    return getattr(root, "profile_manager", None)


def _get_bl_category(category_id: str) -> Optional[BL_CategoryEntry]:
    meta = _category_registry.get(category_id)
    if meta is None:
        return None
    container = _get_container(meta["storage"], meta.get("addon_id"))
    if container is None:
        return None
    return container.categories.get(category_id)


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC PROPERTY PATCHING
# ─────────────────────────────────────────────────────────────────────────────

def _patch_category_entry_profiles(profile_type: Type[BL_BaseProfile]) -> None:
    """
    Inject a 'profiles' CollectionProperty onto BL_CategoryEntry for the given
    profile_type.  Blender requires the annotation to exist on the class before
    register_class() is called, so call this early in your registration order.

    Because multiple categories each have a different profile_type we use a
    separate attribute name per type: 'profiles__<category_id>'.  BL_CategoryEntry
    exposes a convenience property 'profiles' that dispatches to the right one
    at runtime via category_id.
    """
    attr = f"profiles__{profile_type.__name__}"
    if not hasattr(BL_CategoryEntry, attr):
        annotation = CollectionProperty(type=profile_type)
        BL_CategoryEntry.__annotations__[attr] = annotation
        # Re-register BL_CategoryEntry so Blender picks up the new annotation.
        # Callers should ensure BL_CategoryEntry is initially registered AFTER
        # all patch calls, or call bpy.utils.unregister_class / register_class
        # here if it is already registered.


def _get_profiles_collection(cat_entry: BL_CategoryEntry, category_id: str):
    """Retrieve the correct per-type profiles collection from a category entry."""
    meta = _category_registry.get(category_id)
    if meta is None:
        return None
    attr = f"profiles__{meta['profile_type'].__name__}"
    return getattr(cat_entry, attr, None)


# ─────────────────────────────────────────────────────────────────────────────
# UILIST
# ─────────────────────────────────────────────────────────────────────────────

class PROFILEMANAGER_UL_profiles(UIList):
    """Generic UIList for any profile category. Draw via draw_profile_list()."""
    bl_idname = "PROFILEMANAGER_UL_profiles"

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False, icon="DOT")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name, icon="DOT")


def draw_profile_list(layout, category_id: str, context: Context) -> None:
    """
    Convenience function — call from any panel draw() to render the full
    profile list UI for a given category, including add/delete/duplicate
    operator buttons.

    Usage
    -----
    def draw(self, context):
        draw_profile_list(self.layout, "my_category_id", context)
    """
    cat_entry = _get_bl_category(category_id)
    if cat_entry is None:
        layout.label(text=f"Category '{category_id}' not found", icon="ERROR")
        return

    profiles = _get_profiles_collection(cat_entry, category_id)
    if profiles is None:
        layout.label(text="Profile collection unavailable", icon="ERROR")
        return

    row = layout.row()
    row.template_list(
        PROFILEMANAGER_UL_profiles.bl_idname,
        category_id,                        # list_id — unique per category
        cat_entry,
        f"profiles__{_category_registry[category_id]['profile_type'].__name__}",
        cat_entry,
        "active_profile_index",
        rows=4,
    )

    col = row.column(align=True)
    op = col.operator(PROFILE_OT_manage.bl_idname, text="", icon="ADD")
    op.action      = "CREATE"
    op.category_id = category_id

    op = col.operator(PROFILE_OT_manage.bl_idname, text="", icon="REMOVE")
    op.action      = "DELETE"
    op.category_id = category_id

    col.separator()

    op = col.operator(PROFILE_OT_manage.bl_idname, text="", icon="DUPLICATE")
    op.action      = "DUPLICATE"
    op.category_id = category_id


# ─────────────────────────────────────────────────────────────────────────────
# OPERATOR  —  create / delete / duplicate profiles
# ─────────────────────────────────────────────────────────────────────────────

class PROFILE_OT_manage(Operator):
    """Create, delete, or duplicate a profile within a category."""
    bl_idname      = "profile_manager.manage_profile"
    bl_label       = "Manage Profile"
    bl_options     = {"REGISTER", "UNDO"}

    action: bpy.props.EnumProperty(
        items=[
            ("CREATE",    "Create",    "Add a new profile"),
            ("DELETE",    "Delete",    "Remove the active profile"),
            ("DUPLICATE", "Duplicate", "Duplicate the active profile"),
        ],
        name="Action",
        default="CREATE",
    )
    category_id: StringProperty(name="Category ID", default="")

    def execute(self, context: Context):
        cat_entry = _get_bl_category(self.category_id)
        if cat_entry is None:
            self.report({"ERROR"}, f"Category '{self.category_id}' not found")
            return {"CANCELLED"}

        profiles = _get_profiles_collection(cat_entry, self.category_id)
        if profiles is None:
            self.report({"ERROR"}, "Profile collection unavailable")
            return {"CANCELLED"}

        if self.action == "CREATE":
            self._create(cat_entry, profiles)
        elif self.action == "DELETE":
            self._delete(cat_entry, profiles)
        elif self.action == "DUPLICATE":
            self._duplicate(cat_entry, profiles)

        # Keep RTC in sync after any mutation
        Profile_Manager_Wrapper.update_RTC_with_mirrored_BL_data(context.scene)
        return {"FINISHED"}

    # ------------------------------------------------------------------ #

    def _create(self, cat_entry: BL_CategoryEntry, profiles) -> None:
        new_profile = profiles.add()
        new_profile.name       = "Profile"          # Blender auto-increments to "Profile.001" etc.
        new_profile.profile_id = str(uuid.uuid4())
        cat_entry.active_profile_index = len(profiles) - 1
        log.debug("Created profile '%s' in category '%s'", new_profile.name, self.category_id)

    def _delete(self, cat_entry: BL_CategoryEntry, profiles) -> None:
        idx = cat_entry.active_profile_index
        if not (0 <= idx < len(profiles)):
            self.report({"WARNING"}, "No active profile to delete")
            return
        log.debug("Deleting profile '%s' from category '%s'",
                  profiles[idx].name, self.category_id)
        profiles.remove(idx)
        cat_entry.active_profile_index = max(0, idx - 1)

    def _duplicate(self, cat_entry: BL_CategoryEntry, profiles) -> None:
        idx = cat_entry.active_profile_index
        if not (0 <= idx < len(profiles)):
            self.report({"WARNING"}, "No active profile to duplicate")
            return
        src = profiles[idx]
        dst = profiles.add()

        # Copy all base-class scalar properties
        dst.name       = src.name            # Blender auto-increments the name
        dst.profile_id = str(uuid.uuid4())   # new unique ID

        # Copy tags
        for src_tag in src.tags:
            dst_tag         = dst.tags.add()
            dst_tag.name    = src_tag.name
            dst_tag.tag_id  = src_tag.tag_id

        # Copy caller-defined extra properties generically
        _copy_property_group(src, dst, exclude={"profile_id", "name", "tags"})

        cat_entry.active_profile_index = len(profiles) - 1
        log.debug("Duplicated '%s' → '%s' in category '%s'",
                  src.name, dst.name, self.category_id)


def _copy_property_group(src: PropertyGroup, dst: PropertyGroup,
                          exclude: set[str] = frozenset()) -> None:
    """
    Shallow-copy all RNA properties from src to dst, skipping CollectionProperty
    and PointerProperty (which require deeper handling) and anything in exclude.
    """
    for prop_name in src.bl_rna.properties.keys():
        if prop_name in exclude or prop_name in ("rna_type", "name"):
            continue
        rna_prop = src.bl_rna.properties[prop_name]
        if rna_prop.type in ("COLLECTION", "POINTER"):
            continue
        try:
            setattr(dst, prop_name, getattr(src, prop_name))
        except (AttributeError, TypeError):
            pass  # read-only or unsupported — skip silently


# ─────────────────────────────────────────────────────────────────────────────
# MAIN WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

class Profile_Manager_Wrapper(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """
    Singleton-style class.  All methods are @classmethod — never instantiate.

    Typical call order
    ------------------
    1.  Profile_Manager_Wrapper.register_category(...)   ← called once per type
    2.  Profile_Manager_Wrapper.init_pre_bpy()           ← patches PGs, bpy.utils.register_class(...)
    3.  bpy.utils.register_class(BL_ProfileContainer)    ← called by your main register()
    4.  Profile_Manager_Wrapper.init_post_bpy()          ← attaches container to Scene/Prefs
    5.  Profile_Manager_Wrapper.update_RTC_with_mirrored_BL_data(scene)    ← populates RTC on load/undo
    """

    # ------------------------------------------------------------------ #
    # Abstract_Feature_Wrapper
    # ------------------------------------------------------------------ #

    @classmethod
    def init_pre_bpy(cls, **kwargs) -> bool:
        """
        Patch BL_CategoryEntry with per-type CollectionProperties and
        register all PropertyGroup / UIList / Operator classes with Blender.
        Call this before your addon's main bpy.utils.register_class() loop
        if you handle registration manually, or integrate into it.
        """
        try:
            # 1. Patch BL_CategoryEntry for every registered category type
            for meta in _category_registry.values():
                _patch_category_entry_profiles(meta["profile_type"])

            # 2. Register Blender classes (order matters: inner types first)
            _bl_classes = [
                BL_ProfileTag,
                BL_BaseProfile,
                BL_CategoryEntry,
                BL_ProfileContainer,
                PROFILEMANAGER_UL_profiles,
                PROFILE_OT_manage,
            ]
            for cls_ in _bl_classes:
                try:
                    bpy.utils.register_class(cls_)
                except ValueError:
                    pass  # already registered

            # 3. Register caller-supplied profile subclasses
            for meta in _category_registry.values():
                try:
                    bpy.utils.register_class(meta["profile_type"])
                except ValueError:
                    pass

            log.info("Profile_Manager_Wrapper: init_pre_bpy OK")
            return True
        except Exception as exc:
            log.exception("Profile_Manager_Wrapper: init_pre_bpy FAILED: %s", exc)
            return False

    @classmethod
    def init_post_bpy(cls, **kwargs) -> bool:
        """
        Attach BL_ProfileContainer to Scene and/or AddonPreferences,
        then ensure a BL_CategoryEntry row exists for every registered category.
        Call this from your addon's post-registration hook.
        """
        try:
            # Attach container to Scene
            if not hasattr(bpy.types.Scene, "profile_manager"):
                bpy.types.Scene.profile_manager = bpy.props.PointerProperty(
                    type=BL_ProfileContainer
                )

            # Ensure BL_CategoryEntry rows exist for every registered category
            for category_id, meta in _category_registry.items():
                cls._ensure_category_entry(category_id, meta)

            log.info("Profile_Manager_Wrapper: init_post_bpy OK")
            return True
        except Exception as exc:
            log.exception("Profile_Manager_Wrapper: init_post_bpy FAILED: %s", exc)
            return False

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, scene, **kwargs) -> None:
        """
        Rebuild RTC from current Blender data. Scene/Prefs are the source of truth.
        Call on load, undo, redo, and from property update callbacks.
        """
        cat_rtc: dict = {}

        for category_id, meta in _category_registry.items():
            cat_entry = _get_bl_category(category_id)
            if cat_entry is None:
                continue

            cat_rtc[category_id] = cat_entry

            profiles = _get_profiles_collection(cat_entry, category_id)
            if profiles is None:
                continue

            profile_rtc = {p.profile_id: p for p in profiles if p.profile_id}
            Runtime_Cache.set_instance(_rtc_profiles_key(category_id), profile_rtc)

        Runtime_Cache.set_instance(_RTC_CATEGORIES_KEY, cat_rtc)
        log.debug("Profile_Manager_Wrapper: RTC rebuilt from BL (%d categories)", len(cat_rtc))

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, scene, **kwargs) -> None:
        """
        Write RTC state back into Blender data. RTC is the source of truth.
        Useful after bulk programmatic edits to RTC that need persistence.
        """
        cat_rtc: dict = Runtime_Cache.get_instance(_RTC_CATEGORIES_KEY) or {}

        for category_id, cat_entry in cat_rtc.items():
            meta     = _category_registry.get(category_id)
            profiles = _get_profiles_collection(cat_entry, category_id)
            if profiles is None:
                continue

            profile_rtc: dict = Runtime_Cache.get_instance(_rtc_profiles_key(category_id)) or {}

            # Sync names/ids back (other fields live in-place on the PG references)
            for profile_id, profile in profile_rtc.items():
                if profile not in profiles.values():
                    # Profile exists in RTC but was removed from BL — re-add
                    new_p            = profiles.add()
                    new_p.profile_id = profile_id
                    new_p.name       = profile.name
                    _copy_property_group(profile, new_p,
                                         exclude={"profile_id", "name", "tags"})

        log.debug("Profile_Manager_Wrapper: BL written from RTC")

    @classmethod
    def destroy_wrapper(cls, **kwargs) -> None:
        """
        Remove all RTC entries, unregister Blender classes, and detach the
        container from Scene/Prefs. Call from your addon's unregister().
        """
        # Clear RTC
        Runtime_Cache.destroy_instance(_RTC_CATEGORIES_KEY)
        for category_id in _category_registry:
            Runtime_Cache.destroy_instance(_rtc_profiles_key(category_id))

        # Detach container from Scene
        if hasattr(bpy.types.Scene, "profile_manager"):
            del bpy.types.Scene.profile_manager

        # Unregister Blender classes (reverse order)
        _bl_classes = [
            PROFILE_OT_manage,
            PROFILEMANAGER_UL_profiles,
            BL_ProfileContainer,
            BL_CategoryEntry,
        ]
        for meta in _category_registry.values():
            try:
                bpy.utils.unregister_class(meta["profile_type"])
            except RuntimeError:
                pass

        for cls_ in reversed(_bl_classes):
            try:
                bpy.utils.unregister_class(cls_)
            except RuntimeError:
                pass

        # Unregister shared base types last
        for cls_ in (BL_BaseProfile, BL_ProfileTag):
            try:
                bpy.utils.unregister_class(cls_)
            except RuntimeError:
                pass

        _category_registry.clear()
        log.info("Profile_Manager_Wrapper: destroyed")

    # ------------------------------------------------------------------ #
    # Abstract_Datawrapper_Instance_Manager  (instance == profile)
    # ------------------------------------------------------------------ #

    @classmethod
    def create_instance(cls, *, category_id: str, name: str = "Profile", **kwargs):
        """
        Programmatically create a new profile in the given category.
        Returns the new profile PropertyGroup instance, or None on failure.
        """
        cat_entry = _get_bl_category(category_id)
        if cat_entry is None:
            log.error("create_instance: unknown category '%s'", category_id)
            return None

        profiles = _get_profiles_collection(cat_entry, category_id)
        if profiles is None:
            return None

        new_profile            = profiles.add()
        new_profile.name       = name          # Blender auto-increments on collision
        new_profile.profile_id = str(uuid.uuid4())

        # Write any extra kwargs onto the profile
        for key, val in kwargs.items():
            if hasattr(new_profile, key):
                try:
                    setattr(new_profile, key, val)
                except TypeError:
                    pass

        cat_entry.active_profile_index = len(profiles) - 1

        # Update RTC
        profile_rtc = Runtime_Cache.get_instance(_rtc_profiles_key(category_id)) or {}
        profile_rtc[new_profile.profile_id] = new_profile
        Runtime_Cache.set_instance(_rtc_profiles_key(category_id), profile_rtc)

        log.debug("create_instance: created '%s' [%s] in '%s'",
                  new_profile.name, new_profile.profile_id, category_id)
        return new_profile

    @classmethod
    def get_instance(cls, *, category_id: str, profile_id: str, **kwargs):
        """
        Return a profile by its profile_id from the RTC, or None.
        Falls back to a linear BL search if the RTC is cold.
        """
        profile_rtc: dict = Runtime_Cache.get_instance(_rtc_profiles_key(category_id)) or {}
        if profile_id in profile_rtc:
            return profile_rtc[profile_id]

        # Cold-cache fallback
        cat_entry = _get_bl_category(category_id)
        if cat_entry is None:
            return None
        profiles = _get_profiles_collection(cat_entry, category_id)
        if profiles is None:
            return None
        return next((p for p in profiles if p.profile_id == profile_id), None)

    @classmethod
    def set_instance(cls, *, category_id: str, profile_id: str, **kwargs) -> None:
        """
        Update arbitrary properties on an existing profile by profile_id.
        kwargs keys must match PropertyGroup attribute names.
        """
        profile = cls.get_instance(category_id=category_id, profile_id=profile_id)
        if profile is None:
            log.warning("set_instance: profile '%s' not found in '%s'", profile_id, category_id)
            return
        for key, val in kwargs.items():
            if hasattr(profile, key):
                try:
                    setattr(profile, key, val)
                except TypeError:
                    log.warning("set_instance: could not set '%s' on profile", key)

    @classmethod
    def destroy_instance(cls, *, category_id: str, profile_id: str, **kwargs) -> None:
        """Remove a profile by profile_id from both BL storage and the RTC."""
        cat_entry = _get_bl_category(category_id)
        if cat_entry is None:
            return
        profiles = _get_profiles_collection(cat_entry, category_id)
        if profiles is None:
            return

        idx = next((i for i, p in enumerate(profiles) if p.profile_id == profile_id), None)
        if idx is None:
            log.warning("destroy_instance: profile '%s' not found in BL", profile_id)
            return

        profiles.remove(idx)
        cat_entry.active_profile_index = max(0, cat_entry.active_profile_index - 1)

        profile_rtc: dict = Runtime_Cache.get_instance(_rtc_profiles_key(category_id)) or {}
        profile_rtc.pop(profile_id, None)
        Runtime_Cache.set_instance(_rtc_profiles_key(category_id), profile_rtc)

        log.debug("destroy_instance: removed '%s' from '%s'", profile_id, category_id)

    # ------------------------------------------------------------------ #
    # Category management
    # ------------------------------------------------------------------ #

    @classmethod
    def register_category(
        cls,
        category_id:   str,
        display_name:  str,
        profile_type:  Type[BL_BaseProfile],
        storage:       str = "scene",
        addon_id:      Optional[str] = None,
    ) -> bool:
        """
        Declare a new category (= a profile type).

        Parameters
        ----------
        category_id   : Frozen unique string key.  Use snake_case.
        display_name  : Human-readable label shown in the UI.
        profile_type  : A BL_BaseProfile subclass. This IS the category's type.
        storage       : "scene" (default) | "preferences"
        addon_id      : Required when storage == "preferences".

        Returns True if registration succeeded, False if category_id is taken.
        """
        if not cls.validate_category_id(category_id):
            return False

        if not issubclass(profile_type, BL_BaseProfile):
            log.error("register_category: '%s' — profile_type must subclass BL_BaseProfile",
                      category_id)
            return False

        _category_registry[category_id] = {
            "category_id":  category_id,
            "display_name": display_name,
            "storage":      storage,
            "profile_type": profile_type,
            "addon_id":     addon_id,
        }
        log.info("register_category: '%s' registered (type=%s, storage=%s)",
                 category_id, profile_type.__name__, storage)
        return True

    @classmethod
    def unregister_category(cls, category_id: str) -> bool:
        """
        Remove a category from the registry and clean up its BL storage row
        and RTC entry.  Does NOT unregister the caller's profile_type class
        from Blender (caller's responsibility).
        """
        if category_id not in _category_registry:
            log.warning("unregister_category: '%s' not found", category_id)
            return False

        # Remove BL category entry
        meta      = _category_registry[category_id]
        container = _get_container(meta["storage"], meta.get("addon_id"))
        if container is not None:
            idx = container.categories.find(category_id)
            if idx >= 0:
                container.categories.remove(idx)

        # Clear RTC
        Runtime_Cache.destroy_instance(_rtc_profiles_key(category_id))
        cat_rtc: dict = Runtime_Cache.get_instance(_RTC_CATEGORIES_KEY) or {}
        cat_rtc.pop(category_id, None)
        Runtime_Cache.set_instance(_RTC_CATEGORIES_KEY, cat_rtc)

        del _category_registry[category_id]
        log.info("unregister_category: '%s' removed", category_id)
        return True

    @classmethod
    def validate_category_id(cls, category_id: str) -> bool:
        """
        Return True if category_id is valid and not already taken.
        A valid ID is a non-empty string containing only alphanumerics and underscores.
        """
        import re
        if not category_id:
            log.error("validate_category_id: empty category_id")
            return False
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", category_id):
            log.error("validate_category_id: '%s' contains invalid characters", category_id)
            return False
        if category_id in _category_registry:
            log.error("validate_category_id: '%s' already registered", category_id)
            return False
        return True

    # ------------------------------------------------------------------ #
    # Tag management helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def add_tag(
        cls,
        category_id: str,
        profile_id:  str,
        tag_name:    str,
        tag_id:      Optional[int] = None,
    ) -> Optional[BL_ProfileTag]:
        """
        Add a tag to a profile.  tag_id is auto-assigned if not provided.
        Returns the new BL_ProfileTag or None on failure.
        Enforces uniqueness of both name and tag_id within the profile.
        """
        profile = cls.get_instance(category_id=category_id, profile_id=profile_id)
        if profile is None:
            log.error("add_tag: profile '%s' not found", profile_id)
            return None

        # Uniqueness checks
        existing_names  = {t.name   for t in profile.tags}
        existing_ids    = {t.tag_id for t in profile.tags}

        if tag_name in existing_names:
            log.warning("add_tag: tag name '%s' already exists on profile '%s'",
                        tag_name, profile_id)
            return None

        if tag_id is None:
            tag_id = max(existing_ids, default=-1) + 1
        elif tag_id in existing_ids:
            log.warning("add_tag: tag_id %d already exists on profile '%s'", tag_id, profile_id)
            return None

        new_tag         = profile.tags.add()
        new_tag.name    = tag_name
        new_tag.tag_id  = tag_id
        return new_tag

    @classmethod
    def remove_tag(cls, category_id: str, profile_id: str, tag_name: str) -> bool:
        """Remove a tag by name from a profile. Returns True on success."""
        profile = cls.get_instance(category_id=category_id, profile_id=profile_id)
        if profile is None:
            return False
        idx = profile.tags.find(tag_name)
        if idx < 0:
            log.warning("remove_tag: tag '%s' not found on profile '%s'", tag_name, profile_id)
            return False
        profile.tags.remove(idx)
        return True

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @classmethod
    def _ensure_category_entry(cls, category_id: str, meta: dict) -> None:
        """Create the BL_CategoryEntry row if it doesn't already exist."""
        container = _get_container(meta["storage"], meta.get("addon_id"))
        if container is None:
            log.error("_ensure_category_entry: container not found for '%s'", category_id)
            return

        if container.categories.get(category_id) is None:
            entry               = container.categories.add()
            entry.category_id   = category_id
            entry.display_name  = meta["display_name"]
            entry.storage_target = meta["storage"]
            log.debug("_ensure_category_entry: created BL row for '%s'", category_id)


# ─────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE  (illustrative — not executed at import)
# ─────────────────────────────────────────────────────────────────────────────

def _usage_example():
    """
    How a calling module uses Profile_Manager_Wrapper.

        # 1. Define your profile type (= your category type)
        class ShadingProfile(BL_BaseProfile):
            roughness: bpy.props.FloatProperty(name="Roughness", default=0.5)
            metallic:  bpy.props.FloatProperty(name="Metallic",  default=0.0)

        # 2. Register the category once, before init_pre_bpy
        Profile_Manager_Wrapper.register_category(
            category_id  = "shading_profiles",
            display_name = "Shading Profiles",
            profile_type = ShadingProfile,
            storage      = "scene",
        )

        # 3. In your addon register():
        Profile_Manager_Wrapper.init_pre_bpy()
        # ... rest of bpy.utils.register_class calls ...
        Profile_Manager_Wrapper.init_post_bpy()
        Profile_Manager_Wrapper.update_RTC_with_mirrored_BL_data(bpy.context.scene)

        # 4. In a panel draw():
        draw_profile_list(layout, "shading_profiles", context)

        # 5. Programmatic creation:
        p = Profile_Manager_Wrapper.create_instance(
            category_id = "shading_profiles",
            name        = "My Shader",
            roughness   = 0.3,
        )

        # 6. Tag management:
        Profile_Manager_Wrapper.add_tag("shading_profiles", p.profile_id, "production")

        # 7. In your addon unregister():
        Profile_Manager_Wrapper.destroy_wrapper()
    """
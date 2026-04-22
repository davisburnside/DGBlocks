from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import bpy  # type: ignore
from bpy.props import CollectionProperty, PointerProperty, StringProperty  # type: ignore
from bpy.types import AddonPreferences, Operator, PropertyGroup, UILayout  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ....my_addon_config import addon_name

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .feature_runtime_cache import Wrapper_Runtime_Cache
from ..core_data.data_structures import Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager

_RTC = Wrapper_Runtime_Cache

#================================================================================
# RTC KEY CONSTANTS
#================================================================================

_RTC_INSTANCES = "profile_manager/instances"   # dict[uid, ProfileInstance]
_RTC_REGISTRY  = "profile_manager/registry"    # dict[category, list[type]]
_RTC_PREFS_CLS = "profile_manager/prefs_cls"   # type | None


#================================================================================
# RUNTIME DATACLASS  –  one per profile, lives entirely in Python memory
#================================================================================

@dataclass
class ProfileInstance:
    """
    Runtime representation of a single profile.  No bpy.* objects stored here.

    uid              : stable ID matching DGBLOCKS_PG_ProfileStateItem.uid
    category         : Block category string
    profile_type     : bl_idname / __name__ of the concrete PG class
    name             : mirrors bl_item.data.name; kept in sync on save
    is_editing       : True while the edit form is open
    is_new_duplicate : True for a duplicate that hasn't been confirmed yet;
                       Cancel will delete the entry rather than reverting it
    snapshot         : plain-Python-dict copy of data props captured at
                       begin_edit.  Empty dict when not in edit mode.
    """
    uid:               str  = field(default_factory=lambda: str(uuid.uuid4()))
    category:          str  = ""
    profile_type:      str  = ""
    name:              str  = "Profile"
    is_editing:        bool = False
    is_new_duplicate:  bool = False
    snapshot:          dict = field(default_factory=dict)

#================================================================================
# BLENDER PROPERTY GROUPS  –  persistence layer only, no runtime state here
#================================================================================

class DGBLOCKS_PG_ProfileBase(PropertyGroup):
    """
    Base class for all Block profile PropertyGroups.
    Subclass this and add your Block's own bpy.props.
    ``name`` is inherited from Blender's PropertyGroup.
    """
    pass


class DGBLOCKS_PG_ProfileStateItem(PropertyGroup):
    """
    One slot in AddonPreferences.profiles.
    ``uid`` links this Blender item to its ProfileInstance in the RTC.
    All edit-mode state (is_editing, snapshot, is_new_duplicate) lives in the
    RTC ProfileInstance — never in this PropertyGroup.
    """
    uid: StringProperty(
        name="UID",
        description="Stable link to the ProfileInstance in the Runtime-Cache",
        default="",
    )  # type: ignore
    category:     StringProperty(default="")  # type: ignore
    profile_type: StringProperty(default="")  # type: ignore

    # Polymorphic payload – concrete subclass varies per Block
    data: PointerProperty(type=DGBLOCKS_PG_ProfileBase)  # type: ignore


#================================================================================
# PURE-PYTHON HELPERS  –  no bpy.* references beyond function arguments
#================================================================================

def _get_prefs() -> Optional[AddonPreferences]:
    """Return the addon AddonPreferences instance, or None."""
    if _RTC.get_instance(_RTC_PREFS_CLS) is None:
        return None
    try:
        return bpy.context.preferences.addons[addon_name].preferences
    except Exception:
        return None


def _unique_name(base: str, existing: list[str], exclude: str = "") -> str:
    """Return a Blender-style unique name, appending .001/.002/… as needed."""
    candidates = [n for n in existing if n != exclude]
    if base not in candidates:
        return base
    m = re.match(r"^(.*?)\.(\d{3})$", base)
    stem = m.group(1) if m else base
    idx = 1
    while True:
        candidate = f"{stem}.{idx:03d}"
        if candidate not in candidates:
            return candidate
        idx += 1


def _all_profile_names_in_category(category: str) -> list[str]:
    prefs = _get_prefs()
    if prefs is None:
        return []
    return [item.data.name for item in prefs.profiles if item.category == category]


def _resolve_pg_class(type_id: str, category: str) -> Optional[type]:
    registry: dict = _RTC.get_instance(_RTC_REGISTRY) or {}
    for pg_class in registry.get(category, []):
        cid = getattr(pg_class, "bl_idname", pg_class.__name__)
        if cid == type_id:
            return pg_class
    return None


def _capture_snapshot(bl_data: PropertyGroup) -> dict:
    """
    Read user-visible scalar/array props from *bl_data* into a plain Python
    dict (RTC-safe).  Uses sync_blender_propertygroup_and_raw_python with an
    empty template dict so every key is auto-discovered.
    """
    # Build a shallow template from the live PG to drive key discovery
    template: dict = {}
    for prop_name, rna_prop in bl_data.bl_rna.properties.items():
        if prop_name in ("rna_type", "name"):
            continue
        if rna_prop.type in ("POINTER", "COLLECTION"):
            continue
        template[prop_name] = None  # value doesn't matter; only key matters

    return Wrapper_Runtime_Cache.sync_blender_propertygroup_and_raw_python(
        bl_data, template, blender_as_truth_source=False
    )


def _restore_snapshot(bl_data: PropertyGroup, snapshot: dict) -> None:
    """Write *snapshot* dict back into *bl_data* (RTC → Blender)."""
    Wrapper_Runtime_Cache.sync_blender_propertygroup_and_raw_python(
        bl_data, snapshot, blender_as_truth_source=True
    )

#================================================================================
# CORE_PROFILE_MANAGER_WRAPPER
#================================================================================

class Core_Profile_Manager_Wrapper(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """
    Feature wrapper — classmethods only, no instance state.
    Manages named profiles stored in AddonPreferences.

    All runtime state (is_editing, snapshots, is_new_duplicate) lives in the
    Runtime-Cache via ProfileInstance dataclasses.  Blender PropertyGroups are
    the persistence layer only.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Abstract_Feature_Wrapper
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def init_pre_bpy(cls, prefs_cls: type = None, **kwargs) -> bool:
        """Initialise empty RTC buckets before any bpy classes are registered."""
        if _RTC.get_instance(_RTC_INSTANCES) is None:
            _RTC.set_instance(_RTC_INSTANCES, {})
        if _RTC.get_instance(_RTC_REGISTRY) is None:
            _RTC.set_instance(_RTC_REGISTRY, {})
        if _RTC.get_instance(_RTC_PREFS_CLS) is None:
            _RTC.set_instance(_RTC_PREFS_CLS, prefs_cls)
        return True

    @classmethod
    def init_post_bpy(cls, prefs_cls: type = None, **kwargs) -> bool:
        """Bind prefs class, then rebuild RTC from persisted Blender data."""
        if prefs_cls is not None:
            _RTC.set_instance(_RTC_PREFS_CLS, prefs_cls)
        cls.update_BL_with_mirrored_RTC_data(scene=kwargs.get("scene"))
        return True

    @classmethod
    def update_RTC_with_mirrored_BL_data(cls, scene=None, **kwargs):
        """
        Blender is truth → refresh lightweight bookkeeping fields
        (name, category, profile_type) in each ProfileInstance.

        If an item is currently being edited, push its snapshot back into
        Blender so in-progress edits survive undo/redo rebuilds.
        """
        prefs = _get_prefs()
        if prefs is None:
            return
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        for bl_item in prefs.profiles:
            inst = instances.get(bl_item.uid)
            if inst is None:
                continue
            inst.name         = bl_item.data.name
            inst.category     = bl_item.category
            inst.profile_type = bl_item.profile_type
            if inst.is_editing and inst.snapshot:
                _restore_snapshot(bl_item.data, inst.snapshot)
        _RTC.set_instance(_RTC_INSTANCES, instances)

    @classmethod
    def update_BL_with_mirrored_RTC_data(cls, scene=None, **kwargs):
        """
        Blender is truth → read all PG items and create / refresh
        ProfileInstance objects in the RTC.  Called on init and load/undo.
        """
        prefs = _get_prefs()
        if prefs is None:
            return
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}

        for bl_item in prefs.profiles:
            uid = bl_item.uid
            if not uid:
                uid = str(uuid.uuid4())
                bl_item.uid = uid

            if uid not in instances:
                instances[uid] = ProfileInstance(
                    uid=uid,
                    category=bl_item.category,
                    profile_type=bl_item.profile_type,
                    name=bl_item.data.name,
                )
            else:
                inst = instances[uid]
                inst.category     = bl_item.category
                inst.profile_type = bl_item.profile_type
                inst.name         = bl_item.data.name

        # Prune RTC entries whose Blender counterpart was deleted
        bl_uids = {item.uid for item in prefs.profiles}
        for uid in list(instances.keys()):
            if uid not in bl_uids:
                del instances[uid]

        _RTC.set_instance(_RTC_INSTANCES, instances)

    @classmethod
    def destroy_wrapper(cls, **kwargs):
        """Clear all RTC buckets owned by this wrapper.  Call during unregister."""
        _RTC.destroy_instance(_RTC_INSTANCES)
        _RTC.destroy_instance(_RTC_REGISTRY)
        _RTC.destroy_instance(_RTC_PREFS_CLS)

    # ══════════════════════════════════════════════════════════════════════════
    # Abstract_Datawrapper_Instance_Manager
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def create_instance(
        cls,
        category: str = "",
        pg_class: type = None,
        name: str = "Profile",
        **kwargs,
    ) -> Optional[ProfileInstance]:
        """Add a new ProfileInstance + matching Blender PG item."""
        prefs = _get_prefs()
        if prefs is None or pg_class is None:
            return None

        uid    = str(uuid.uuid4())
        unique = _unique_name(name, _all_profile_names_in_category(category))

        bl_item: DGBLOCKS_PG_ProfileStateItem = prefs.profiles.add()
        bl_item.uid          = uid
        bl_item.category     = category
        bl_item.profile_type = getattr(pg_class, "bl_idname", pg_class.__name__)
        bl_item.data.name    = unique

        inst = ProfileInstance(
            uid=uid,
            category=category,
            profile_type=bl_item.profile_type,
            name=unique,
        )
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        instances[uid]  = inst
        _RTC.set_instance(_RTC_INSTANCES, instances)
        return inst

    @classmethod
    def get_instance(cls, uid: str = None, **kwargs) -> Optional[ProfileInstance]:
        """Return the ProfileInstance for *uid*, or None."""
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        return instances.get(uid)

    @classmethod
    def set_instance(cls, uid: str = None, instance: ProfileInstance = None, **kwargs):
        """Write (replace) a ProfileInstance in the RTC and mirror its name to Blender."""
        if uid is None or instance is None:
            return
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        instances[uid]  = instance
        _RTC.set_instance(_RTC_INSTANCES, instances)
        prefs = _get_prefs()
        if prefs:
            for bl_item in prefs.profiles:
                if bl_item.uid == uid:
                    bl_item.data.name = instance.name
                    break

    @classmethod
    def destroy_instance(cls, uid: str = None, **kwargs):
        """Remove a ProfileInstance from the RTC and its Blender PG item."""
        if uid is None:
            return
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        instances.pop(uid, None)
        _RTC.set_instance(_RTC_INSTANCES, instances)
        prefs = _get_prefs()
        if prefs:
            for i, bl_item in enumerate(prefs.profiles):
                if bl_item.uid == uid:
                    prefs.profiles.remove(i)
                    break

    # ══════════════════════════════════════════════════════════════════════════
    # Additional public methods
    # ══════════════════════════════════════════════════════════════════════════

    @classmethod
    def register_profile_type(cls, category: str, pg_class: type) -> None:
        """Register *pg_class* under *category* so the UI can offer an Add button."""
        if not (isinstance(pg_class, type) and issubclass(pg_class, DGBLOCKS_PG_ProfileBase)):
            raise TypeError(f"{pg_class} must be a subclass of DGBLOCKS_PG_ProfileBase")
        registry: dict = _RTC.get_instance(_RTC_REGISTRY) or {}
        registry.setdefault(category, [])
        if pg_class not in registry[category]:
            registry[category].append(pg_class)
        _RTC.set_instance(_RTC_REGISTRY, registry)

    @classmethod
    def bind_prefs_class(cls, prefs_cls: type) -> None:
        """Late-bind which AddonPreferences class to use for profile storage."""
        _RTC.set_instance(_RTC_PREFS_CLS, prefs_cls)

    @classmethod
    def get_instances_for_category(cls, category: str) -> list[tuple[str, ProfileInstance]]:
        """Return [(uid, ProfileInstance), ...] for every profile in *category*."""
        instances: dict = _RTC.get_instance(_RTC_INSTANCES) or {}
        return [(uid, inst) for uid, inst in instances.items() if inst.category == category]

    # ── Edit / Save / Cancel ─────────────────────────────────────────────────

    @classmethod
    def begin_edit(cls, uid: str) -> bool:
        """
        Enter edit mode.  Snapshot current Blender PG values → RTC dict.
        Returns True on success.
        """
        inst    = cls.get_instance(uid=uid)
        bl_item = cls._get_bl_item(uid)
        if inst is None or bl_item is None:
            return False

        inst.snapshot   = _capture_snapshot(bl_item.data)
        inst.is_editing = True
        cls.set_instance(uid=uid, instance=inst)
        return True

    @classmethod
    def validate_edit(cls, uid: str) -> bool:
        """
        Placeholder validation.  Returns False ~25 % of the time to simulate
        a validation failure (replace with real logic later).
        """
        import random
        return random.random() >= 0.25

    @classmethod
    def save_edit(cls, uid: str) -> bool:
        """
        Confirm current Blender PG values, enforce category-unique naming, exit
        edit mode.  Calls validate_edit first; returns False without saving if
        validation fails.
        """
        if not cls.validate_edit(uid):
            return False

        inst    = cls.get_instance(uid=uid)
        bl_item = cls._get_bl_item(uid)
        if inst is None or bl_item is None:
            return False

        existing = _all_profile_names_in_category(inst.category)
        unique   = _unique_name(bl_item.data.name, existing, exclude=bl_item.data.name)
        if unique != bl_item.data.name:
            bl_item.data.name = unique

        inst.name             = bl_item.data.name
        inst.snapshot         = {}
        inst.is_editing       = False
        inst.is_new_duplicate = False
        cls.set_instance(uid=uid, instance=inst)
        return True

    @classmethod
    def cancel_edit(cls, uid: str) -> bool:
        """
        Cancel edit mode.
        - is_new_duplicate=True → delete the entry and return True.
        - Otherwise → restore snapshot into Blender PG and return False.
        """
        inst = cls.get_instance(uid=uid)
        if inst is None:
            return False

        if inst.is_new_duplicate:
            cls.destroy_instance(uid=uid)
            return True

        bl_item = cls._get_bl_item(uid)
        if bl_item is not None and inst.snapshot:
            _restore_snapshot(bl_item.data, inst.snapshot)
            bl_item.data.name = inst.name  # name is excluded from data snapshot

        inst.snapshot   = {}
        inst.is_editing = False
        cls.set_instance(uid=uid, instance=inst)
        return False

    # ── Duplicate ─────────────────────────────────────────────────────────────

    @classmethod
    def duplicate_profile(cls, source_uid: str) -> Optional[ProfileInstance]:
        """
        Copy an existing profile.  The duplicate immediately enters edit mode
        with is_new_duplicate=True so Cancel will delete it.
        """
        source_inst = cls.get_instance(uid=source_uid)
        source_bl   = cls._get_bl_item(source_uid)
        if source_inst is None or source_bl is None:
            return None

        pg_class = _resolve_pg_class(source_inst.profile_type, source_inst.category)
        if pg_class is None:
            return None

        new_inst = cls.create_instance(
            category=source_inst.category,
            pg_class=pg_class,
            name=source_inst.name,
        )
        if new_inst is None:
            return None

        # Copy source Blender PG values into the new item
        new_bl = cls._get_bl_item(new_inst.uid)
        if new_bl:
            preserved_name = new_bl.data.name
            source_snapshot = _capture_snapshot(source_bl.data)
            _restore_snapshot(new_bl.data, source_snapshot)
            new_bl.data.name = preserved_name

        new_inst.is_new_duplicate = True
        cls.set_instance(uid=new_inst.uid, instance=new_inst)
        cls.begin_edit(new_inst.uid)
        return new_inst

    # ── Utility ───────────────────────────────────────────────────────────────

    @classmethod
    def get_profile_values(cls, uid: str, prop_names: list[str]) -> list[Any]:
        """
        Return values of *prop_names* from the live Blender PG (reflects
        in-progress edits when is_editing=True).

        Raises LookupError, AttributeError, or TypeError on bad input.
        """
        bl_item = cls._get_bl_item(uid)
        if bl_item is None:
            raise LookupError(f"No Blender profile item found for uid='{uid}'")

        result = []
        for prop_name in prop_names:
            if not hasattr(bl_item.data, prop_name):
                raise AttributeError(
                    f"get_profile_values: '{prop_name}' not found on "
                    f"{bl_item.data.__class__.__name__}"
                )
            rna_prop = bl_item.data.bl_rna.properties.get(prop_name)
            if rna_prop is None:
                raise AttributeError(
                    f"get_profile_values: '{prop_name}' has no RNA descriptor"
                )
            if rna_prop.type in ("POINTER", "COLLECTION"):
                raise TypeError(
                    f"get_profile_values: '{prop_name}' is type "
                    f"'{rna_prop.type}' – only scalar/array props are supported."
                )
            val = getattr(bl_item.data, prop_name)
            result.append(list(val) if rna_prop.is_array else val)
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _get_bl_item(cls, uid: str) -> Optional[DGBLOCKS_PG_ProfileStateItem]:
        """Return the Blender PG item matching *uid*, or None."""
        prefs = _get_prefs()
        if prefs is None:
            return None
        for item in prefs.profiles:
            if item.uid == uid:
                return item
        return None

#================================================================================
# OPERATORS  –  thin Blender-side delegates; all logic lives in the wrapper
#================================================================================

class DGBLOCKS_OT_ProfileAdd(Operator):
    bl_idname  = "dgblocks.profile_add"
    bl_label   = "Add Profile"
    bl_options = {"INTERNAL", "UNDO"}

    category:     StringProperty()  # type: ignore
    profile_type: StringProperty()  # type: ignore

    def execute(self, context):
        pg_class = _resolve_pg_class(self.profile_type, self.category)
        if pg_class is None:
            self.report({"ERROR"}, f"Unknown profile type: {self.profile_type}")
            return {"CANCELLED"}
        inst = Core_Profile_Manager_Wrapper.create_instance(
            category=self.category, pg_class=pg_class
        )
        if inst:
            Core_Profile_Manager_Wrapper.begin_edit(inst.uid)
        return {"FINISHED"}


class DGBLOCKS_OT_ProfileEdit(Operator):
    bl_idname  = "dgblocks.profile_edit"
    bl_label   = "Edit Profile"
    bl_options = {"INTERNAL", "UNDO"}

    uid: StringProperty()  # type: ignore

    def execute(self, context):
        Core_Profile_Manager_Wrapper.begin_edit(self.uid)
        return {"FINISHED"}


class DGBLOCKS_OT_ProfileSave(Operator):
    bl_idname  = "dgblocks.profile_save"
    bl_label   = "Save Profile"
    bl_options = {"INTERNAL", "UNDO"}

    uid: StringProperty()  # type: ignore

    def execute(self, context):
        saved = Core_Profile_Manager_Wrapper.save_edit(self.uid)
        if not saved:
            self.report({"WARNING"}, "Validation failed — profile not saved.")
            return {"CANCELLED"}
        return {"FINISHED"}


class DGBLOCKS_OT_ProfileCancel(Operator):
    bl_idname  = "dgblocks.profile_cancel"
    bl_label   = "Cancel Edit"
    bl_options = {"INTERNAL", "UNDO"}

    uid: StringProperty()  # type: ignore

    def execute(self, context):
        Core_Profile_Manager_Wrapper.cancel_edit(self.uid)
        return {"FINISHED"}


class DGBLOCKS_OT_ProfileDuplicate(Operator):
    bl_idname  = "dgblocks.profile_duplicate"
    bl_label   = "Duplicate Profile"
    bl_options = {"INTERNAL", "UNDO"}

    uid: StringProperty()  # type: ignore

    def execute(self, context):
        Core_Profile_Manager_Wrapper.duplicate_profile(self.uid)
        return {"FINISHED"}


class DGBLOCKS_OT_ProfileDeleteConfirm(Operator):
    bl_idname  = "dgblocks.profile_delete_confirm"
    bl_label   = "Delete Profile?"
    bl_options = {"INTERNAL"}

    uid: StringProperty()  # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        Core_Profile_Manager_Wrapper.destroy_instance(uid=self.uid)
        return {"FINISHED"}

#================================================================================
# UI ENGINE
#================================================================================

# ------------------------------------------------------------
# UIList – one row per profile (header / action buttons only)
# ------------------------------------------------------------

class DGBLOCKS_UL_Profiles(bpy.types.UIList):
    """
    Displays one profile per row.
    Row content:
      - Name field (editable only when ProfileInstance.is_editing=True)
      - Edit / Save(+validate) / Cancel / Duplicate / Delete buttons
    The expanded property-detail panel is drawn below the list by
    draw_profiles_ui(), which calls draw_profile_props() for the active item.
    """

    bl_idname = "DGBLOCKS_UL_Profiles"

    def draw_item(
        self, context, layout, data, item, icon,
        active_data, active_propname, index,
    ):
        uid  = item.uid
        inst = Core_Profile_Manager_Wrapper.get_instance(uid=uid)
        if inst is None:
            layout.label(text="(orphan)", icon="ERROR")
            return

        row = layout.row(align=True)

        # Name field – active (editable) only while in edit mode
        name_col = row.row()
        name_col.enabled = inst.is_editing
        name_col.prop(item.data, "name", text="", emboss=inst.is_editing)

        # Action buttons
        if inst.is_editing:
            op = row.operator(DGBLOCKS_OT_ProfileSave.bl_idname, text="", icon="CHECKMARK")
            op.uid = uid

            op = row.operator(DGBLOCKS_OT_ProfileCancel.bl_idname, text="", icon="X")
            op.uid = uid
        else:
            op = row.operator(DGBLOCKS_OT_ProfileEdit.bl_idname, text="", icon="GREASEPENCIL")
            op.uid = uid

            op = row.operator(DGBLOCKS_OT_ProfileDuplicate.bl_idname, text="", icon="DUPLICATE")
            op.uid = uid

            op = row.operator(DGBLOCKS_OT_ProfileDeleteConfirm.bl_idname, text="", icon="TRASH")
            op.uid = uid


# ------------------------------------------------------------
# Property detail drawer (recursive bl_rna inspection)
# ------------------------------------------------------------

def draw_profile_props(layout: UILayout, pg: PropertyGroup, editable: bool) -> None:
    """
    Draw every user-facing scalar/array property on *pg*.
    POINTER / COLLECTION props are skipped (use a dedicated sub-panel if needed).
    When *editable* is False the column is greyed out (layout.enabled = False).
    """
    col = layout.column(align=True)
    col.enabled = editable

    for prop_name, rna_prop in pg.bl_rna.properties.items():
        if prop_name in ("rna_type", "name"):
            continue
        if rna_prop.type in ("POINTER", "COLLECTION"):
            continue
        col.prop(pg, prop_name)


# ------------------------------------------------------------
# Public entry-point: draw a category's full UIList + detail
# ------------------------------------------------------------

def draw_profiles_ui(
    layout: UILayout,
    category: str,
    show_add: bool = True,
) -> None:
    """
    Draw the complete profile UI for *category*:
      1. Header row with category label and Add button(s).
      2. DGBLOCKS_UL_Profiles UIList (all profiles as rows).
      3. Property detail panel for the currently selected profile.

    The UIList active-index is stored on the AddonPreferences object at
    runtime via a temporary int attribute (no bpy.props needed).
    """
    prefs = _get_prefs()
    if prefs is None:
        layout.label(text="AddonPreferences not found!", icon="ERROR")
        return

    # Collect items belonging to this category
    cat_items = [
        item for item in prefs.profiles
        if item.category == category
    ]

    # ── Header + Add button(s) ────────────────────────────────────────────────
    header = layout.row()
    header.label(text=category, icon="PRESET")

    if show_add:
        registry: dict = _RTC.get_instance(_RTC_REGISTRY) or {}
        for pg_class in registry.get(category, []):
            type_id = getattr(pg_class, "bl_idname", pg_class.__name__)
            op = header.operator(DGBLOCKS_OT_ProfileAdd.bl_idname, text="", icon="ADD")
            op.category     = category
            op.profile_type = type_id

    layout.separator(factor=0.4)

    if not cat_items:
        layout.label(text="No profiles yet.", icon="INFO")
        return

    # ── UIList ────────────────────────────────────────────────────────────────
    # Active-index is stored as a transient Python attribute on the prefs
    # object (not a bpy.props, so it resets on reload – that is intentional).
    active_key = f"_profile_list_active_{category.replace(' ', '_')}"
    if not hasattr(prefs, active_key):
        object.__setattr__(prefs, active_key, 0)

    active_index = getattr(prefs, active_key, 0)
    active_index = max(0, min(active_index, len(cat_items) - 1))

    # UIList draws from AddonPreferences.profiles filtered to this category.
    # Because CollectionProperty can't be easily filtered in-place, we draw
    # the full collection but rely on draw_item to show only matching rows.
    # For the active-index we use a small helper IntProperty on prefs if it
    # exists, otherwise fall back to the stored Python attr.
    list_id = f"DGBLOCKS_UL_Profiles_{category.replace(' ', '_')}"
    layout.template_list(
        DGBLOCKS_UL_Profiles.bl_idname,   # listtype_name
        list_id,                           # list_id (unique per category)
        prefs,                             # dataptr  (collection owner)
        "profiles",                        # propname (collection prop name)
        prefs,                             # active_dataptr
        "profiles_active_index",           # active_propname  (see note below)
        rows=max(2, len(cat_items)),
        maxrows=6,
    )
    # NOTE: "profiles_active_index" must exist on AddonPreferences.
    # Blocks using this UI should add:
    #   profiles_active_index: bpy.props.IntProperty()
    # to their AddonPreferences class.  The core prefs class does this below.

    layout.separator(factor=0.4)

    # ── Detail panel for the selected profile ─────────────────────────────────
    sel_index = getattr(prefs, "profiles_active_index", 0)
    if 0 <= sel_index < len(prefs.profiles):
        sel_item = prefs.profiles[sel_index]
        # Only show detail when the item belongs to this category
        if sel_item.category == category:
            inst = Core_Profile_Manager_Wrapper.get_instance(uid=sel_item.uid)
            if inst is not None:
                detail_box = layout.box()
                draw_profile_props(detail_box, sel_item.data, editable=inst.is_editing)

#================================================================================
# MODULE-LEVEL CLASS LIST
#================================================================================

# Classes that must be registered/unregistered via bpy.utils.register_class.
# Does NOT include the block-specific pg_class subclasses (those are the
# responsibility of each block's register_block / unregister_block).
_BPY_CLASSES = [
    DGBLOCKS_PG_ProfileBase,
    DGBLOCKS_PG_ProfileStateItem,
    DGBLOCKS_UL_Profiles,
    DGBLOCKS_OT_ProfileAdd,
    DGBLOCKS_OT_ProfileEdit,
    DGBLOCKS_OT_ProfileSave,
    DGBLOCKS_OT_ProfileCancel,
    DGBLOCKS_OT_ProfileDuplicate,
    DGBLOCKS_OT_ProfileDeleteConfirm,
]


#================================================================================
# USAGE EXAMPLE  (module-level docstring – never executed at import time)
#================================================================================
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE EXAMPLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── 1. Define your Block's profile PropertyGroup ──────────────────────────

class MY_PG_DebugProfile(DGBLOCKS_PG_ProfileBase):
    bl_idname = "MY_PG_DebugProfile"
    log_level : bpy.props.IntProperty(name="Log Level", default=1, min=0, max=5)
    verbose   : bpy.props.BoolProperty(name="Verbose",  default=False)
    prefix    : bpy.props.StringProperty(name="Prefix", default="[DEBUG]")


# ── 2. Define AddonPreferences with the required properties ───────────────

class MY_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    profiles: bpy.props.CollectionProperty(type=DGBLOCKS_PG_ProfileStateItem)
    profiles_active_index: bpy.props.IntProperty()    # required by UIList

    def draw(self, context):
        draw_profiles_ui(self.layout, category="Debug Profiles")


# ── 3. Register ───────────────────────────────────────────────────────────

def register():
    for cls in _BPY_CLASSES:
        bpy.utils.register_class(cls)
    bpy.utils.register_class(MY_PG_DebugProfile)
    bpy.utils.register_class(MY_AddonPreferences)

    Core_Profile_Manager_Wrapper.register_profile_type("Debug Profiles", MY_PG_DebugProfile)
    Core_Profile_Manager_Wrapper.init_pre_bpy(prefs_cls=MY_AddonPreferences)
    # init_post_bpy is called from the post-register init hook:
    #   Core_Profile_Manager_Wrapper.init_post_bpy(prefs_cls=MY_AddonPreferences)


def unregister():
    Core_Profile_Manager_Wrapper.destroy_wrapper()
    bpy.utils.unregister_class(MY_AddonPreferences)
    bpy.utils.unregister_class(MY_PG_DebugProfile)
    for cls in reversed(_BPY_CLASSES):
        bpy.utils.unregister_class(cls)


# ── 4. Reading values ─────────────────────────────────────────────────────

entries = Core_Profile_Manager_Wrapper.get_instances_for_category("Debug Profiles")
if entries:
    uid, inst = entries[0]
    log_level, verbose, prefix = Core_Profile_Manager_Wrapper.get_profile_values(
        uid, ["log_level", "verbose", "prefix"]
    )
    # is_editing=True → returns the live in-progress (unsaved) values

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

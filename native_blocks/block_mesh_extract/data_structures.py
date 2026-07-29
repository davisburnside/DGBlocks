
from __future__ import annotations

import time
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Callable, Optional, Sequence

import numpy as np

# ==============================================================================================================================
# ENUMS
# ==============================================================================================================================

class Enum_Mesh_Domain(StrEnum):
    """MET-side domain names. Blender's attribute API calls VERTEX 'POINT'."""
    VERTEX = "VERTEX"
    EDGE   = "EDGE"
    FACE   = "FACE"
    CORNER = "CORNER"


# MET domain  →  Blender attribute-API domain
BL_DOMAIN_FROM_MET: dict[str, str] = {
    "VERTEX": "POINT",
    "EDGE":   "EDGE",
    "FACE":   "FACE",
    "CORNER": "CORNER",
}
MET_DOMAIN_FROM_BL: dict[str, str] = {v: k for k, v in BL_DOMAIN_FROM_MET.items()}


class Enum_Attr_Accessor(StrEnum):
    """How an attribute is reached on a bpy Mesh."""
    COLLECTION      = "COLLECTION"       # mesh.vertices / edges / polygons / loops
    NAMED_ATTRIBUTE = "NAMED_ATTRIBUTE"  # mesh.attributes[name]


class Enum_Read_Source(StrEnum):
    """
    EVALUATED : post-modifier cage via evaluated_get(depsgraph).to_mesh().
                Index space may NOT match the original mesh — unsafe for write-back.
    ORIGINAL  : the editable base mesh. Object Mode reads object.data directly;
                Edit Mode reads it after object.update_from_editmode().
                Index space is write-back safe.
    """
    EVALUATED = "EVALUATED"
    ORIGINAL  = "ORIGINAL"


class Enum_Mesh_Op_Type(StrEnum):
    READ     = "READ"
    CALLBACK = "CALLBACK"
    WRITE    = "WRITE"


class Enum_Edit_Mode_Write_Strategy(StrEnum):
    """
    BMESH_LOOP : Edit-Mode writes go through bmesh with a per-element Python loop.
    REJECT     : Edit-Mode writes fail with an error instead of paying the loop cost.
    """
    BMESH_LOOP = "BMESH_LOOP"
    REJECT     = "REJECT"


class Enum_Attr_Type_Mismatch(StrEnum):
    """What to do when a write target exists with a different domain/data_type."""
    ERROR    = "ERROR"
    RECREATE = "RECREATE"


# Blender data_type → (numpy dtype, components, foreach value field)
BL_DATA_TYPE_MAP: dict[str, tuple[str, int, str]] = {
    "FLOAT":        ("float32", 1,  "value"),
    "INT":          ("int32",   1,  "value"),
    "INT8":         ("int32",   1,  "value"),
    "BOOLEAN":      ("bool",    1,  "value"),
    "FLOAT_VECTOR": ("float32", 3,  "vector"),
    "FLOAT2":       ("float32", 2,  "vector"),
    "FLOAT_COLOR":  ("float32", 4,  "color"),
    "BYTE_COLOR":   ("float32", 4,  "color"),
    "INT32_2D":     ("int32",   2,  "value"),
    "QUATERNION":   ("float32", 4,  "value"),
}

# Attribute names Blender reserves / manages itself — never a valid write target
RESERVED_ATTR_NAMES: frozenset[str] = frozenset({
    "position", "id", "material_index",
})


# ==============================================================================================================================
# MET ATTRIBUTE DECLARATIONS
# ==============================================================================================================================

@dataclass(frozen=True, eq=False)
class MET_Attr_Declaration:
    """
    Table-driven descriptor for one mesh attribute — used for BOTH reads and writes.

    domain          : Enum_Mesh_Domain value
    name            : blender attribute / collection-property name (also the custom attr name)
    dtype           : numpy dtype string. None = resolve at read time from the BL attribute.
    components      : scalars per element (1 = scalar, 2 = vec2, 3 = vec3, 4 = color/quat)
    accessor        : Enum_Attr_Accessor
    collection_name : for COLLECTION accessor — "vertices" / "edges" / "polygons" / "loops"
    value_field     : field name passed to foreach_get / foreach_set
    is_writable     : False for derived/topology data Blender computes itself
    instance_field  : builtin slot name on the domain dataclass. None → stored in domain.custom[name]
    data_type       : Blender data_type string, required to CREATE a named attribute on write
    is_custom       : True for user/GN named attributes (dtype resolved at runtime)
    is_uv_map       : True for UV layers (CORNER / FLOAT2)
    resolve_active  : True when `name` must be resolved at runtime (active UV map)
    """
    domain:          str
    name:            str
    dtype:           Optional[str] = None
    components:      int           = 1
    accessor:        str           = Enum_Attr_Accessor.COLLECTION
    collection_name: Optional[str] = None
    value_field:     str           = "value"
    is_writable:     bool          = False
    instance_field:  Optional[str] = None
    data_type:       Optional[str] = None
    is_custom:       bool          = False
    is_uv_map:       bool          = False
    resolve_active:  bool          = False

    @property
    def key(self) -> str:
        return f"{self.domain}.{self.name}"

    @property
    def label(self) -> str:
        prefix = "custom" if self.is_custom else "attr"
        return f"{self.domain}.{self.name}" if not self.is_custom else f"{self.domain}.{self.name} ({prefix})"

    @property
    def storage_path(self) -> str:
        """Human-readable location of this attribute inside an RTC_Mesh_Extract_Instance."""
        slot = self.instance_field if self.instance_field else f"custom['{self.name}']"
        return f"{self.domain.lower()}.{slot}"

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        other_key = getattr(other, "key", None)
        return NotImplemented if other_key is None else other_key == self.key

    def resolved_copy(self, **overrides) -> "MET_Attr_Declaration":
        return replace(self, **overrides)


def met_attr_label(attr: MET_Attr_Declaration) -> str:
    """Stable string key for metadata / logs, e.g. 'VERTEX.co' or 'FACE.planar_groups'."""
    return attr.key


# ----------------------------------------------------------
# Custom-attribute factories (shared by every domain namespace)

def _make_custom_attr(
    domain:     str,
    name:       str,
    data_type:  Optional[str] = None,
) -> MET_Attr_Declaration:
    """
    Declare a named mesh attribute (GN output, vertex color, user attribute...).
    dtype/components are resolved at read time. `data_type` is REQUIRED only when the
    attribute must be created during a write.
    """
    dtype, components, value_field = (None, 1, "value")
    if data_type in BL_DATA_TYPE_MAP:
        dtype, components, value_field = BL_DATA_TYPE_MAP[data_type]

    return MET_Attr_Declaration(
        domain          = domain,
        name            = name,
        dtype           = dtype,
        components      = components,
        accessor        = Enum_Attr_Accessor.NAMED_ATTRIBUTE,
        value_field     = value_field,
        is_writable     = True,
        instance_field  = None,          # → domain.custom[name]
        data_type       = data_type,
        is_custom       = True,
    )


def _make_uv_map_attr(name: Optional[str] = None) -> MET_Attr_Declaration:
    """
    Declare a UV map. UV maps are ordinary CORNER / FLOAT2 named attributes.
    name=None → the mesh's ACTIVE uv layer, resolved at run time (resolved name is
    recorded in the action op record for provenance).
    """
    return MET_Attr_Declaration(
        domain          = Enum_Mesh_Domain.CORNER,
        name            = name if name else "",
        dtype           = "float32",
        components      = 2,
        accessor        = Enum_Attr_Accessor.NAMED_ATTRIBUTE,
        value_field     = "vector",
        is_writable     = True,
        instance_field  = None,
        data_type       = "FLOAT2",
        is_custom       = True,
        is_uv_map       = True,
        resolve_active  = name is None,
    )


# ----------------------------------------------------------
# VERTEX

class _MET_VERTEX:
    CO = MET_Attr_Declaration(
        domain = "VERTEX", name = "co", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "vertices",
        value_field = "co", is_writable = True, instance_field = "co",
        data_type = "FLOAT_VECTOR",
    )
    NORMAL = MET_Attr_Declaration(
        domain = "VERTEX", name = "normal", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "vertices",
        value_field = "normal", is_writable = False, instance_field = "normal",
    )
    CREASE = MET_Attr_Declaration(
        domain = "VERTEX", name = "crease_vert", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "crease", data_type = "FLOAT",
    )
    BEVEL_WEIGHT = MET_Attr_Declaration(
        domain = "VERTEX", name = "bevel_weight_vert", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "bevel_weight", data_type = "FLOAT",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> MET_Attr_Declaration:
        return _make_custom_attr(Enum_Mesh_Domain.VERTEX, name, data_type)


# ----------------------------------------------------------
# EDGE

class _MET_EDGE:
    VERTICES = MET_Attr_Declaration(
        domain = "EDGE", name = "vertices", dtype = "int32", components = 2,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "edges",
        value_field = "vertices", is_writable = False, instance_field = "vertices",
    )
    CREASE = MET_Attr_Declaration(
        domain = "EDGE", name = "crease_edge", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "crease", data_type = "FLOAT",
    )
    SHARP = MET_Attr_Declaration(
        domain = "EDGE", name = "sharp_edge", dtype = "bool", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "sharp", data_type = "BOOLEAN",
    )
    SEAM = MET_Attr_Declaration(
        domain = "EDGE", name = "seam_edge", dtype = "bool", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "seam", data_type = "BOOLEAN",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> MET_Attr_Declaration:
        return _make_custom_attr(Enum_Mesh_Domain.EDGE, name, data_type)


# ----------------------------------------------------------
# FACE

class _MET_FACE:
    NORMAL = MET_Attr_Declaration(
        domain = "FACE", name = "normal", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "normal", is_writable = False, instance_field = "normal",
    )
    AREA = MET_Attr_Declaration(
        domain = "FACE", name = "area", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "area", is_writable = False, instance_field = "area",
    )
    LOOP_START = MET_Attr_Declaration(
        domain = "FACE", name = "loop_start", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "loop_start", is_writable = False, instance_field = "loop_start",
    )
    LOOP_TOTAL = MET_Attr_Declaration(
        domain = "FACE", name = "loop_total", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "loop_total", is_writable = False, instance_field = "loop_total",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> MET_Attr_Declaration:
        return _make_custom_attr(Enum_Mesh_Domain.FACE, name, data_type)


# ----------------------------------------------------------
# CORNER

class _MET_CORNER:
    VERTEX_INDEX = MET_Attr_Declaration(
        domain = "CORNER", name = "vertex_index", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "loops",
        value_field = "vertex_index", is_writable = False, instance_field = "vertex_index",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> MET_Attr_Declaration:
        return _make_custom_attr(Enum_Mesh_Domain.CORNER, name, data_type)

    @staticmethod
    def UV_MAP(name: Optional[str] = None) -> MET_Attr_Declaration:
        return _make_uv_map_attr(name)


# ----------------------------------------------------------
# Public namespace

class MET:
    """
    Mesh Extract Target attribute namespace — one ordered vocabulary for reads AND writes.

        MET.VERTEX.CO
        MET.EDGE.SEAM
        MET.FACE.CUSTOM_ATTRIBUTE("planar_groups", data_type="INT")
        MET.CORNER.UV_MAP()                 # active UV layer
        MET.CORNER.UV_MAP("UVMap")
    """
    VERTEX = _MET_VERTEX
    EDGE   = _MET_EDGE
    FACE   = _MET_FACE
    CORNER = _MET_CORNER


ALL_MET_ATTRS: tuple[MET_Attr_Declaration, ...] = (
    MET.VERTEX.CO,
    MET.VERTEX.NORMAL,
    MET.VERTEX.CREASE,
    MET.VERTEX.BEVEL_WEIGHT,
    MET.EDGE.VERTICES,
    MET.EDGE.CREASE,
    MET.EDGE.SHARP,
    MET.EDGE.SEAM,
    MET.FACE.NORMAL,
    MET.FACE.AREA,
    MET.FACE.LOOP_START,
    MET.FACE.LOOP_TOTAL,
    MET.CORNER.VERTEX_INDEX,
)


# ==============================================================================================================================
# DOMAIN DATA NAMESPACES
# ==============================================================================================================================

class _Mesh_Domain_Base:
    """
    Shared behaviour for the four domain namespaces.

    Builtin attributes are declared fields (typed, autocompleted, None until read).
    Named/custom attributes live in `custom` and are also reachable as attributes
    when their name is a valid Python identifier:

        instance.corner.vertex_index      # builtin field
        instance.face.custom["gn_f1"]     # canonical
        instance.face.gn_f1               # sugar (identifier-safe names only)
        instance.corner.custom["UV Map"]  # names with spaces: dict access only
    """

    def __getattr__(self, name):
        # Only reached when normal attribute lookup fails. Never touch self.<attr> here.
        custom = self.__dict__.get("custom")
        if custom is not None and name in custom:
            return custom[name]
        raise AttributeError(
            f"{type(self).__name__} has no attribute or custom attribute '{name}'"
        )

    def get(self, name: str, default=None):
        """Fetch a builtin field or a custom attribute by name. None values fall back to default."""
        custom = self.__dict__.get("custom") or {}
        if name in custom:
            return custom[name]
        value = self.__dict__.get(name, None)
        return default if value is None else value

    def has(self, name: str) -> bool:
        return self.get(name, None) is not None

    def set_custom(self, name: str, value) -> None:
        self.custom[name] = value

    @classmethod
    def builtin_field_names(cls) -> list[str]:
        return [f.name for f in fields(cls) if f.name not in ("count", "custom")]

    def populated_field_names(self) -> list[str]:
        names = [n for n in self.builtin_field_names() if self.__dict__.get(n) is not None]
        names += [f"custom['{k}']" for k in (self.__dict__.get("custom") or {})]
        return names


@dataclass
class Mesh_Domain_Vertex(_Mesh_Domain_Base):
    count:        int                  = 0
    co:           Optional[np.ndarray] = None   # (n_verts, 3) float32
    normal:       Optional[np.ndarray] = None   # (n_verts, 3) float32
    crease:       Optional[np.ndarray] = None   # (n_verts,)   float32
    bevel_weight: Optional[np.ndarray] = None   # (n_verts,)   float32
    custom:       dict                 = field(default_factory=dict)


@dataclass
class Mesh_Domain_Edge(_Mesh_Domain_Base):
    count:    int                  = 0
    vertices: Optional[np.ndarray] = None       # (n_edges, 2) int32
    crease:   Optional[np.ndarray] = None       # (n_edges,)   float32
    sharp:    Optional[np.ndarray] = None       # (n_edges,)   bool
    seam:     Optional[np.ndarray] = None       # (n_edges,)   bool
    custom:   dict                 = field(default_factory=dict)


@dataclass
class Mesh_Domain_Face(_Mesh_Domain_Base):
    count:      int                  = 0
    normal:     Optional[np.ndarray] = None     # (n_faces, 3) float32
    area:       Optional[np.ndarray] = None     # (n_faces,)   float32
    loop_start: Optional[np.ndarray] = None     # (n_faces,)   int32
    loop_total: Optional[np.ndarray] = None     # (n_faces,)   int32
    custom:     dict                 = field(default_factory=dict)


@dataclass
class Mesh_Domain_Corner(_Mesh_Domain_Base):
    count:        int                  = 0
    vertex_index: Optional[np.ndarray] = None   # (n_corners,) int32
    custom:       dict                 = field(default_factory=dict)


# ==============================================================================================================================
# ACTION RECORDS
# ==============================================================================================================================

@dataclass
class Mesh_Action_Op_Record:
    """One read / callback / write step inside a single action."""
    op_type:     str                 # Enum_Mesh_Op_Type
    label:       str
    duration_ms: float         = 0.0
    shape:       str           = "-"
    is_valid:    bool          = True
    error_str:   Optional[str] = None
    detail:      str           = ""  # e.g. "→ face.custom['planar_groups']" / "bmesh loop, 12 changed"


@dataclass
class Mesh_Action_Record:
    """
    Metadata for ONE run_mesh_action_for_object call. Arrays are never stored here —
    they live on the instance. Records are append-only and kept in start-time order.
    """
    action_uid:      int
    label:           str
    object_name:     str
    timestamp_start: float                       # wall clock (display)
    duration_ms:     float         = 0.0
    read_source:     str           = Enum_Read_Source.EVALUATED
    object_mode:     str           = ""          # "OBJECT" / "EDIT" / ...
    is_valid:        bool          = False
    error_str:       Optional[str] = None
    ops:             list          = field(default_factory=list)   # list[Mesh_Action_Op_Record]
    domain_counts:   dict          = field(default_factory=dict)   # {"VERTEX": 8, ...}

    # ---- convenience ----
    @property
    def read_count(self) -> int:
        return sum(1 for op in self.ops if op.op_type == Enum_Mesh_Op_Type.READ)

    @property
    def write_count(self) -> int:
        return sum(1 for op in self.ops if op.op_type == Enum_Mesh_Op_Type.WRITE)

    @property
    def callback_count(self) -> int:
        return sum(1 for op in self.ops if op.op_type == Enum_Mesh_Op_Type.CALLBACK)

    @property
    def failed_ops(self) -> list:
        return [op for op in self.ops if not op.is_valid]


# ==============================================================================================================================
# DECLARATIONS
# ==============================================================================================================================

@dataclass
class Callback_Op:
    """
    Optional wrapper giving a callback an explicit panel label.
    A bare callable is also accepted in `callbacks` (label = func.__name__).

    Callback contract:
        func(instance, action_record) -> None
    The callback MUTATES the instance:
        instance.face.custom["planar_groups"] = arr    # per-element → writable back to the mesh
        instance.derived["boundaries"] = data          # non-domain data
    Return values are ignored.
    """
    func:  Callable
    label: Optional[str] = None

    @property
    def resolved_label(self) -> str:
        return self.label or getattr(self.func, "__name__", "callback")


@dataclass
class Write_Op:
    """
    A write target. By default the payload is whatever currently sits at the
    attribute's slot on the instance (the instance is a bidirectional staging buffer).
    Pass `payload` to write a one-shot array without staging it.
    """
    attr:    MET_Attr_Declaration
    payload: Optional[np.ndarray] = None


@dataclass
class Numpy_Mesh_Action_Declaration:
    """
    One reusable, object-free declaration. Phases run in a fixed order:

        READ  →  CALLBACKS  →  WRITE

    Never store a bpy.types.Object here — declarations are module-level constants and
    caching Blender IDs is forbidden. The object is passed to
    Wrapper_Mesh_Extract.run_mesh_action_for_object(object, declaration).

    label            : identifies this action in the panel / logs
    slot             : instance identity is (object_name, slot). Same slot accumulates
                       data across declarations (pass 1 → pass 2 chaining).
    read_attributes  : ordered MET attrs (builtin, custom, or UV map)
    callbacks        : ordered callables / Callback_Op — mutate the instance in place
    write_attributes : ordered MET attrs / Write_Op — flushed from the instance to the mesh
    read_source      : EVALUATED (post-modifier) or ORIGINAL (write-back safe indices)
    """
    label:            str
    read_attributes:  Sequence = field(default_factory=tuple)
    callbacks:        Sequence = field(default_factory=tuple)
    write_attributes: Sequence = field(default_factory=tuple)

    read_source:      str  = Enum_Read_Source.EVALUATED
    should_cache_in_RTC: bool = True
    slot:             str  = "default"

    # Safety / behaviour switches
    allow_evaluated_index_space: bool = False   # required to combine writes with EVALUATED reads
    edit_mode_write_strategy:    str  = Enum_Edit_Mode_Write_Strategy.BMESH_LOOP
    on_type_mismatch:            str  = Enum_Attr_Type_Mismatch.ERROR
    diff_limited_writes:         bool = True    # only touch elements whose value actually changed
    should_push_undo:            bool = False
    max_actions_retained:        int  = 50      # per instance, oldest evicted

    @property
    def has_writes(self) -> bool:
        return bool(self.write_attributes)


# ==============================================================================================================================
# RTC INSTANCE
# ==============================================================================================================================

@dataclass
class RTC_Mesh_Extract_Instance:
    """
    Accumulated mesh data for one (object_name, slot) pair, plus the chronological
    log of every action that touched it.

    Data is domain-namespaced:
        instance.vertex.co                      instance.vertex.count
        instance.face.normal                    instance.face.custom["planar_groups"]
        instance.corner.custom["UVMap"]         instance.corner.vertex_index
        instance.derived["face_face_neighbors"] # non-domain data (CSR pairs, dicts, scalars)

    Latest read wins per slot. Actions are append-only and ordered by start time.
    A failed action keeps whatever data it managed to read before failing.
    """
    object_name:        str
    slot:               str = "default"
    object_session_uid: int = 0

    vertex: Mesh_Domain_Vertex = field(default_factory=Mesh_Domain_Vertex)
    edge:   Mesh_Domain_Edge   = field(default_factory=Mesh_Domain_Edge)
    face:   Mesh_Domain_Face   = field(default_factory=Mesh_Domain_Face)
    corner: Mesh_Domain_Corner = field(default_factory=Mesh_Domain_Corner)

    # Non-domain results (CSR tuples, dicts, scalars, matrices...)
    derived: dict = field(default_factory=dict)

    # Chronological action log — list[Mesh_Action_Record]
    actions: list = field(default_factory=list)

    # Bumped whenever a write changes element counts; invalidates cached index-space data
    topology_generation: int = 0

    # Mirror of the most recent action's outcome (cheap UI access)
    is_valid:  bool          = False
    error_str: Optional[str] = None

    # ----------------------------------------------------------
    # Domain access

    def domain(self, domain_str: str) -> _Mesh_Domain_Base:
        return {
            "VERTEX": self.vertex,
            "EDGE":   self.edge,
            "FACE":   self.face,
            "CORNER": self.corner,
        }[str(domain_str)]

    def get_attr_value(self, attr: MET_Attr_Declaration):
        """Read the value staged at this attribute's slot (None when absent)."""
        domain_obj = self.domain(attr.domain)
        if attr.instance_field:
            return getattr(domain_obj, attr.instance_field, None)
        return (domain_obj.custom or {}).get(attr.name)

    def set_attr_value(self, attr: MET_Attr_Declaration, value) -> None:
        domain_obj = self.domain(attr.domain)
        if attr.instance_field:
            setattr(domain_obj, attr.instance_field, value)
        else:
            domain_obj.custom[attr.name] = value

    # ----------------------------------------------------------
    # Action log

    @property
    def last_action(self) -> Optional[Mesh_Action_Record]:
        return self.actions[-1] if self.actions else None

    @property
    def timestamp_last_action(self) -> float:
        last = self.last_action
        return last.timestamp_start if last else 0.0

    @property
    def total_duration_ms(self) -> float:
        return sum(a.duration_ms for a in self.actions)

    def append_action(self, action: Mesh_Action_Record, max_retained: int = 50) -> None:
        """Append in start-time order and evict the oldest beyond max_retained."""
        self.actions.append(action)
        self.actions.sort(key=lambda a: (a.timestamp_start, a.action_uid))
        if max_retained > 0 and len(self.actions) > max_retained:
            del self.actions[: len(self.actions) - max_retained]
        self.is_valid  = action.is_valid
        self.error_str = action.error_str

    def summary_str(self) -> str:
        return (
            f"{self.object_name}[{self.slot}] "
            f"v{self.vertex.count}/e{self.edge.count}/f{self.face.count}/c{self.corner.count} "
            f"actions={len(self.actions)}"
        )

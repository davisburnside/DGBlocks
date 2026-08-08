
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Callable, Optional, Sequence

import numpy as np

# ==============================================================================================================================
# ENUMS
# ==============================================================================================================================

class Enum_Geometry_Type(StrEnum):
    """What kind of datablock an action actually operated on."""
    MESH    = "MESH"        # bpy.types.Mesh (also the result of to_mesh() on anything)
    CURVES  = "CURVES"      # bpy.types.Curves — has .points / .curves / .attributes
    UNKNOWN = "UNKNOWN"


class Enum_Geometry_Target(StrEnum):
    """
    Which datablock the step list reads from / writes to.

    MESH_EVALUATED : always go through a mesh (to_mesh() for non-mesh objects).
                     Mesh domains (VERTEX/EDGE/FACE/CORNER) only.
    NATIVE_DATA    : operate on the object's own datablock. Mesh objects use mesh
                     domains; curve objects use curve domains (POINT/CURVE).
    AUTO           : NATIVE_DATA for MESH / CURVES / CURVE objects, MESH_EVALUATED
                     for everything else (META, FONT, SURFACE, POINTCLOUD...).
    """
    AUTO           = "AUTO"
    MESH_EVALUATED = "MESH_EVALUATED"
    NATIVE_DATA    = "NATIVE_DATA"


class Enum_Domain(StrEnum):
    """Attribute domains across both geometry types."""
    # mesh
    VERTEX = "VERTEX"
    EDGE   = "EDGE"
    FACE   = "FACE"
    CORNER = "CORNER"
    # curves
    POINT  = "POINT"
    CURVE  = "CURVE"


MESH_DOMAINS:  tuple[str, ...] = ("VERTEX", "EDGE", "FACE", "CORNER")
CURVE_DOMAINS: tuple[str, ...] = ("POINT", "CURVE")

# Attribute-API domain string used by Blender for each of our domains.
# NOTE mesh VERTEX and curve POINT both map to Blender's "POINT".
BL_DOMAIN_FROM_DOMAIN: dict[str, str] = {
    "VERTEX": "POINT",
    "EDGE":   "EDGE",
    "FACE":   "FACE",
    "CORNER": "CORNER",
    "POINT":  "POINT",
    "CURVE":  "CURVE",
}


def domain_from_bl_domain(bl_domain: str, geometry_type: str) -> Optional[str]:
    """Reverse of BL_DOMAIN_FROM_DOMAIN — needs the geometry type to disambiguate POINT."""
    if str(geometry_type) == Enum_Geometry_Type.CURVES:
        return {"POINT": "POINT", "CURVE": "CURVE"}.get(bl_domain)
    return {"POINT": "VERTEX", "EDGE": "EDGE", "FACE": "FACE", "CORNER": "CORNER"}.get(bl_domain)


class Enum_Attr_Accessor(StrEnum):
    """How an attribute is reached on the datablock."""
    COLLECTION      = "COLLECTION"       # mesh.vertices / edges / polygons / loops, curves.curves
    NAMED_ATTRIBUTE = "NAMED_ATTRIBUTE"  # datablock.attributes[name]


class Enum_Read_Source(StrEnum):
    """
    EVALUATED : post-modifier data via evaluated_get(depsgraph).
                Index space may NOT match the original — unsafe for write-back.
    ORIGINAL  : the editable base datablock. Object Mode reads object.data directly;
                Edit Mode reads it after object.update_from_editmode().
                Index space is write-back safe.
    """
    EVALUATED = "EVALUATED"
    ORIGINAL  = "ORIGINAL"


class Enum_Op_Type(StrEnum):
    READ     = "READ"
    CALLBACK = "CALLBACK"
    WRITE    = "WRITE"
    GROUP    = "GROUP"


class Enum_Step_Kind(StrEnum):
    """
    Discriminator stored ON every step dataclass.

    Step dispatch matches on this string rather than `isinstance`, so a declaration
    authored against a second import path of this module (double-imported package,
    stale __pycache__) still runs correctly.
    """
    READ     = "READ"
    CALLBACK = "CALLBACK"
    GROUP    = "GROUP"


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
    "id", "material_index",
})


# ==============================================================================================================================
# ATTRIBUTE DECLARATIONS
# ==============================================================================================================================

@dataclass(frozen=True, eq=False)
class Attr_Declaration:
    """
    Table-driven descriptor for one attribute — used for BOTH reads and writes, on
    meshes and on curves.

    domain          : Enum_Domain value
    name            : blender attribute / collection-property name (also the custom attr name)
    dtype           : numpy dtype string. None = resolve at read time from the BL attribute.
    components      : scalars per element (1 = scalar, 2 = vec2, 3 = vec3, 4 = color/quat)
    accessor        : Enum_Attr_Accessor
    collection_name : for COLLECTION accessor — "vertices" / "edges" / "polygons" / "loops" / "curves"
    value_field     : field name passed to foreach_get / foreach_set
    is_writable     : False for derived/topology data Blender computes itself
    instance_field  : builtin slot name on the domain dataclass. None → stored in domain.custom[name]
    data_type       : Blender data_type string, required to CREATE a named attribute on write
    is_custom       : True for user/GN/named attributes (dtype resolved at runtime)
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
    def storage_path(self) -> str:
        """Human-readable location of this attribute inside a Geometry_Actions_Result_Instance."""
        slot = self.instance_field if self.instance_field else f"custom['{self.name}']"
        return f"{self.domain.lower()}.{slot}"

    @property
    def is_curve_domain(self) -> bool:
        return str(self.domain) in CURVE_DOMAINS

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        other_key = getattr(other, "key", None)
        return NotImplemented if other_key is None else other_key == self.key

    def resolved_copy(self, **overrides) -> "Attr_Declaration":
        return replace(self, **overrides)


# ----------------------------------------------------------
# Custom-attribute factories (shared by every domain namespace)

def _make_custom_attr(domain: str, name: str, data_type: Optional[str] = None) -> Attr_Declaration:
    """
    Declare a named attribute (GN output, vertex color, user attribute, curve attribute...).
    dtype/components are resolved at read time. `data_type` is REQUIRED only when the
    attribute must be created during a write.
    """
    dtype, components, value_field = (None, 1, "value")
    if data_type in BL_DATA_TYPE_MAP:
        dtype, components, value_field = BL_DATA_TYPE_MAP[data_type]

    return Attr_Declaration(
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


def _make_uv_map_attr(name: Optional[str] = None) -> Attr_Declaration:
    """
    Declare a UV map. UV maps are ordinary CORNER / FLOAT2 named attributes.
    name=None → the mesh's ACTIVE uv layer, resolved at run time.
    """
    return Attr_Declaration(
        domain          = Enum_Domain.CORNER,
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


# ==============================================================================================================================
# MET — MESH ATTRIBUTE NAMESPACE
# ==============================================================================================================================

class _MET_VERTEX:
    CO = Attr_Declaration(
        domain = "VERTEX", name = "co", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "vertices",
        value_field = "co", is_writable = True, instance_field = "co",
        data_type = "FLOAT_VECTOR",
    )
    NORMAL = Attr_Declaration(
        domain = "VERTEX", name = "normal", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "vertices",
        value_field = "normal", is_writable = False, instance_field = "normal",
    )
    CREASE = Attr_Declaration(
        domain = "VERTEX", name = "crease_vert", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "crease", data_type = "FLOAT",
    )
    BEVEL_WEIGHT = Attr_Declaration(
        domain = "VERTEX", name = "bevel_weight_vert", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "bevel_weight", data_type = "FLOAT",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.VERTEX, name, data_type)


class _MET_EDGE:
    VERTICES = Attr_Declaration(
        domain = "EDGE", name = "vertices", dtype = "int32", components = 2,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "edges",
        value_field = "vertices", is_writable = False, instance_field = "vertices",
    )
    CREASE = Attr_Declaration(
        domain = "EDGE", name = "crease_edge", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "crease", data_type = "FLOAT",
    )
    SHARP = Attr_Declaration(
        domain = "EDGE", name = "sharp_edge", dtype = "bool", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "sharp", data_type = "BOOLEAN",
    )
    SEAM = Attr_Declaration(
        domain = "EDGE", name = "seam_edge", dtype = "bool", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "seam", data_type = "BOOLEAN",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.EDGE, name, data_type)


class _MET_FACE:
    NORMAL = Attr_Declaration(
        domain = "FACE", name = "normal", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "normal", is_writable = False, instance_field = "normal",
    )
    AREA = Attr_Declaration(
        domain = "FACE", name = "area", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "area", is_writable = False, instance_field = "area",
    )
    LOOP_START = Attr_Declaration(
        domain = "FACE", name = "loop_start", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "loop_start", is_writable = False, instance_field = "loop_start",
    )
    LOOP_TOTAL = Attr_Declaration(
        domain = "FACE", name = "loop_total", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "polygons",
        value_field = "loop_total", is_writable = False, instance_field = "loop_total",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.FACE, name, data_type)


class _MET_CORNER:
    VERTEX_INDEX = Attr_Declaration(
        domain = "CORNER", name = "vertex_index", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "loops",
        value_field = "vertex_index", is_writable = False, instance_field = "vertex_index",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.CORNER, name, data_type)

    @staticmethod
    def UV_MAP(name: Optional[str] = None) -> Attr_Declaration:
        return _make_uv_map_attr(name)


class MET:
    """
    Mesh attribute namespace — one ordered vocabulary for reads AND writes.

        MET.VERTEX.CO
        MET.EDGE.SEAM
        MET.FACE.CUSTOM_ATTRIBUTE("planar_groups", data_type="INT")
        MET.CORNER.UV_MAP()                 # active UV layer
    """
    VERTEX = _MET_VERTEX
    EDGE   = _MET_EDGE
    FACE   = _MET_FACE
    CORNER = _MET_CORNER


# ==============================================================================================================================
# CET — CURVE ATTRIBUTE NAMESPACE  (bpy.types.Curves: .points / .curves / .attributes)
# ==============================================================================================================================

class _CET_POINT:
    POSITION = Attr_Declaration(
        domain = "POINT", name = "position", dtype = "float32", components = 3,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "vector",
        is_writable = True, instance_field = "position", data_type = "FLOAT_VECTOR",
    )
    RADIUS = Attr_Declaration(
        domain = "POINT", name = "radius", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "radius", data_type = "FLOAT",
    )
    TILT = Attr_Declaration(
        domain = "POINT", name = "tilt", dtype = "float32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "tilt", data_type = "FLOAT",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.POINT, name, data_type)


class _CET_CURVE:
    CURVE_TYPE = Attr_Declaration(
        domain = "CURVE", name = "curve_type", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "curve_type", data_type = "INT8",
    )
    CYCLIC = Attr_Declaration(
        domain = "CURVE", name = "cyclic", dtype = "bool", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "cyclic", data_type = "BOOLEAN",
    )
    RESOLUTION = Attr_Declaration(
        domain = "CURVE", name = "resolution", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.NAMED_ATTRIBUTE, value_field = "value",
        is_writable = True, instance_field = "resolution", data_type = "INT",
    )
    POINTS_LENGTH = Attr_Declaration(
        domain = "CURVE", name = "points_length", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "curves",
        value_field = "points_length", is_writable = False, instance_field = "points_length",
    )
    FIRST_POINT_INDEX = Attr_Declaration(
        domain = "CURVE", name = "first_point_index", dtype = "int32", components = 1,
        accessor = Enum_Attr_Accessor.COLLECTION, collection_name = "curves",
        value_field = "first_point_index", is_writable = False,
        instance_field = "first_point_index",
    )

    @staticmethod
    def CUSTOM_ATTRIBUTE(name: str, data_type: Optional[str] = None) -> Attr_Declaration:
        return _make_custom_attr(Enum_Domain.CURVE, name, data_type)


class CET:
    """
    Curve attribute namespace — the curve-side twin of MET.

        CET.POINT.POSITION
        CET.POINT.CUSTOM_ATTRIBUTE("p_data", data_type="FLOAT")
        CET.CURVE.CYCLIC
        CET.CURVE.CUSTOM_ATTRIBUTE("s_data", data_type="INT")

    Requires a `bpy.types.Curves` datablock. Legacy `bpy.types.Curve` objects are
    converted on demand (see helpers_read.acquire_geometry_for_read).
    """
    POINT = _CET_POINT
    CURVE = _CET_CURVE


ALL_MET_ATTRS: tuple[Attr_Declaration, ...] = (
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

ALL_CET_ATTRS: tuple[Attr_Declaration, ...] = (
    CET.POINT.POSITION,
    CET.POINT.RADIUS,
    CET.POINT.TILT,
    CET.CURVE.CURVE_TYPE,
    CET.CURVE.CYCLIC,
    CET.CURVE.RESOLUTION,
    CET.CURVE.POINTS_LENGTH,
    CET.CURVE.FIRST_POINT_INDEX,
)


# ==============================================================================================================================
# DOMAIN DATA NAMESPACES
# ==============================================================================================================================

class _Domain_Base:
    """
    Shared behaviour for every domain namespace.

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
class Domain_Vertex(_Domain_Base):
    count:        int                  = 0
    co:           Optional[np.ndarray] = None   # (n_verts, 3) float32
    normal:       Optional[np.ndarray] = None   # (n_verts, 3) float32
    crease:       Optional[np.ndarray] = None   # (n_verts,)   float32
    bevel_weight: Optional[np.ndarray] = None   # (n_verts,)   float32
    custom:       dict                 = field(default_factory=dict)


@dataclass
class Domain_Edge(_Domain_Base):
    count:    int                  = 0
    vertices: Optional[np.ndarray] = None       # (n_edges, 2) int32
    crease:   Optional[np.ndarray] = None       # (n_edges,)   float32
    sharp:    Optional[np.ndarray] = None       # (n_edges,)   bool
    seam:     Optional[np.ndarray] = None       # (n_edges,)   bool
    custom:   dict                 = field(default_factory=dict)


@dataclass
class Domain_Face(_Domain_Base):
    count:      int                  = 0
    normal:     Optional[np.ndarray] = None     # (n_faces, 3) float32
    area:       Optional[np.ndarray] = None     # (n_faces,)   float32
    loop_start: Optional[np.ndarray] = None     # (n_faces,)   int32
    loop_total: Optional[np.ndarray] = None     # (n_faces,)   int32
    custom:     dict                 = field(default_factory=dict)


@dataclass
class Domain_Corner(_Domain_Base):
    count:        int                  = 0
    vertex_index: Optional[np.ndarray] = None   # (n_corners,) int32
    custom:       dict                 = field(default_factory=dict)


@dataclass
class Domain_Point(_Domain_Base):
    """Curve control points (bpy.types.Curves.points)."""
    count:    int                  = 0
    position: Optional[np.ndarray] = None       # (n_points, 3) float32
    radius:   Optional[np.ndarray] = None       # (n_points,)   float32
    tilt:     Optional[np.ndarray] = None       # (n_points,)   float32
    custom:   dict                 = field(default_factory=dict)


@dataclass
class Domain_Curve(_Domain_Base):
    """Individual splines (bpy.types.Curves.curves)."""
    count:             int                  = 0
    curve_type:        Optional[np.ndarray] = None   # (n_curves,) int32
    cyclic:            Optional[np.ndarray] = None   # (n_curves,) bool
    resolution:        Optional[np.ndarray] = None   # (n_curves,) int32
    points_length:     Optional[np.ndarray] = None   # (n_curves,) int32
    first_point_index: Optional[np.ndarray] = None   # (n_curves,) int32
    custom:            dict                 = field(default_factory=dict)


# ==============================================================================================================================
# ACTION RECORDS
# ==============================================================================================================================

@dataclass
class Action_Op_Record:
    """One read / callback / write step inside a single action."""
    op_type:     str                 # Enum_Op_Type
    label:       str
    duration_ms: float         = 0.0
    shape:       str           = "-"
    is_valid:    bool          = True
    error_str:   Optional[str] = None


@dataclass
class Action_Record:
    """
    Metadata for ONE run_geometry_action_for_object call. Arrays are never stored here —
    they live on the instance. Records are append-only and kept in start-time order.
    """
    action_uid:      int
    declaration_id:  str
    label:           str
    object_name:     str
    timestamp_start: float                       # wall clock (display + sort key)
    duration_ms:     float         = 0.0
    read_source:     str           = Enum_Read_Source.EVALUATED
    geometry_target: str           = Enum_Geometry_Target.AUTO
    geometry_type:   str           = Enum_Geometry_Type.UNKNOWN
    object_mode:     str           = ""          # "OBJECT" / "EDIT" / "SCULPT" / ...
    is_valid:        bool          = False
    error_str:       Optional[str] = None
    ops:             list          = field(default_factory=list)   # list[Action_Op_Record]
    domain_counts:   dict          = field(default_factory=dict)   # {"VERTEX": 8, ...}

    # ---- convenience ----
    @property
    def read_count(self) -> int:
        return sum(1 for op in self.ops if op.op_type == Enum_Op_Type.READ)

    @property
    def callback_count(self) -> int:
        return sum(1 for op in self.ops if op.op_type == Enum_Op_Type.CALLBACK)

    @property
    def failed_ops(self) -> list:
        return [op for op in self.ops if not op.is_valid]


# ==============================================================================================================================
# STEP TYPES
# ==============================================================================================================================
#
# A declaration is an ordered list of steps. Each step is one of:
#   - Read_Step(attr)        : read one attribute into the instance (manual refresh)
#   - Callback_Step(func)    : run a callback that mutates the instance and/or the geometry
#   - Group_Tag(label)       : a named grouping marker for log/UI formatting only
#
# Steps run in the order given. There is no automatic re-read after a callback —
# if a callback changes topology or attribute values, the developer must add an
# explicit Read_Step afterwards to refresh the instance slot.
#
# Callback contract:
#     func(instance, action_record, geometry_context) -> None
# Return values are ignored. A raising callback fails the action gracefully.
# ==============================================================================================================================

@dataclass
class Read_Step:
    """Read one attribute into the instance slot."""
    attr: Attr_Declaration
    step_kind: str = Enum_Step_Kind.READ


@dataclass
class Callback_Step:
    """
    Run a callback.
    Signature: func(instance, action_record, geometry_context) -> None
    """
    func: Callable
    label: Optional[str] = None
    step_kind: str = Enum_Step_Kind.CALLBACK

    @property
    def resolved_label(self) -> str:
        return self.label or getattr(self.func, "__name__", "callback")


@dataclass
class Group_Tag:
    """
    A named grouping marker inserted into the step list. It performs no work —
    it exists solely to provide structure for execution-time logs and the debug
    panel. Subsequent steps are displayed/logged under this group until another
    Group_Tag appears.
    """
    label: str
    step_kind: str = Enum_Step_Kind.GROUP


def get_step_kind(step) -> Optional[str]:
    """
    Robust step discriminator. Reads the `step_kind` field rather than using
    `isinstance`, so double-imported step classes still dispatch correctly.
    """
    kind = getattr(step, "step_kind", None)
    return str(kind) if kind is not None else None


# ==============================================================================================================================
# DECLARATION
# ==============================================================================================================================

@dataclass
class Geometry_Actions_Declaration:
    """
    One reusable, object-free declaration describing an ordered step list.

    Never store a bpy.types.Object here — declarations are module-level constants
    and caching Blender IDs is forbidden. The object is passed to
    Wrapper_Geometry_Actions.run_geometry_action_for_object(object, declaration).

    declaration_id  : REQUIRED unique identity for this action. Results are stacked per
                      (declaration_id, object_name); two declarations sharing an id share
                      a stack regardless of their step content.
    label           : display-only name for the panel / logs (defaults to declaration_id)
    steps           : ordered tuple of Read_Step / Callback_Step / Group_Tag
    read_source     : EVALUATED (post-modifier) or ORIGINAL (write-back safe indices)
    geometry_target : AUTO / MESH_EVALUATED / NATIVE_DATA — see Enum_Geometry_Target
    retention_count : how many results to keep per (declaration_id, object_name).
                      1 = only the latest (default). 0 = don't store at all.
                      N > 1 = keep the last N for before/after diffs.
    max_actions_retained : per-result action-log cap; oldest evicted
    """
    declaration_id:        str
    label:                 str      = ""
    steps:                 Sequence = field(default_factory=tuple)

    read_source:           str  = Enum_Read_Source.EVALUATED
    geometry_target:       str  = Enum_Geometry_Target.AUTO
    retention_count:       int  = 1
    max_actions_retained:  int  = 50

    def __post_init__(self):
        if not self.declaration_id:
            raise ValueError("Geometry_Actions_Declaration requires a non-empty declaration_id.")
        if not self.label:
            self.label = self.declaration_id

    @property
    def has_callbacks(self) -> bool:
        return any(get_step_kind(s) == Enum_Step_Kind.CALLBACK for s in self.steps or ())

    @property
    def should_store(self) -> bool:
        return self.retention_count > 0


# ==============================================================================================================================
# RESULT INSTANCE
# ==============================================================================================================================

@dataclass
class Geometry_Actions_Result_Instance:
    """
    The result of one run (or of one explicitly chained sequence of runs) for a
    (declaration_id, object_name) pair, plus the log of every action that touched it.

    Data is domain-namespaced:
        instance.vertex.co                      instance.vertex.count
        instance.face.normal                    instance.face.custom["planar_groups"]
        instance.point.position                 instance.curve.cyclic
        instance.derived["face_face_neighbors"] # non-domain data (CSR pairs, dicts, scalars)

    Each run pushes a NEW instance onto the stack (retention_count deep), so
    stack[-2] vs stack[-1] is always a valid before/after pair.
    """
    declaration_id:     str
    object_name:        str
    object_session_uid: int = 0
    geometry_type:      str = Enum_Geometry_Type.UNKNOWN

    timestamp_start:    float = 0.0
    timestamp_end:      float = 0.0

    # mesh domains
    vertex: Domain_Vertex = field(default_factory=Domain_Vertex)
    edge:   Domain_Edge   = field(default_factory=Domain_Edge)
    face:   Domain_Face   = field(default_factory=Domain_Face)
    corner: Domain_Corner = field(default_factory=Domain_Corner)
    # curve domains
    point:  Domain_Point  = field(default_factory=Domain_Point)
    curve:  Domain_Curve  = field(default_factory=Domain_Curve)

    # Non-domain results (CSR tuples, dicts, scalars, serialized strings...)
    derived: dict = field(default_factory=dict)

    # Chronological action log — list[Action_Record]
    actions: list = field(default_factory=list)

    # Bumped whenever a write changes element counts; invalidates cached index-space data
    topology_generation: int = 0

    # Mirror of the most recent action's outcome (cheap UI access)
    is_valid:  bool          = False
    error_str: Optional[str] = None

    # ----------------------------------------------------------
    # Identity

    @property
    def stack_key(self) -> str:
        return f"{self.declaration_id}|{self.object_name}"

    # ----------------------------------------------------------
    # Domain access

    @property
    def domain_names(self) -> tuple[str, ...]:
        if str(self.geometry_type) == Enum_Geometry_Type.CURVES:
            return ("point", "curve")
        return ("vertex", "edge", "face", "corner")

    def domain(self, domain_str: str) -> _Domain_Base:
        return {
            "VERTEX": self.vertex,
            "EDGE":   self.edge,
            "FACE":   self.face,
            "CORNER": self.corner,
            "POINT":  self.point,
            "CURVE":  self.curve,
        }[str(domain_str)]

    def get_attr_value(self, attr: Attr_Declaration):
        """Read the value staged at this attribute's slot (None when absent)."""
        domain_obj = self.domain(attr.domain)
        if attr.instance_field:
            return getattr(domain_obj, attr.instance_field, None)
        return (domain_obj.custom or {}).get(attr.name)

    def set_attr_value(self, attr: Attr_Declaration, value) -> None:
        domain_obj = self.domain(attr.domain)
        if attr.instance_field:
            setattr(domain_obj, attr.instance_field, value)
        else:
            domain_obj.custom[attr.name] = value

    # ----------------------------------------------------------
    # Action log

    @property
    def last_action(self) -> Optional[Action_Record]:
        return self.actions[-1] if self.actions else None

    @property
    def timestamp_last_action(self) -> float:
        last = self.last_action
        return last.timestamp_start if last else self.timestamp_start

    @property
    def total_duration_ms(self) -> float:
        return sum(a.duration_ms for a in self.actions)

    def append_action(self, action: Action_Record, max_retained: int = 50) -> None:
        """Append in start-time order and evict the oldest beyond max_retained."""
        self.actions.append(action)
        self.actions.sort(key=lambda a: (a.timestamp_start, a.action_uid))
        if max_retained > 0 and len(self.actions) > max_retained:
            del self.actions[: len(self.actions) - max_retained]
        self.is_valid  = action.is_valid
        self.error_str = action.error_str

    def summary_str(self) -> str:
        if str(self.geometry_type) == Enum_Geometry_Type.CURVES:
            counts = f"p{self.point.count}/c{self.curve.count}"
        else:
            counts = (
                f"v{self.vertex.count}/e{self.edge.count}"
                f"/f{self.face.count}/c{self.corner.count}"
            )
        return f"{self.declaration_id}@{self.object_name} {counts} actions={len(self.actions)}"

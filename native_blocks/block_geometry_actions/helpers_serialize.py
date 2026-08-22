"""
helpers_serialize.py — geometry ⇄ string, for shipping a mesh or curve over a socket.

FORMAT
    "DGGEO2:" + base64( uint64_header_length + zlib(json_header) + raw_array_bytes )

The JSON header describes every payload block (name, domain, dtype, shape, byte length);
the binary tail is the concatenation of those blocks in header order. Numpy arrays are
never round-tripped through JSON numbers, so precision is exact and the payload is compact.

The header also carries `geometry_type`, per-domain element counts, and the mesh topology
needed to rebuild geometry from scratch (edges + face loops, or curve point counts).

Both directions raise on invalid data — malformed strings, unknown versions, checksum
mismatches, shape/count disagreements, and unsupported attribute types. Callers wrap them
in a Callback_Step, so a raise fails the action gracefully instead of crashing the host.

Server / socket infrastructure is explicitly out of scope: this module only produces and
consumes the string.
"""

import base64
import json
import zlib
from typing import Optional

import numpy as np

from .data_structures import (
    BL_DATA_TYPE_MAP,
    BL_DOMAIN_FROM_DOMAIN,
    CURVE_DOMAINS,
    Enum_Geometry_Type,
    domain_from_bl_domain,
)

SERIALIZATION_PREFIX  = "DGGEO2:"
SERIALIZATION_VERSION = 2

# derived[] keys used by the builtin serialize / deserialize callbacks
DERIVED_KEY_SERIALIZED = "serialized_geometry"

_HEADER_LENGTH_BYTES = 8

# Attributes Blender owns and refuses to have re-created by name
_SKIP_ATTRIBUTE_NAMES = frozenset({".corner_vert", ".corner_edge", ".edge_verts"})


# ==============================================================================================================================
# HARVEST — datablock → plain python payload
# ==============================================================================================================================

def _harvest_named_attributes(data, geometry_type: str) -> list[dict]:
    """Every user-visible named attribute on the datablock, as raw numpy blocks."""
    blocks: list[dict] = []
    for bl_attr in data.attributes:
        name = bl_attr.name
        if name.startswith(".") or name in _SKIP_ATTRIBUTE_NAMES:
            continue
        data_type = bl_attr.data_type
        if data_type not in BL_DATA_TYPE_MAP:
            raise RuntimeError(
                f"Attribute '{name}' has unsupported data_type {data_type!r} — "
                f"cannot serialize."
            )
        domain = domain_from_bl_domain(bl_attr.domain, geometry_type)
        if domain is None:
            raise RuntimeError(
                f"Attribute '{name}' is on unsupported domain {bl_attr.domain!r}."
            )
        dtype, components, value_field = BL_DATA_TYPE_MAP[data_type]
        count = len(bl_attr.data)
        buf = np.empty(count * components, dtype=dtype)
        if count:
            bl_attr.data.foreach_get(value_field, buf)
        blocks.append({
            "kind":       "attribute",
            "name":       name,
            "domain":     domain,
            "data_type":  data_type,
            "components": components,
            "count":      count,
            "array":      buf,
        })
    return blocks


def serialize_geometry(data, geometry_type: str) -> str:
    """
    Serialize a bpy.types.Mesh or bpy.types.Curves (topology + every named attribute)
    into a single transport-safe string. Raises RuntimeError for anything unsupported.
    """
    geometry_type = str(geometry_type)
    if geometry_type not in (Enum_Geometry_Type.MESH, Enum_Geometry_Type.CURVES):
        raise RuntimeError(f"Cannot serialize geometry_type {geometry_type!r}.")

    blocks: list[dict] = []
    header: dict = {
        "version":       SERIALIZATION_VERSION,
        "geometry_type": geometry_type,
        "name":          getattr(data, "name", ""),
    }

    if geometry_type == Enum_Geometry_Type.MESH:
        n_verts   = len(data.vertices)
        n_edges   = len(data.edges)
        n_faces   = len(data.polygons)
        n_corners = len(data.loops)
        header["counts"] = {
            "VERTEX": n_verts, "EDGE": n_edges, "FACE": n_faces, "CORNER": n_corners,
        }

        edge_verts = np.empty(n_edges * 2, dtype="int32")
        if n_edges:
            data.edges.foreach_get("vertices", edge_verts)
        loop_total = np.empty(n_faces, dtype="int32")
        if n_faces:
            data.polygons.foreach_get("loop_total", loop_total)
        corner_verts = np.empty(n_corners, dtype="int32")
        if n_corners:
            data.loops.foreach_get("vertex_index", corner_verts)

        blocks += [
            {"kind": "topology", "name": "edge_verts",   "array": edge_verts},
            {"kind": "topology", "name": "loop_total",   "array": loop_total},
            {"kind": "topology", "name": "corner_verts", "array": corner_verts},
        ]
    else:
        n_points = len(data.points)
        n_curves = len(data.curves)
        header["counts"] = {"POINT": n_points, "CURVE": n_curves}
        points_length = np.array(
            [c.points_length for c in data.curves], dtype="int32"
        ) if n_curves else np.zeros(0, dtype="int32")
        if int(points_length.sum()) != n_points:
            raise RuntimeError(
                f"Curve point layout is inconsistent: per-curve totals "
                f"{int(points_length.sum())} != {n_points} points."
            )
        blocks.append({"kind": "topology", "name": "points_length", "array": points_length})

    blocks += _harvest_named_attributes(data, geometry_type)

    # ---- pack ----------------------------------------------------------------
    payload = bytearray()
    header_blocks = []
    for block in blocks:
        arr = np.ascontiguousarray(block["array"])
        raw = arr.tobytes()
        header_blocks.append({
            "kind":       block["kind"],
            "name":       block["name"],
            "domain":     block.get("domain"),
            "data_type":  block.get("data_type"),
            "components": block.get("components"),
            "count":      block.get("count"),
            "dtype":      arr.dtype.str,
            "shape":      list(arr.shape),
            "nbytes":     len(raw),
        })
        payload += raw

    header["blocks"]   = header_blocks
    header["checksum"] = zlib.crc32(bytes(payload))

    header_bytes = zlib.compress(json.dumps(header).encode("utf-8"), 6)
    body = len(header_bytes).to_bytes(_HEADER_LENGTH_BYTES, "big") + header_bytes + bytes(payload)
    return SERIALIZATION_PREFIX + base64.b64encode(body).decode("ascii")


# ==============================================================================================================================
# UNPACK — string → header + arrays
# ==============================================================================================================================

def deserialize_to_payload(serialized: str) -> tuple[dict, dict]:
    """
    Decode a serialized string into (header, {block_name: numpy_array}).
    Raises RuntimeError for any malformed / corrupted input.
    """
    if not isinstance(serialized, str) or not serialized.startswith(SERIALIZATION_PREFIX):
        raise RuntimeError(
            f"Not a DGBlocks geometry string — expected the {SERIALIZATION_PREFIX!r} prefix."
        )
    try:
        body = base64.b64decode(serialized[len(SERIALIZATION_PREFIX):], validate=True)
    except Exception as e:
        raise RuntimeError(f"Base64 decode failed: {e}") from e

    if len(body) < _HEADER_LENGTH_BYTES:
        raise RuntimeError("Malformed payload — missing header length.")
    header_length = int.from_bytes(body[:_HEADER_LENGTH_BYTES], "big")
    header_start = _HEADER_LENGTH_BYTES
    header_end = header_start + header_length
    if header_length <= 0 or header_end > len(body):
        raise RuntimeError("Malformed payload — invalid or truncated header length.")
    header_bytes = body[header_start:header_end]
    payload = body[header_end:]
    try:
        header = json.loads(zlib.decompress(header_bytes).decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Header decode failed: {e}") from e

    if header.get("version") != SERIALIZATION_VERSION:
        raise RuntimeError(
            f"Unsupported serialization version {header.get('version')!r} "
            f"(this build reads v{SERIALIZATION_VERSION})."
        )
    if zlib.crc32(payload) != header.get("checksum"):
        raise RuntimeError("Payload checksum mismatch — the data is corrupted.")

    arrays: dict = {}
    offset = 0
    for block in header.get("blocks", ()):
        nbytes = int(block["nbytes"])
        chunk = payload[offset: offset + nbytes]
        if len(chunk) != nbytes:
            raise RuntimeError(f"Payload truncated while reading block '{block['name']}'.")
        arr = np.frombuffer(chunk, dtype=np.dtype(block["dtype"])).reshape(block["shape"])
        arrays[f"{block['kind']}:{block['name']}"] = arr.copy()
        offset += nbytes
    if offset != len(payload):
        raise RuntimeError(
            f"Payload has {len(payload) - offset} trailing byte(s) not described by the header."
        )
    return header, arrays


# ==============================================================================================================================
# APPLY — payload → datablock (destructive replace)
# ==============================================================================================================================

def apply_serialized_geometry(data, serialized: str, geometry_type: str) -> str:
    """
    Replace `data`'s contents with the serialized geometry, custom attributes included.
    Object Mode only. Returns a short detail string. Raises on any mismatch.
    """
    geometry_type = str(geometry_type)
    header, arrays = deserialize_to_payload(serialized)

    if str(header["geometry_type"]) != geometry_type:
        raise RuntimeError(
            f"Payload holds {header['geometry_type']} data but the target is "
            f"{geometry_type} — replace the datablock type first."
        )
    counts = header["counts"]

    if geometry_type == Enum_Geometry_Type.MESH:
        _apply_mesh(data, header, arrays, counts)
        element_summary = (
            f"v{counts['VERTEX']} e{counts['EDGE']} f{counts['FACE']} c{counts['CORNER']}"
        )
    else:
        _apply_curves(data, header, arrays, counts)
        element_summary = f"p{counts['POINT']} c{counts['CURVE']}"

    attr_count = _apply_attributes(data, header, arrays, geometry_type)
    if hasattr(data, "update"):
        data.update()
    return f"replaced geometry ({element_summary}) + {attr_count} attribute(s)"


def _apply_mesh(data, header: dict, arrays: dict, counts: dict) -> None:
    n_verts   = int(counts["VERTEX"])
    n_edges   = int(counts["EDGE"])
    n_faces   = int(counts["FACE"])
    n_corners = int(counts["CORNER"])

    positions = None
    for block in header["blocks"]:
        if block["kind"] == "attribute" and block["name"] == "position":
            positions = arrays["attribute:position"]
            break
    if positions is None:
        raise RuntimeError("Payload has no 'position' attribute — cannot rebuild the mesh.")
    if positions.size != n_verts * 3:
        raise RuntimeError(
            f"'position' holds {positions.size} floats, expected {n_verts * 3}."
        )

    edge_verts   = arrays["topology:edge_verts"]
    loop_total   = arrays["topology:loop_total"]
    corner_verts = arrays["topology:corner_verts"]
    if int(loop_total.sum()) != n_corners:
        raise RuntimeError(
            f"Face loop totals sum to {int(loop_total.sum())}, expected {n_corners} corners."
        )

    data.clear_geometry()
    data.vertices.add(n_verts)
    data.vertices.foreach_set("co", np.ascontiguousarray(positions, dtype="float32").ravel())
    if n_edges:
        data.edges.add(n_edges)
        data.edges.foreach_set("vertices", edge_verts.ravel())
    if n_faces:
        data.loops.add(n_corners)
        data.polygons.add(n_faces)
        loop_start = np.zeros(n_faces, dtype="int32")
        np.cumsum(loop_total[:-1], out=loop_start[1:]) if n_faces > 1 else None
        data.polygons.foreach_set("loop_start", loop_start)
        data.polygons.foreach_set("loop_total", loop_total)
        data.loops.foreach_set("vertex_index", corner_verts)
    data.update(calc_edges=not n_edges)
    data.validate(verbose=False)


def _apply_curves(data, header: dict, arrays: dict, counts: dict) -> None:
    points_length = arrays["topology:points_length"]
    n_points = int(counts["POINT"])
    if int(points_length.sum()) != n_points:
        raise RuntimeError(
            f"Per-curve point totals sum to {int(points_length.sum())}, expected {n_points}."
        )
    data.remove_curves()
    if len(points_length):
        data.add_curves([int(n) for n in points_length])


def _apply_attributes(data, header: dict, arrays: dict, geometry_type: str) -> int:
    applied = 0
    for block in header["blocks"]:
        if block["kind"] != "attribute":
            continue
        name      = block["name"]
        domain    = block["domain"]
        data_type = block["data_type"]
        arr       = arrays[f"attribute:{name}"]

        bl_domain = BL_DOMAIN_FROM_DOMAIN.get(str(domain))
        if bl_domain is None:
            raise RuntimeError(f"Attribute '{name}' has unknown domain {domain!r}.")
        _, _, value_field = BL_DATA_TYPE_MAP[data_type]

        bl_attr = data.attributes.get(name)
        if bl_attr is None:
            bl_attr = data.attributes.new(name=name, type=data_type, domain=bl_domain)
        elif bl_attr.data_type != data_type or bl_attr.domain != bl_domain:
            raise RuntimeError(
                f"Attribute '{name}' already exists as {bl_attr.data_type}/{bl_attr.domain} "
                f"but the payload holds {data_type}/{bl_domain}."
            )

        expected = len(bl_attr.data) * int(block["components"])
        if arr.size != expected:
            raise RuntimeError(
                f"Attribute '{name}' holds {arr.size} value(s) but the rebuilt geometry "
                f"needs {expected}."
            )
        bl_attr.data.foreach_set(value_field, arr.ravel())
        applied += 1
    return applied

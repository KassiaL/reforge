"""Jolt collider export: `.joltshape` (hulls and meshes) and `.joltbody` (the component that is
added to the .go), both written as protobuf text, the same format Defold reads for its own files.

Object custom properties:
    jolt_collision      none | auto | mesh | hull | box | sphere | capsule | cylinder
                        auto = mesh for a static body, hull for anything that moves
    jolt_motion         static | kinematic | dynamic
    jolt_layer          an object layer of `jolt.layers` in game.project
    jolt_mass           0 takes the mass from the density and the volume
    jolt_density, jolt_friction, jolt_restitution, jolt_convex_radius
    jolt_sensor         bool
"""
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

AXIS_CONVERT = Matrix((
    (1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, -1, 0, 0),
    (0, 0, 0, 1),
))

SHAPE_TYPES = {
    "mesh": "SHAPE_TYPE_MESH",
    "hull": "SHAPE_TYPE_HULL",
    "box": "SHAPE_TYPE_BOX",
    "sphere": "SHAPE_TYPE_SPHERE",
    "capsule": "SHAPE_TYPE_CAPSULE",
    "cylinder": "SHAPE_TYPE_CYLINDER",
}

MOTION_TYPES = {
    "static": "MOTION_TYPE_STATIC",
    "kinematic": "MOTION_TYPE_KINEMATIC",
    "dynamic": "MOTION_TYPE_DYNAMIC",
}

GEOMETRY_KINDS = ("mesh", "hull")

DEFAULTS = {
    "jolt_motion": "static",
    "jolt_layer": "static",
    "jolt_mass": 0.0,
    "jolt_density": 1000.0,
    "jolt_friction": 0.2,
    "jolt_restitution": 0.0,
    "jolt_convex_radius": 0.05,
    "jolt_sensor": False,
}


def _prop(obj, key):
    value = obj.get(key)
    if value is None and obj.data is not None:
        value = obj.data.get(key)
    return DEFAULTS.get(key) if value is None else value


def _string_prop(obj, key):
    return str(_prop(obj, key)).strip().lower()


def _float_prop(obj, key):
    return float(_prop(obj, key))


def motion_of(obj) -> str:
    motion = _string_prop(obj, "jolt_motion")
    return motion if motion in MOTION_TYPES else "static"


def kind_of(obj) -> str:
    """The shape kind this object exports, "none" when it has no Jolt collider."""
    kind = _string_prop(obj, "jolt_collision")
    if kind == "auto":
        return "mesh" if motion_of(obj) == "static" else "hull"
    return kind if kind in SHAPE_TYPES else "none"


def has_collision(obj) -> bool:
    return kind_of(obj) != "none"


def _evaluated_mesh(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return obj.evaluated_get(depsgraph)


def _to_defold(point):
    return AXIS_CONVERT.to_3x3() @ point


def mesh_triangles(obj):
    """Points and triangle indices of the evaluated mesh, in Defold axes."""
    obj_eval = _evaluated_mesh(obj)
    mesh = obj_eval.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        rs = obj.matrix_world.to_3x3()
        points = []
        for vert in bm.verts:
            point = _to_defold(rs @ vert.co)
            points.extend((point.x, point.y, point.z))
        bm.verts.index_update()
        indices = []
        for face in bm.faces:
            indices.extend(vert.index for vert in face.verts)
        bm.free()
        return points, indices
    finally:
        obj_eval.to_mesh_clear()


def hull_points(obj):
    """Points of the convex hull of the evaluated mesh, in Defold axes."""
    obj_eval = _evaluated_mesh(obj)
    mesh = obj_eval.to_mesh()
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        if not bm.verts:
            bm.free()
            return []
        bmesh.ops.convex_hull(bm, input=bm.verts)
        rs = obj.matrix_world.to_3x3()
        points = []
        for vert in bm.verts:
            point = _to_defold(rs @ vert.co)
            points.extend((point.x, point.y, point.z))
        bm.free()
        return points
    finally:
        obj_eval.to_mesh_clear()


def local_bounds(obj):
    """Centre and half extents of the object bounding box, in Defold axes."""
    rs = obj.matrix_world.to_3x3()
    corners = [_to_defold(rs @ Vector(corner)) for corner in obj.bound_box]
    lows = [min(corner[axis] for corner in corners) for axis in range(3)]
    highs = [max(corner[axis] for corner in corners) for axis in range(3)]
    centre = tuple((lows[axis] + highs[axis]) * 0.5 for axis in range(3))
    half = tuple(max((highs[axis] - lows[axis]) * 0.5, 1e-6) for axis in range(3))
    return centre, half


def _vector_block(name, values, indent="  "):
    labels = "xyzw"
    lines = [f"{indent}{name} {{\n"]
    lines += [f"{indent}  {labels[i]}: {value:.6f}\n" for i, value in enumerate(values)]
    lines.append(f"{indent}}}\n")
    return "".join(lines)


def make_joltshape_text(kind: str, points, indices, convex_radius: float) -> str:
    parts = ["parts {\n", f"  type: {SHAPE_TYPES[kind]}\n"]
    parts.append(f"  convex_radius: {convex_radius:.6f}\n")
    parts.extend(f"  points: {value:.6f}\n" for value in points)
    parts.extend(f"  indices: {value}\n" for value in indices)
    parts.append("}\n")
    return "".join(parts)


def make_primitive_shape_text(kind: str, centre, half, convex_radius: float) -> str:
    lines = ["shapes {\n", f"  type: {SHAPE_TYPES[kind]}\n"]
    lines.append(_vector_block("position", centre))
    if kind == "box":
        lines.append(_vector_block("half_extents", half))
    elif kind == "sphere":
        lines.append(f"  radius: {max(half):.6f}\n")
    else:
        radius = max(half[0], half[2])
        half_height = half[1] - radius if kind == "capsule" else half[1]
        lines.append(f"  radius: {radius:.6f}\n")
        lines.append(f"  half_height: {max(half_height, 1e-6):.6f}\n")
    lines.append(f"  convex_radius: {convex_radius:.6f}\n")
    lines.append("}\n")
    return "".join(lines)


def make_joltbody_text(obj, shape_text: str, geometry_project_path) -> str:
    lines = [shape_text] if shape_text else []
    if geometry_project_path:
        lines.append(f'geometry: "{geometry_project_path}"\n')
    lines.append(f"motion_type: {MOTION_TYPES[motion_of(obj)]}\n")
    lines.append(f'layer: "{_string_prop(obj, "jolt_layer")}"\n')
    lines.append(f'mass: {_float_prop(obj, "jolt_mass"):.6f}\n')
    lines.append(f'density: {_float_prop(obj, "jolt_density"):.6f}\n')
    lines.append(f'friction: {_float_prop(obj, "jolt_friction"):.6f}\n')
    lines.append(f'restitution: {_float_prop(obj, "jolt_restitution"):.6f}\n')
    lines.append(f'is_sensor: {"true" if _prop(obj, "jolt_sensor") else "false"}\n')
    return "".join(lines)


def export_jolt_assets(obj, proto: str, abs_jolt_dir: str, jolt_dir_project: str):
    """Writes <proto>.joltshape (only for hull and mesh) and <proto>.joltbody.
    Returns the project path of the .joltbody, or None when the object has no Jolt collider.
    """
    kind = kind_of(obj)
    if kind == "none":
        return None

    convex_radius = _float_prop(obj, "jolt_convex_radius")
    abs_shape = os.path.join(abs_jolt_dir, f"{proto}.joltshape")
    abs_body = os.path.join(abs_jolt_dir, f"{proto}.joltbody")
    shape_project_path = f"/{jolt_dir_project}/{proto}.joltshape".replace("\\", "/")
    body_project_path = f"/{jolt_dir_project}/{proto}.joltbody".replace("\\", "/")

    if os.path.isfile(abs_shape):
        os.remove(abs_shape)

    if kind in GEOMETRY_KINDS:
        points, indices = mesh_triangles(obj) if kind == "mesh" else (hull_points(obj), [])
        with open(abs_shape, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(make_joltshape_text(kind, points, indices, convex_radius))
        body_text = make_joltbody_text(obj, "", shape_project_path)
    else:
        centre, half = local_bounds(obj)
        body_text = make_joltbody_text(obj, make_primitive_shape_text(kind, centre, half, convex_radius), None)

    with open(abs_body, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body_text)
    return body_project_path

# reforge/export_core.py
import os
from mathutils import Matrix

from .utils import (
    ensure_dir,
    safe_remove_file,
    write_text_file,
    sanitize_id,
    select_only,
    export_glb_selected,
    get_prop,
    is_object_visible,
)

from .materials import (
    iter_unique_materials_in_order,
    resolve_defold_material_and_texture_for_material,
    ensure_material_props,
)

from .collision import (
    export_convex_hull_points,
    make_collisionobject_text,
)

from .jolt import (
    export_jolt_assets,
    has_collision as has_jolt_collision,
)

from .defold_formats import (
    make_model_text_multi,
    make_go_components_text,
    make_collection_text_grouped_embedded,
)

from .bake import bake_color_emit_png


AXIS_CONVERT = Matrix((
    (1, 0, 0, 0),
    (0, 0, 1, 0),
    (0, -1, 0, 0),
    (0, 0, 0, 1),
))


def is_collision_only(obj) -> bool:
    """`defold_collision_only`: the mesh is a collider shape, no GLB / .model is written."""
    return bool(get_prop(obj, "defold_collision_only"))


def has_defold_collision(obj) -> bool:
    """Only the explicit property: `defold_collision_only` says the mesh has no model, not that it
    needs a Defold collision object, and a Jolt-only project has none at all."""
    return bool(get_prop(obj, "defold_collision"))


def get_collision_group(obj) -> str:
    v = get_prop(obj, "collision_group")
    v = (str(v).strip() if v is not None else "")
    return v if v else "default"


def get_collision_mask(obj) -> str:
    v = get_prop(obj, "collision_mask")
    v = (str(v).strip() if v is not None else "")
    return v if v else "default"


def to_defold_trs(obj):
    """
    Convert Blender world transform to Defold-friendly TRS using axis conversion.
    Returns:
      pos (x,y,z), quat (x,y,z,w), scale (x,y,z)
    """
    mw = obj.matrix_world.copy()
    c = AXIS_CONVERT
    mw_def = c @ mw @ c.inverted()
    loc = mw_def.to_translation()
    rot = mw_def.to_quaternion()
    scl = mw_def.to_scale()
    return (loc.x, loc.y, loc.z), (rot.x, rot.y, rot.z, rot.w), (scl.x, scl.y, scl.z)


def prototype_id_of(obj) -> str:
    """`defold_prototype` custom property, or the object name for parts of prototype collections."""
    proto_raw = get_prop(obj, "defold_prototype")
    return sanitize_id(proto_raw if proto_raw else obj.name)


def _make_baked_texture_filename(proto: str, mat_name: str) -> str:
    # Stable filename, always PNG
    return f"{proto}__{sanitize_id(mat_name)}_albedo.png"

def _material_prop_bool(mat, key: str, default: bool = False) -> bool:
    if not mat:
        return default
    v = mat.get(key)
    return bool(v) if v is not None else default

def _material_prop_int(mat, key: str, default: int) -> int:
    if not mat:
        return default
    v = mat.get(key)
    try:
        return int(v)
    except Exception:
        return default


def _export_glb_at_origin(context, obj, abs_glb: str):
    """
    Blender's glTF exporter bakes the object's world transform into the GLB node and Defold
    applies glTF node transforms, so a placed instance would be offset twice. The mesh is
    exported with an identity transform and the transform is restored afterwards.
    """
    world = obj.matrix_world.copy()
    obj.matrix_world = Matrix.Identity(4)
    context.view_layer.update()
    try:
        select_only(obj)
        export_glb_selected(abs_glb)
    finally:
        obj.matrix_world = world
        context.view_layer.update()


def export_single_prototype_assets(context, obj, overwrite_go: bool = False) -> str:
    """
    Export assets for ONE prototype:
      - <proto>.glb (mesh at the origin)
      - <proto>.model
      - <proto>.go: created once, never overwritten (unless overwrite_go)
      - optional collision: <proto>.convexshape + <proto>.collisionobject (overwritten)
      - optional bake: per-material PNGs (overwritten)
    With `defold_collision_only` only the collision files and a collision-only .go are written.
    Returns: proto id (sanitized)
    """
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    if not obj or obj.type != "MESH":
        raise RuntimeError("Active object is not a MESH.")

    proto = prototype_id_of(obj)
    collision_only = is_collision_only(obj)

    # absolute dirs
    abs_models = os.path.join(project_root, s.models_dir)
    abs_prefabs = os.path.join(project_root, s.prefabs_dir)
    abs_textures = os.path.join(project_root, s.textures_dir)
    abs_collisions = os.path.join(project_root, s.collisions_dir)
    abs_jolt = os.path.join(project_root, s.jolt_dir)

    materials = iter_unique_materials_in_order(obj)
    for m in materials:
        ensure_material_props(m)
    needs_bake = any(_material_prop_bool(m, "bake_color_texture") for m in materials)

    # ensure dirs
    ensure_dir(abs_models)
    ensure_dir(abs_prefabs)
    ensure_dir(abs_collisions)
    ensure_dir(abs_jolt)
    if s.export_textures or needs_bake:
        ensure_dir(abs_textures)

    # filenames
    glb_filename = f"{proto}.glb"
    model_filename = f"{proto}.model"
    go_filename = f"{proto}.go"

    # absolute paths
    abs_glb = os.path.join(abs_models, glb_filename)
    abs_model = os.path.join(abs_models, model_filename)
    abs_go = os.path.join(abs_prefabs, go_filename)

    # project paths
    glb_project_path = f"/{s.models_dir}/{glb_filename}".replace("\\", "/")
    model_project_path = f"/{s.models_dir}/{model_filename}".replace("\\", "/")

    # cleanup generated files (NEVER delete .go)
    safe_remove_file(abs_glb)
    safe_remove_file(abs_model)

    # cleanup collision generated
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.convexshape"))
    safe_remove_file(os.path.join(abs_collisions, f"{proto}.collisionobject"))
    safe_remove_file(os.path.join(abs_jolt, f"{proto}.joltshape"))
    safe_remove_file(os.path.join(abs_jolt, f"{proto}.joltbody"))

    # build .model material blocks
    blocks = []

    if collision_only:
        pass
    elif materials:
        for mat in materials:
            mat_name, defold_mat_path, defold_tex_path = resolve_defold_material_and_texture_for_material(
                settings=s,
                mat=mat,
                abs_textures_dir=abs_textures,
                textures_dir_project=s.textures_dir,
                obj=obj
            )

            # Bake overrides tex0 path (works with complex materials / Ucupaint)
            if _material_prop_bool(mat, "bake_color_texture"):
                bake_resolution = _material_prop_int(mat, "bake_resolution", 1024)
                bake_padding = _material_prop_int(mat, "bake_padding", 8)
                baked_filename = _make_baked_texture_filename(proto, mat_name)
                baked_abs = os.path.join(abs_textures, baked_filename)

                # overwrite old baked file to avoid _1/_2 naming issues
                safe_remove_file(baked_abs)

                baked_ok = bake_color_emit_png(
                    obj=obj,
                    mat=mat,
                    out_abs_path=baked_abs,
                    resolution=bake_resolution,
                    padding=bake_padding,
                )
                if baked_ok:
                    defold_tex_path = f"/{s.textures_dir}/{baked_filename}".replace("\\", "/")

            blocks.append((mat_name, defold_mat_path, defold_tex_path))
    else:
        # no materials on mesh -> use default single block
        mat_name, defold_mat_path, defold_tex_path = resolve_defold_material_and_texture_for_material(
            settings=s,
            mat=None,
            abs_textures_dir=abs_textures,
            textures_dir_project=s.textures_dir,
            obj=obj
        )
        blocks.append((mat_name, defold_mat_path, defold_tex_path))

    if not collision_only:
        _export_glb_at_origin(context, obj, abs_glb)
        write_text_file(abs_model, make_model_text_multi(glb_project_path, proto, blocks))

    # optional collision (hull points are taken at the origin as well)
    collisionobject_project_path = None
    if has_defold_collision(obj):
        group = get_collision_group(obj)
        mask = get_collision_mask(obj)

        abs_convex = os.path.join(abs_collisions, f"{proto}.convexshape")
        abs_colobj = os.path.join(abs_collisions, f"{proto}.collisionobject")

        convex_project_path = f"/{s.collisions_dir}/{proto}.convexshape".replace("\\", "/")
        colobj_project_path = f"/{s.collisions_dir}/{proto}.collisionobject".replace("\\", "/")

        world = obj.matrix_world.copy()
        obj.matrix_world = Matrix.Identity(4)
        context.view_layer.update()
        try:
            export_convex_hull_points(obj, abs_convex)
        finally:
            obj.matrix_world = world
            context.view_layer.update()
        write_text_file(abs_colobj, make_collisionobject_text(convex_project_path, group, mask))
        collisionobject_project_path = colobj_project_path

    # optional Jolt collider (geometry is taken at the origin as well)
    joltbody_project_path = None
    if has_jolt_collision(obj):
        world = obj.matrix_world.copy()
        obj.matrix_world = Matrix.Identity(4)
        context.view_layer.update()
        try:
            joltbody_project_path = export_jolt_assets(obj, proto, abs_jolt, s.jolt_dir)
        finally:
            obj.matrix_world = world
            context.view_layer.update()

    # create .go ONCE (do not overwrite to preserve manual edits like collision/logic added in Defold)
    if overwrite_go or not os.path.isfile(abs_go):
        identity = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
        components = []
        if not collision_only:
            components.append(("model", model_project_path, identity[0], identity[1]))
        if collisionobject_project_path:
            components.append(("collision", collisionobject_project_path, identity[0], identity[1]))
        if joltbody_project_path:
            components.append(("jolt", joltbody_project_path, identity[0], identity[1]))
        write_text_file(abs_go, make_go_components_text(components))

    return proto


# ------------------------------------------------------------
# Prototype collections (collection instances)
# ------------------------------------------------------------
def collection_parts(collection):
    """MESH objects directly inside a prototype collection."""
    return [o for o in collection.objects if o.type == "MESH"]


def export_prototype_collection(context, name: str, collection) -> str:
    """
    A collection instanced through Empties (Instance Collection) is a prototype made of parts:
    every MESH part is exported as a Reforge prototype of its own (glb/model/collision), then
    <name>.go is written with a model component per part and a collision component per collider
    part, keeping the part's position and rotation inside the collection. Scale of a part must be
    applied. The .go of a prototype collection is derived data and is rewritten on every export;
    the per-part .go files are removed.
    Returns: prototype id (sanitized collection name)
    """
    s = context.scene.reforge_settings
    parts = collection_parts(collection)
    if not parts:
        raise RuntimeError(f"Prototype collection '{collection.name}' has no MESH parts.")

    components = []
    for part in parts:
        pos, quat, scale = to_defold_trs(part)
        if any(abs(v - 1.0) > 1e-6 for v in scale):
            raise RuntimeError(f"'{collection.name}/{part.name}': apply the scale of prototype parts (Ctrl+A > Scale).")
        part_id = export_single_prototype_assets(context, part, overwrite_go=True)
        if not is_collision_only(part):
            components.append((part_id, f"/{s.models_dir}/{part_id}.model".replace("\\", "/"), pos, quat))
        if has_defold_collision(part):
            components.append((f"{part_id}_collision", f"/{s.collisions_dir}/{part_id}.collisionobject".replace("\\", "/"), pos, quat))
        if has_jolt_collision(part):
            components.append((f"{part_id}_jolt", f"/{s.jolt_dir}/{part_id}.joltbody".replace("\\", "/"), pos, quat))
        if part_id != name:
            safe_remove_file(os.path.join(s.project_root, s.prefabs_dir, f"{part_id}.go"))

    abs_go = os.path.join(s.project_root, s.prefabs_dir, f"{name}.go")
    write_text_file(abs_go, make_go_components_text(components))
    return name


def collect_export_groups(context):
    """
    Returns (collection_groups, mesh_groups):
      collection_groups: proto id -> (collection, [instance Empties])
      mesh_groups:       proto id -> [MESH objects with defold_prototype]
    Both respect `export_visible_only` for the instances/objects placed in the scene; the parts
    of a prototype collection are exported even when the collection itself is hidden.
    """
    s = context.scene.reforge_settings
    view_layer = context.view_layer
    collection_groups = {}
    mesh_groups = {}
    for obj in context.scene.objects:
        if s.export_visible_only and not is_object_visible(obj, view_layer):
            continue
        if obj.instance_type == "COLLECTION" and obj.instance_collection is not None:
            proto = sanitize_id(obj.instance_collection.name)
            collection_groups.setdefault(proto, (obj.instance_collection, []))[1].append(obj)
        elif obj.type == "MESH" and get_prop(obj, "defold_prototype"):
            mesh_groups.setdefault(prototype_id_of(obj), []).append(obj)
    if not collection_groups and not mesh_groups:
        raise RuntimeError("Nothing to export: no collection instances and no MESH objects with 'defold_prototype' (with current visibility filter).")
    return collection_groups, mesh_groups


def export_all_prototypes_assets_no_scene(context) -> int:
    """
    Export assets (.glb/.model/optional collisions/bake) for all prototypes in scene.
    Does NOT regenerate .collection.
    """
    collection_groups, mesh_groups = collect_export_groups(context)
    n = 0
    for proto in sorted(collection_groups.keys()):
        export_prototype_collection(context, proto, collection_groups[proto][0])
        n += 1
    for proto in sorted(mesh_groups.keys()):
        # export only "etalon" mesh for this proto
        export_single_prototype_assets(context, mesh_groups[proto][0])
        n += 1
    return n


def run_export_scene(context) -> str:
    """
    Full pipeline:
      - export assets for each prototype (collection prototypes and etalon meshes)
      - generate <collection_name>.collection with grouped embedded instances:
            root
              ├─ <protoA> -> children instances
              ├─ <protoB> -> children instances
              ...
    Returns absolute path to generated .collection
    """
    s = context.scene.reforge_settings
    project_root = s.project_root
    if not project_root or not os.path.isdir(project_root):
        raise RuntimeError("Project Root is empty or not found.")

    abs_scenes = os.path.join(project_root, s.scenes_dir)
    ensure_dir(abs_scenes)

    collection_groups, mesh_groups = collect_export_groups(context)

    placed = {}
    for proto, (collection, empties) in collection_groups.items():
        export_prototype_collection(context, proto, collection)
        placed[proto] = empties
    for proto, objs in mesh_groups.items():
        export_single_prototype_assets(context, objs[0])
        placed[proto] = objs

    # create instance list per proto
    instances_by_proto = {}
    for proto, objs in placed.items():
        go_path = f"/{s.prefabs_dir}/{proto}.go".replace("\\", "/")
        for index, obj in enumerate(objs, start=1):
            pos, quat, scale = to_defold_trs(obj)
            instances_by_proto.setdefault(proto, []).append({
                "id": f"{proto}_{index:03d}",
                "prototype": go_path,
                "pos": pos,
                "quat": quat,
                "scale": scale,
            })

    protos_sorted = sorted(placed.keys())
    collection_text = make_collection_text_grouped_embedded(
        s.collection_name,
        protos_sorted,
        instances_by_proto
    )

    abs_collection = os.path.join(abs_scenes, f"{s.collection_name}.collection")
    safe_remove_file(abs_collection)
    write_text_file(abs_collection, collection_text)
    return abs_collection

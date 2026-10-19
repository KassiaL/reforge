# Reforge fork notes

Fork of [ufgo/reforge](https://github.com/ufgo/reforge) (Blender add-on exporting scenes into a
Defold project), used by `~/defold_projects/3d_demo`. Written for myself: what the add-on does,
what the fork changed, how it is installed. Upstream README: `README.md`.

## Install (this machine)

Blender 5.2.1 (`/opt/blender-5.2.1-linux-x64/blender`) loads the add-on straight from this
checkout through a symlink in the "User Default" extension repository:

```
~/.config/blender/5.2/extensions/user_default/reforge -> ~/defold_projects/reforge/reforge
```

Module name: `bl_ext.user_default.reforge` (the store version was `bl_ext.blender_org.reforge`
and is uninstalled). The add-on is enabled in the saved user preferences, so the panel is there in
the GUI; headless scripts still call `addon_utils.enable("bl_ext.user_default.reforge")` because
`-b` does not load the add-on list in every case. After editing the sources, restart Blender (or
`Reload Scripts`); headless runs always pick up the current files.

Re-create the setup:

```bash
mkdir -p ~/.config/blender/5.2/extensions/user_default
ln -s ~/defold_projects/reforge/reforge ~/.config/blender/5.2/extensions/user_default/reforge
/opt/blender-5.2.1-linux-x64/blender -b --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.reforge'); bpy.ops.wm.save_userpref()"
```

## Layout

| File | Role |
|---|---|
| `reforge/__init__.py` | `bl_info`, registers settings, operators, UI |
| `reforge/settings.py` | `Scene.reforge_settings`: project root, collection name, folders, visibility filter, default material, Tools flags |
| `reforge/ui.py` | sidebar panel (3D view, `N`, tab Reforge) and the Material tab panel with the material custom properties |
| `reforge/operators.py` | Generate Scene, Export Selected / All prototypes, Set Props (writes `defold_prototype` etc.), Clear |
| `reforge/export_core.py` | the exporter: grouping, GLB + `.model` + `.go` + collision per prototype, `.collection` |
| `reforge/materials.py` | material custom props (`defold_material`, `defold_texture`, `bake_*`), texture lookup through the Principled BSDF base colour, texture copy |
| `reforge/bake.py` | Cycles EMIT bake of the colour graph into a PNG (`bake_color_texture`) |
| `reforge/collision.py` | convex hull (`bmesh.ops.convex_hull`) -> `.convexshape` (`TYPE_HULL`) and `.collisionobject` (STATIC) |
| `reforge/defold_formats.py` | text writers for `.model`, `.go`, `.collection` |
| `reforge/utils.py` | selection helpers, glTF export call, `get_prop` (object then mesh data), visibility |

## Data model

- Object custom properties: `defold_prototype` (objects sharing a value are instances of one
  prototype; the first one is the "etalon" whose mesh is exported), `defold_collision` (bool),
  `defold_collision_only` (bool, fork),
  `collision_group`, `collision_mask`. Object-level `defold_material` / `defold_texture` override
  the material ones.
- Material custom properties: `defold_material` (Defold `.material` path written into `.model`),
  `defold_texture` (overrides the auto-found base colour image), `bake_color_texture`,
  `bake_resolution`, `bake_padding`.
- Output per prototype: `<models_dir>/<proto>.glb` + `.model` (one `materials {}` block per
  Blender material, sampler `tex0`), `<prefabs_dir>/<proto>.go`, `<collisions_dir>/<proto>.convexshape`
  + `.collisionobject`, textures copied into `<textures_dir>`, baked PNGs
  `<proto>__<material>_albedo.png`. Scene: `<scenes_dir>/<collection_name>.collection`, one
  game object per instance, grouped under an embedded `root` -> `<proto>` hierarchy.
- Axis conversion Blender Z-up -> Defold Y-up: `(x, y, z) = (bx, bz, -by)` (`AXIS_CONVERT`).

## Fork changes (0.5.3)

1. **Meshes are exported at the origin.** Upstream exported the etalon as placed; Blender's glTF
   exporter bakes the world transform into the GLB node and Defold applies node transforms, so
   every instance was offset by the etalon's transform. `_export_glb_at_origin` sets the matrix
   to identity for the export (and for the convex hull) and restores it.
2. **Deselect includes hidden objects.** `bpy.ops.object.select_all(action='DESELECT')` skips
   hidden objects; a hidden selected object was exported into every GLB (`use_selection`).
   `utils.deselect_all` iterates the view layer.
3. **Prototype collections / collection instances.** An Empty with Instance Collection is an
   instance of the collection. Every MESH part of the collection is exported as its own
   prototype (name = `defold_prototype` or the object name), and `<collection>.go` is written
   with a model component per part plus a collision component per part with `defold_collision`,
   keeping the part's position and rotation inside the collection (scale must be applied). That
   `.go` is derived data: rewritten on every export, the per-part `.go` files are removed.
   Parts are exported even when the prototype collection is hidden in the viewport (the usual
   "asset library" setup: hide the collection, place instances). `export_visible_only` applies
   to the placed Empties. Nested collection instances inside a prototype are not expanded.
   Export Selected Prototype accepts a collection instance.
4. **`defold_collision_only`** object property: the mesh is a collider shape only, no GLB /
   `.model` is written, the `.go` (or the part's components) gets the collision object alone. It
   does not imply `defold_collision`: a Jolt-only project sets `jolt_collision` and gets no Defold
   collision object at all.
   Used for invisible collider meshes (a cylinder for a tree trunk) and for the ground chunks of
   3d_demo: 388 chunk meshes in one prototype collection give one `ground.go` with 388
   collision components and no models.
5. `export_single_prototype_assets(context, obj, overwrite_go=False)`; `prototype_id_of`,
   `collect_export_groups`, `export_prototype_collection` are the new entry points.
   `defold_formats.make_go_components_text` writes multi-component `.go` files.

## Jolt export (fork)

`reforge/jolt.py` writes the resources of the Jolt Defold extension
(`~/defold_projects/jolt/jolt`) next to the Defold ones: `<proto>.joltshape` (the points of a hull
or the indexed triangles of a mesh) and `<proto>.joltbody` (the component added to the prototype's
`.go`), both protobuf text, into the `Jolt Dir` setting (`assets/jolt`).

Object custom properties: `jolt_collision` (`none` / `auto` / `mesh` / `hull` / `box` / `sphere` /
`capsule` / `cylinder`; `auto` = mesh for a static body, hull otherwise), `jolt_motion`
(`static` / `kinematic` / `dynamic`), `jolt_layer`, `jolt_mass`, `jolt_density`, `jolt_friction`,
`jolt_restitution`, `jolt_convex_radius`, `jolt_sensor`. `defold_collision_only` keeps its meaning
(collider mesh, no model). The Tools box writes `jolt_collision`, `jolt_motion` and `jolt_layer`.

Jolt takes concave triangle meshes on static bodies, so ground does not have to be cut into convex
chunks the way Defold's own 3D physics required. Primitive shapes are derived from the bounding box
of the mesh, and the scale has to be applied (`ScaledShape` does not support shear).

## Headless use

```python
import addon_utils, bpy
addon_utils.enable("bl_ext.user_default.reforge", default_set=False, persistent=False)
s = bpy.context.scene.reforge_settings
s.project_root = "/path/to/defold/project"; s.collection_name = "island"
from bl_ext.user_default.reforge import export_core
export_core.run_export_scene(bpy.context)
```

`3d_demo/blender/export_island.py` is exactly this.

## Known limits

- Defold 3D physics has no triangle mesh shape: collisions are convex hulls only. Concave ground
  must be cut into pieces (3d_demo: 4 m chunks).
- One glTF per prototype, no animations (`export_animations=False`), `export_apply=True`
  (modifiers applied).
- The `.model` always uses sampler `tex0`; extra samplers (normal maps) have to be added by hand
  or by a project script.

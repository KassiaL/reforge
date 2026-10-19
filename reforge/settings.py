import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, PointerProperty

BUILTIN_DEFAULT_DEFOLD_MATERIAL = "/builtins/materials/model.material"

class ReforgeSettings(bpy.types.PropertyGroup):
    # Foldouts
    show_export: BoolProperty(name="Export", default=True)
    show_quick_export: BoolProperty(name="Quick Export", default=True)
    show_folders: BoolProperty(name="Folders", default=False)
    show_tools: BoolProperty(name="Tools", default=False)
    show_clear: BoolProperty(name="Clear", default=False)

    # Main
    project_root: StringProperty(name="Defold Project Root", subtype="DIR_PATH", default="")
    collection_name: StringProperty(name="Collection Name", default="scene_from_blender")

    export_visible_only: BoolProperty(name="Export Visible Only", default=True)
    export_textures: BoolProperty(name="Export Textures to Defold Project", default=True)

    default_material: StringProperty(name="Default Material", default=BUILTIN_DEFAULT_DEFOLD_MATERIAL)

    # Paths (project-relative)
    models_dir: StringProperty(name="Models Dir", default="assets/models")
    prefabs_dir: StringProperty(name="Prefabs Dir", default="assets/prefabs")
    scenes_dir: StringProperty(name="Scenes Dir", default="assets/scenes")
    textures_dir: StringProperty(name="Textures Dir", default="assets/textures")
    collisions_dir: StringProperty(name="Collisions Dir", default="assets/collisions")
    jolt_dir: StringProperty(name="Jolt Dir", default="assets/jolt")

    # Tools overwrite flags (OBJECT ONLY)
    overwrite_prototype: BoolProperty(name="Overwrite defold_prototype", default=False)
    overwrite_collision: BoolProperty(name="Overwrite defold_collision", default=False)
    overwrite_collision_group: BoolProperty(name="Overwrite collision_group", default=False)
    overwrite_collision_mask: BoolProperty(name="Overwrite collision_mask", default=False)
    overwrite_jolt: BoolProperty(name="Overwrite jolt_*", default=False)

    # Tools values
    set_defold_collision_value: BoolProperty(name="Set defold_collision", default=False)
    set_collision_group_value: StringProperty(name="Collision group", default="default")
    set_collision_mask_value: StringProperty(name="Collision mask", default="default")
    set_jolt_collision_value: EnumProperty(
        name="Jolt collision",
        default="none",
        items=[
            ("none", "None", "No Jolt collider"),
            ("auto", "Auto", "Mesh for a static body, hull for anything that moves"),
            ("mesh", "Mesh", "Triangle mesh, static bodies"),
            ("hull", "Hull", "Convex hull"),
            ("box", "Box", "Box from the bounding box"),
            ("sphere", "Sphere", "Sphere from the bounding box"),
            ("capsule", "Capsule", "Capsule around the Y axis"),
            ("cylinder", "Cylinder", "Cylinder around the Y axis"),
        ],
    )
    set_jolt_motion_value: EnumProperty(
        name="Jolt motion",
        default="static",
        items=[
            ("static", "Static", "Never moves"),
            ("kinematic", "Kinematic", "Moved by the game"),
            ("dynamic", "Dynamic", "Moved by the simulation"),
        ],
    )
    set_jolt_layer_value: StringProperty(name="Jolt layer", default="static")

    # Duplicate detection
    detect_duplicates: BoolProperty(name="Detect duplicates (.001, .002, etc -> base name)",default=False)
    

_CLASSES = (ReforgeSettings,)

def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.reforge_settings = PointerProperty(type=ReforgeSettings)

def unregister():
    del bpy.types.Scene.reforge_settings
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)

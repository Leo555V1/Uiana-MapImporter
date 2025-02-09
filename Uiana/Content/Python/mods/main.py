import os
import re
import subprocess
import time
from pathlib import Path
import unreal
import winsound
from mods.liana.helpers import *
from mods.liana.valorant import *

# BigSets 
all_textures = []
all_blueprints = {}
object_types = []
all_level_paths = []

AssetTools = unreal.AssetToolsHelpers.get_asset_tools()


def create_override_material(data):
    material_array = []
    for mat in data["Properties"]["OverrideMaterials"]:
        if not mat:
            material_array.append(None)
            continue
        object_name = return_object_name(mat["ObjectName"])
        if object_name == "Stone_M2_Steps_MI1":
            object_name = "Stone_M2_Steps_MI"
        if "MaterialInstanceDynamic" in object_name:
            material_array.append(None)
            continue
        material_array.append(unreal.load_asset(
            f'/Game/ValorantContent/Materials/{object_name}'))
    return material_array


def extract_assets(settings: Settings):
    asset_objects = settings.selected_map.folder_path.joinpath("all_assets.txt")
    args = [settings.umodel.__str__(),
            f"-path={settings.paks_path.__str__()}",
            f"-game=valorant",
            f"-aes={settings.aes}",
            f"-files={asset_objects}",
            "-export",
            f"-{settings.texture_format.replace('.', '')}",
            f"-out={settings.assets_path.__str__()}"]
    subprocess.call(args, stderr=subprocess.DEVNULL)


def extract_data(
        settings: Settings,
        export_directory: str,
        asset_list_txt: str = ""):
    args = [settings.cue4extractor.__str__(),
            "--game-directory", settings.paks_path.__str__(),
            "--aes-key", settings.aes,
            "--export-directory", export_directory.__str__(),
            "--map-name", settings.selected_map.name,
            "--file-list", asset_list_txt,
            "--game-umaps", settings.umap_list_path.__str__()
            ]
    subprocess.call(args)


def get_map_assets(settings: Settings):
    umaps = []

    if not settings.selected_map.folder_path.joinpath("exported.yo").exists():
        extract_data(
            settings, export_directory=settings.selected_map.umaps_path)
        extract_assets(settings)

        umaps = get_files(
            path=settings.selected_map.umaps_path.__str__(), extension=".json")
        umap: Path

        object_list = list()
        actor_list = list()
        materials_ovr_list = list()
        materials_list = list()

        for umap in umaps:
            umap_json, asd = filter_umap(read_json(umap))
            object_types.append(asd)

            # save json
            save_json(umap.__str__(), umap_json)

            # get objects
            umap_objects, umap_materials, umap_actors = get_objects(umap_json)
            actor_list.append(umap_actors)
            object_list.append(umap_objects)
            materials_ovr_list.append(umap_materials)
        # ACTORS
        actor_txt = save_list(filepath=settings.selected_map.folder_path.joinpath(
            f"_assets_actors.txt"), lines=actor_list)
        extract_data(
            settings,
            export_directory=settings.selected_map.actors_path,
            asset_list_txt=actor_txt)
        actors = get_files(
            path=settings.selected_map.actors_path.__str__(),
            extension=".json")

        for ac in actors:
            actor_json = read_json(ac)
            actor_objects, actor_materials, local4list = get_objects(actor_json)
            object_list.append(actor_objects)
            materials_ovr_list.append(actor_materials)
        # next
        object_txt = save_list(filepath=settings.selected_map.folder_path.joinpath(
            f"_assets_objects.txt"), lines=object_list)
        mats_ovr_txt = save_list(filepath=settings.selected_map.folder_path.joinpath(
            f"_assets_materials_ovr.txt"), lines=materials_ovr_list)

        extract_data(
            settings,
            export_directory=settings.selected_map.objects_path,
            asset_list_txt=object_txt)
        extract_data(
            settings,
            export_directory=settings.selected_map.materials_ovr_path,
            asset_list_txt=mats_ovr_txt)

        # ---------------------------------------------------------------------------------------

        models = get_files(
            path=settings.selected_map.objects_path.__str__(),
            extension=".json")
        model: Path
        for model in models:
            model_json = read_json(model)
            # save json
            save_json(model.__str__(), model_json)
            # get object materials
            model_materials = get_object_materials(model_json)
            # get object textures
            # ...

            materials_list.append(model_materials)
        save_list(filepath=settings.selected_map.folder_path.joinpath("all_assets.txt"), lines=[
            [
                path_convert(path) for path in _list
            ] for _list in object_list + materials_list + materials_ovr_list
        ])
        mats_txt = save_list(filepath=settings.selected_map.folder_path.joinpath(
            f"_assets_materials.txt"), lines=materials_list)
        extract_data(
            settings,
            export_directory=settings.selected_map.materials_path,
            asset_list_txt=mats_txt)
        extract_assets(settings)
        with open(settings.selected_map.folder_path.joinpath('exported.yo').__str__(), 'w') as out_file:
            out_file.write("")
        with open(settings.assets_path.joinpath('exported.yo').__str__(), 'w') as out_file:
            out_file.write("")

    else:
        umaps = get_files(
            path=settings.selected_map.umaps_path.__str__(), extension=".json")

    return umaps


def get_decal_material(actor_def):
    if actor_def.props["DecalMaterial"] is not None:
        mat_name = get_obj_name(data=actor_def.props["DecalMaterial"], mat=True)
        mat = unreal.load_asset(
            f'/Game/ValorantContent/Materials/{mat_name}.{mat_name}')
        return mat


def set_material(
        ue_material,
        settings: Settings,
        mat_data: actor_defs, ):
    if not mat_data.props:
        return
    mat_props = mat_data.props

    set_textures(mat_props, ue_material, settings=settings)
    set_all_settings(mat_props, ue_material)
    
    # fix this
    if "BasePropertyOverrides" in mat_props:
        base_prop_override = set_all_settings(mat_props["BasePropertyOverrides"],
                                            unreal.MaterialInstanceBasePropertyOverrides())
        ue_material.set_editor_property('BasePropertyOverrides', base_prop_override)
        unreal.MaterialEditingLibrary.update_material_instance(ue_material)

    if "StaticParameters" in mat_props:
        if "StaticSwitchParameters" in mat_props["StaticParameters"]:
            for param in mat_props["StaticParameters"]["StaticSwitchParameters"]:
                param_name = param["ParameterInfo"]["Name"].lower()
                param_value = param["Value"]
                unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                    ue_material, param_name, bool(param_value))
        if "StaticComponentMaskParameters" in mat_props["StaticParameters"]:
            for param in mat_props["StaticParameters"]["StaticComponentMaskParameters"]:
                mask_list = ["R", "G", "B"]
                for mask in mask_list:
                    value = param[mask]
                    unreal.MaterialEditingLibrary.set_material_instance_static_switch_parameter_value(
                        ue_material, mask, bool(value))
    if "ScalarParameterValues" in mat_props:
        for param in mat_props["ScalarParameterValues"]:
            param_name = param['ParameterInfo']['Name'].lower()
            param_value = param["ParameterValue"]
            set_material_scalar_value(ue_material, param_name, param_value)

    if "VectorParameterValues" in mat_props:
        for param in mat_props["VectorParameterValues"]:
            param_name = param['ParameterInfo']['Name'].lower()
            param_value = param["ParameterValue"]
            if param_name == "texture tint a":
                param_name = "layer a tint"
            if param_name == "texture tint b":
                param_name = "layer b tint"
            set_material_vector_value(ue_material, param_name, get_rgb(param_value))


def set_textures(mat_props: dict,material_reference,settings: Settings):
    set_texture_param = unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value
    if not has_key("TextureParameterValues", mat_props):
        return
    for tex_param in mat_props["TextureParameterValues"]:
        tex_game_path = get_texture_path(s=tex_param, f=settings.texture_format)
        if not tex_game_path:
            continue
        tex_local_path = settings.assets_path.joinpath(tex_game_path).__str__()
        param_name = tex_param['ParameterInfo']['Name'].lower()
        tex_name = Path(tex_local_path).stem
        if Path(tex_local_path).exists():
            loaded_texture = unreal.load_asset(
                f'/Game/ValorantContent/Textures/{tex_name}')
            if not loaded_texture:
                continue
            set_texture_param(material_reference, param_name, loaded_texture)
    unreal.MaterialEditingLibrary.update_material_instance(material_reference)


def set_all_settings(asset_props: dict, component_reference):
    if not asset_props:
        return
    for setting in asset_props:
        value_setting = asset_props[setting]
        try:
            editor_property = component_reference.get_editor_property(setting)
        except:
            continue
        class_name = type(editor_property).__name__
        type_value = type(value_setting).__name__
        if type_value == "int" or type_value == "float" or type_value == "bool":
            component_reference.set_editor_property(setting, value_setting)
            continue
        if "::" in value_setting:
            value_setting = value_setting.split("::")[1]
        if class_name == "Color":
            component_reference.set_editor_property(setting, unreal.Color(r=value_setting['R'], g=value_setting['G'],
                                                                          b=value_setting['B'], a=value_setting['A']))
            continue
        if type_value == "dict":
            if setting == "StaticMesh":
                component_reference.set_editor_property('static_mesh',
                                                        mesh_to_asset(value_setting, "StaticMesh ", "Meshes"))
                continue
            if setting == "BoxExtent":
                component_reference.set_editor_property('box_extent',
                                                        unreal.Vector(x=value_setting['X'], y=value_setting['Y'],
                                                                      z=value_setting['Z']))
                continue
            if setting == "LightmassSettings":
                component_reference.set_editor_property('lightmass_settings', get_light_mass(value_setting,component_reference.get_editor_property('lightmass_settings')))
                continue
            continue
        if type_value == "list":
            continue
        python_unreal_value = return_python_unreal_enum(value_setting)
        value = f'unreal.{class_name}.{python_unreal_value}'
        try:
            value = eval(value)
            component_reference.set_editor_property(setting, value)
        except:
            print(f"UianaSettingsLOG: Error setting {setting} to {value}")
            continue
    return component_reference
def get_light_mass(light_mass:dict, light_mass_reference):
    for l_mass in light_mass:
        if l_mass[0] == "b":
            l_mass = l_mass[1:]
        value = re.sub(r'(?<!^)(?=[A-Z])', '_', l_mass)
        try:
            light_mass_reference.set_editor_property(value, light_mass[l_mass])
        except:
            continue
    return light_mass_reference
def import_light(light_data:actor_defs, all_objs: list):
    light_type_replace = light_data.type.replace("Component","")
    if not light_data.transform:
        light_data.transform = get_scene_parent(light_data.data,light_data.outer,all_objs)
    if not light_data.transform:
        return
    light = unreal.EditorLevelLibrary.spawn_actor_from_class(eval(f'unreal.{light_type_replace}'), light_data.transform.translation,light_data.transform.rotation.rotator())
    light.set_folder_path(f'Lights/{light_type_replace}')
    light.set_actor_label(light_data.name)
    light.set_actor_scale3d(light_data.transform.scale3d)
    light_component = unreal.BPFL.get_component(light)
    if type(light_component) == unreal.BrushComponent:
        light_component = light
    if hasattr(light_component, "settings"):
        light_component.set_editor_property("Unbound", True)
        light_component.set_editor_property("Priority",1.0)
        set_all_settings(light_data.props["Settings"], light_component)
    set_all_settings(light_data.props, light_component)
def import_decal(decal_data:actor_defs):
    if not decal_data.transform:
        return
    decal = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.DecalActor, decal_data.transform.translation, decal_data.transform.rotation.rotator())
    decal.set_folder_path(f'Decals')
    decal.set_actor_label(decal_data.name)
    decal.set_actor_scale3d(decal_data.transform.scale3d)
    decal_component = decal.decal
    decal_component.set_decal_material(get_decal_material(actor_def=decal_data))
    set_all_settings(decal_data.props, decal_component)

def fix_actor_bp(actor_data:dict,settings:Settings):
    try:
        component = unreal.BPFL.get_component_by_name(all_blueprints[actor_data.outer], actor_data.name)
    except:
        return
    if not component or not has_key("AttachParent", actor_data.props):
        return
    transform = get_transform(actor_data.props)

    component = unreal.BPFL.get_component_by_name(all_blueprints[actor_data.outer], actor_data.name)
    component.set_editor_property('relative_scale3d',transform.scale3d)
    component = unreal.BPFL.get_component_by_name(all_blueprints[actor_data.outer], actor_data.name)
    component.set_editor_property('relative_location',transform.translation)
    component = unreal.BPFL.get_component_by_name(all_blueprints[actor_data.outer], actor_data.name)
    component.set_editor_property('relative_rotation',transform.rotation.rotator())
    if has_key("OverrideMaterials", actor_data.props):
        if not settings.import_materials:
            return
        mat_override = create_override_material(actor_data.data)
        if mat_override:
            unreal.BPFL.set_override_material(all_blueprints[actor_data.outer],actor_data.name,mat_override)

def import_mesh(mesh_data:actor_defs,settings:Settings,map_obj: MapObject):
    override_vertex_colors = []
    if has_key("Template", mesh_data.data):
        fix_actor_bp(mesh_data,settings)
        return
    if not has_key("StaticMesh", mesh_data.props):
        return
    transform = get_transform(mesh_data.props)
    if not transform:
        return 
    unreal_mesh_type = unreal.StaticMeshActor
    if map_obj.is_instanced():
        unreal_mesh_type = unreal.HismActor
    mesh_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal_mesh_type,location=unreal.Vector(),rotation = unreal.Rotator())
    mesh_actor.set_actor_label(mesh_data.outer)
    if has_key("LODData", mesh_data.data):
        override_vertex_colors = get_override_vertex_color(mesh_data.data)
    if map_obj.is_instanced():
        component = mesh_actor.hism_component
        mesh_actor.set_folder_path('Meshes/Instanced')
        for inst_index in mesh_data.data["PerInstanceSMData"]:
            component.add_instance(get_transform(inst_index))
    else:
        component = mesh_actor.static_mesh_component
        folder_name = 'Meshes/Static'
        if map_obj.umap.endswith('_VFX'):
            folder_name = 'Meshes/VFX'
        mesh_actor.set_folder_path(folder_name)
    set_all_settings(mesh_data.props, component)
    component.set_world_transform(transform,False,False)
    if len(override_vertex_colors) > 0:
        unreal.BPFL.paint_sm_vertices(component,override_vertex_colors,map_obj.model_path)
    if has_key("OverrideMaterials", mesh_data.props):
        if not settings.import_materials:
            return
        mat_override = create_override_material(mesh_data.data)
        if mat_override:
            component.set_editor_property('override_materials',mat_override)
def set_mesh_build_settings(settings:Settings):
    light_res_multiplier = settings.manual_lmres_mult
    objects_path = settings.selected_map.objects_path
    list_objects = objects_path
    for m_object in os.listdir(list_objects):
        key = actor_defs(m_object)
        if key.type == "StaticMesh":
            light_map_res = round(256*light_res_multiplier/4)*4
            light_map_coord = 1
            if has_key("LightMapCoordinateIndex", key.props):
                light_map_coord = key.props["LightMapCoordinateIndex"]
            if has_key("LightMapResolution", key.props):
                light_map_res = round(key.props["LightMapResolution"]*light_res_multiplier/4)*4
            mesh_load = unreal.load_asset(f"/Game/ValorantContent/Meshes/{key.name}")
            if mesh_load:
                cast_mesh = unreal.StaticMesh.cast(mesh_load)
                actual_coord = cast_mesh.get_editor_property("light_map_coordinate_index")
                actual_resolution = cast_mesh.get_editor_property("light_map_resolution")
                if actual_coord != light_map_coord:
                    cast_mesh.set_editor_property("light_map_coordinate_index",light_map_coord)
                if actual_resolution != light_map_res:
                    cast_mesh.set_editor_property("light_map_resolution",light_map_res)
        if key.type == "BodySetup":
            if has_key("CollisionTraceFlag", key.props):
                col_trace = re.sub('([A-Z])', r'_\1', key.props["CollisionTraceFlag"])
                mesh_load = unreal.load_asset(f"/Game/ValorantContent/Meshes/{key.name}")
                if mesh_load:
                    cast_mesh = unreal.StaticMesh.cast(mesh_load)
                    body_setup = cast_mesh.get_editor_property("body_setup")
                    str_collision = 'CTF_' + col_trace[8:len(col_trace)].upper()
                    body_setup.set_editor_property("collision_trace_flag",eval(f'unreal.CollisionTraceFlag.{str_collision}'))
                    cast_mesh.set_editor_property("body_setup",body_setup)
                    
                    
def import_umap(settings:Settings,umap_data: dict, umap_name:str):
    objects_to_import = filter_objects(umap_data)
    if settings.import_blueprints:
        for objectIndex, object_data in enumerate(objects_to_import):
            object_type = get_object_type(object_data)
            if object_type == "blueprint":
                import_blueprint(actor_defs(object_data),objects_to_import)
    for objectIndex, object_data in enumerate(objects_to_import):
        object_type = get_object_type(object_data)
        actor_data_definition = actor_defs(object_data)
        if object_type == "mesh" and settings.import_Mesh:
            map_object = MapObject(settings=settings, data=object_data, umap_name=umap_name,umap_data=umap_data)
            import_mesh(mesh_data=actor_data_definition,settings=settings,map_obj=map_object)
        if object_type == "decal" and settings.import_decals:
            import_decal(actor_data_definition)
        if object_type == "light" and settings.import_lights:
            import_light(actor_data_definition,objects_to_import)
def level_streaming_setup():
    world = unreal.EditorLevelLibrary.get_editor_world()
    for level_path in all_level_paths:
        map_type = get_umap_type(level_path.split('/')[1])
        unreal.EditorLevelUtils.add_level_to_world(world,level_path,map_type)
def import_blueprint(bp_actor: actor_defs, umap_data: list):
    transform = bp_actor.transform
    if not transform:
        transform = get_scene_parent(bp_actor.data,bp_actor.outer,umap_data)
    if type(transform) == bool:
        transform = get_transform(bp_actor.props)
    if not transform:
        return
    bp_name = bp_actor.type[0:len(bp_actor.type)-2]
    loaded_bp = unreal.load_asset(f"/Game/ValorantContent/Blueprints/{bp_name}.{bp_name}")
    actor = unreal.EditorLevelLibrary.spawn_actor_from_object(loaded_bp,transform.translation,transform.rotation.rotator())
    if not actor:
        return
    all_blueprints[bp_actor.name] = actor
    actor.set_actor_label(bp_actor.name)
    actor.set_actor_scale3d(transform.scale3d)
def create_new_level(map_name):
    new_map = map_name.split('_')[0]
    map_path = (f"/Game/ValorantContent/Maps/{new_map}/{map_name}")
    loaded_map = unreal.load_asset(map_path)
    sub_system_editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    unreal.LevelEditorSubsystem.new_level(sub_system_editor,map_path)
    all_level_paths.append(map_name)
def get_override_vertex_color(mesh_data: dict):
    lod_data = mesh_data["LODData"]
    vtx_array = []
    for lod in lod_data:
        if has_key("OverrideVertexColors",lod):
            vertex_to_convert = lod["OverrideVertexColors"]["Data"]
            for rgba_hex in vertex_to_convert:
                vtx_array.append(unreal.BPFL.return_from_hex(rgba_hex))
    return vtx_array

def import_all_textures_from_material(material_data: dict, settings: Settings):
    mat_info = actor_defs(material_data[0])
    if mat_info.props:
        if has_key("TextureParameterValues",mat_info.props):
            tx_parameters = mat_info.props["TextureParameterValues"]
            for tx_param in tx_parameters:
                tex_game_path = get_texture_path(s=tx_param, f=settings.texture_format)
                if not tex_game_path:
                    continue
                tex_local_path = settings.assets_path.joinpath(tex_game_path).__str__()
                if tex_local_path not in all_textures:
                    all_textures.append(tex_local_path)
def create_material(material_data: list, settings: Settings):
    mat_data = material_data[0]
    mat_data = actor_defs(mat_data)
    parent = "BaseEnv_MAT_V4"
    if not mat_data.props:
        return
    loaded_material = unreal.load_asset(f"/Game/ValorantContent/Materials/{mat_data.name}.{mat_data.name}")
    if not loaded_material:
        loaded_material = AssetTools.create_asset(mat_data.name,'/Game/ValorantContent/Materials/', unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if has_key("Parent",mat_data.props):
        parent = return_parent(mat_data.props["Parent"]["ObjectName"])
    material_instance = unreal.MaterialInstanceConstant.cast(loaded_material)
    material_instance.set_editor_property("parent",import_shader(parent))
    set_material(settings=settings, mat_data=mat_data,ue_material=loaded_material)
## still have to fix this
def export_all_meshes(settings: Settings):
    all_meshes = []
    obj_path = settings.selected_map.folder_path.joinpath("_assets_objects.txt")
    with open (obj_path,'r') as file:
        lines = file.read().splitlines()
    exp_path = str(settings.assets_path)
    for line in lines:
        if is_blacklisted(line.split('\\')[-1]):
            continue
        line_arr = line.split('\\')
        if line_arr[0] == "Engine":
            continue
        else:
            line_arr.pop(0)
            line_arr.pop(0)
        joined_lines_back = "\\".join(line_arr)
        full_path = exp_path + '\\Game\\' + joined_lines_back + ".pskx"
        if full_path not in all_meshes:
            all_meshes.append(full_path)
    # import
    unreal.BPFL.import_meshes(all_meshes, str(settings.selected_map.objects_path))


def export_all_textures(settings: Settings):
    mat_path = settings.selected_map.materials_path
    mat_ovr_path = settings.selected_map.materials_ovr_path
    
    for path_mat in os.listdir(mat_path):
        mat_json = read_json(mat_path.joinpath(path_mat))
        import_all_textures_from_material(mat_json,settings)
    for path_ovr_mat in os.listdir(mat_ovr_path):
        mat_ovr_json = read_json(mat_ovr_path.joinpath(path_ovr_mat))
        import_all_textures_from_material(mat_ovr_json,settings)
    unreal.BPFL.import_textures(all_textures)
    
    
def create_bp(full_data: dict,bp_name: str, settings: Settings):
    BlacklistBP = ['SpawnBarrier','SoundBarrier','SpawnBarrierProjectile','Gumshoe_CameraBlockingVolumeParent_Box','DomeBuyMarker','BP_StuckPickupVolume','BP_LevelBlockingVolume','BP_TargetingLandmark','BombSpawnLocation']
    bp_name = bp_name.split('.')[0]
    bp_actor = unreal.load_asset(f'/Game/ValorantContent/Blueprints/{bp_name}')
    if not bp_actor and bp_name not in BlacklistBP:
        bp_actor = AssetTools.create_asset(bp_name,'/Game/ValorantContent/Blueprints/', unreal.Blueprint, unreal.BlueprintFactory())
    else:
        return
    data = full_data["Nodes"]
    if len(data) == 0:
        return
    root_scene = full_data["SceneRoot"]
    default_scene_root = root_scene[0].split('.')[-1]
    game_objects = full_data["GameObjects"]
    nodes_root = full_data["ChildNodes"]
    for idx, bpc in enumerate(data):
        if bpc["Name"] == default_scene_root:
            del data[idx]
            data.insert(len(data), bpc)
            break
    data.reverse()
    nodes_array = []
    for bp_node in data:
        if bp_node["Name"] in nodes_root:
            continue
        component_name = bp_node["Properties"]["ComponentClass"]["ObjectName"].replace(
            "Class ", "")
        try:
            unreal_class = eval(f'unreal.{component_name}')
        except:
            continue
        properties = bp_node["Properties"]
        if has_key("ChildNodes",properties):
            nodes_array = handle_child_nodes(properties["ChildNodes"],data,bp_actor)
        comp_internal_name = properties["InternalVariableName"]
        component = unreal.BPFL.create_bp_comp(
            bp_actor, unreal_class, comp_internal_name, nodes_array)
        if has_key("CompProps",properties):
            comp_props = properties["CompProps"]
            set_all_settings(comp_props, component)
        set_mesh_settings(properties,component)
    for game_object in game_objects:
        component = unreal.BPFL.create_bp_comp(bp_actor, unreal.StaticMeshComponent, "GameObjectMesh",nodes_array)
        set_mesh_settings(game_object["Properties"],component)

def set_mesh_settings(mesh_properties: dict, component):
    set_all_settings(mesh_properties, component)
    transform = get_transform(mesh_properties) 
    if has_key("RelativeRotation", mesh_properties):
        component.set_editor_property('relative_rotation', transform.rotation.rotator())
    if has_key("RelativeLocation", mesh_properties):
        component.set_editor_property('relative_location', transform.translation)
    if has_key("RelativeScale3D", mesh_properties):
        component.set_editor_property('relative_scale3d', transform.scale3d)

def handle_child_nodes(child_nodes_array: dict, entire_data: list, bp_actor):
    local_child_array = []
    for child_node in child_nodes_array:
        child_obj_name = child_node["ObjectName"]
        child_name = child_obj_name.split('.')[-1]
        for c_node in entire_data:
            component_name = c_node["Properties"]["ComponentClass"]["ObjectName"].replace(
                "Class ", "")
            try:
                unreal_class = eval(f'unreal.{component_name}')
            except:
                continue
            internal_name = c_node["Properties"]["InternalVariableName"]
            if "TargetViewMode" in internal_name:
                continue
            if c_node["Name"] == child_name:
                u_node, comp_node = unreal.BPFL.create_node(
                    bp_actor, unreal_class, internal_name)
                local_child_array.append(u_node)
                set_all_settings(c_node["Properties"]["CompProps"], comp_node)
                break
    return local_child_array

def export_all_blueprints(settings: Settings):
    bp_path = settings.selected_map.actors_path
    for bp in os.listdir(bp_path):
        bp_json = reduce_bp_json(read_json(settings.selected_map.actors_path.joinpath(bp)))
        create_bp(bp_json,bp,settings)

def export_all_materials(settings:Settings):
    mat_path = settings.selected_map.materials_path
    mat_ovr_path = settings.selected_map.materials_ovr_path
    for path_mat in os.listdir(mat_path):
        mat_json = read_json(mat_path.joinpath(path_mat))
        create_material(mat_json,settings)
    for path_ovr_mat in os.listdir(mat_ovr_path):
        mat_ovr_json = read_json(mat_ovr_path.joinpath(path_ovr_mat))
        create_material(mat_ovr_json,settings)
def import_map(setting):
    unreal.BPFL.change_project_settings()
    unreal.BPFL.execute_console_command('r.DefaultFeature.LightUnits 0')
    unreal.BPFL.execute_console_command('r.DynamicGlobalIlluminationMethod 0')
    all_level_paths.clear()
    settings = Settings(setting)
    umap_json_paths = get_map_assets(settings)
    if not settings.import_sublevel:
        create_new_level(settings.selected_map.name)
    clear_level()
    if settings.import_materials:
        txt_time = time.time()
        export_all_textures(settings)
        print(f'Exported all textures in {time.time() - txt_time} seconds')
        mat_time = time.time()
        export_all_materials(settings)
        print(f'Exported all materials in {time.time() - mat_time} seconds')
    m_start_time = time.time()
    if settings.import_Mesh:
        export_all_meshes(settings)
    print(f'Exported all meshes in {time.time() - m_start_time} seconds')
    bp_start_time = time.time()
    if settings.import_blueprints:
        export_all_blueprints(settings)
    print(f'Exported all blueprints in {time.time() - bp_start_time} seconds')
    umap_json_path: Path
    actor_start_time = time.time()
    with unreal.ScopedSlowTask(len(umap_json_paths), "Importing levels") as slow_task:
        slow_task.make_dialog(True)
        idx = 0
        for index, umap_json_path in reversed(
                list(enumerate(umap_json_paths))):
            umap_data = read_json(umap_json_path)
            umap_name = umap_json_path.stem
            slow_task.enter_progress_frame(
                work=1, desc=f"Importing level:{umap_name}  {idx}/{len(umap_json_paths)} ")
            if settings.import_sublevel:
                create_new_level(umap_name)
            import_umap(settings=settings, umap_data=umap_data, umap_name=umap_name)
            if settings.import_sublevel:
                unreal.EditorLevelLibrary.save_current_level()
            idx = idx + 1
        print("--- %s seconds to spawn actors ---" % (time.time() - actor_start_time))
        if settings.import_sublevel:
            level_streaming_setup()
        if settings.import_Mesh:
            set_mesh_build_settings(settings=settings)
        winsound.Beep(16000, 1500)

from ..blocks_natively_included._block_core.core_helper_uilayouts import create_ui_box_with_header
from ..blocks_natively_included._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache.get_cache

from .block_constants import CACHE_KNOWN_OBJECT_IDS
from .feature_library_import.library_installation_wrapper import Python_Library_Dependencies, Library_Installation_Wrapper

        
def uilayout_draw_main_panel(context, container):
    
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_enforecement_pip", default_closed=True)
    panel_header.label(text = "Library Dependencies")
    if panel_body is not None:  
        uilayout_draw_libraries_panel(context, panel_body)
        
    box = container.box()
    panel_header, panel_body = box.panel(idname = "_dummy_dgblocks_enforcement_blender", default_closed=True)
    panel_header.label(text = "Stable Datablock IDs")
    if panel_body is not None:  
        uilayout_draw_stable_ids_panel(context, panel_body)

def uilayout_draw_libraries_panel(context, container):
    
    box = create_ui_box_with_header(context, container, ["Home Folder for Library Downloads", "Editable in Preferences -> Addons"])
    folder_str = Library_Installation_Wrapper._get_library_home_path()
    row = box.row()
    row.label(text = folder_str)
    row.operator("dgblocks.open_folder", text = "", icon="FOLDER_REDIRECT").folder_path = folder_str
    
    box = create_ui_box_with_header(context, container, "Required Python Libraries")
    row = box.row()
    col_left = row.column()
    libraries = [i for i in Python_Library_Dependencies]
    for library_data in libraries:
        
        library_name = library_data.value[0]
        row = box.row()
        split = row.split(factor = 0.7)
        col_left = split.column()
        col_right = split.column()
        col_right.alignment = "RIGHT"
        if Library_Installation_Wrapper.is_installed(library_name):
            col_left.label(text=f"{library_name} is installed", icon='CHECKMARK')
            op = col_right.operator("dgblocks.library_manager", text="Uninstall")
            op.library_name = library_name
            op.action = "UNINSTALL"
        else:
            row.alert = True
            col_left.alert = True
            col_left.label(text=f"{library_name} is not installed", icon='ERROR')
            op = col_right.operator("dgblocks.library_manager", text="Install")
            op.library_name = library_name
            op.action = "INSTALL"
            
            
def uilayout_draw_stable_ids_panel(context, container):
    
    # Get the stable ID cache
    id_cache = Wrapper_Runtime_Cache.get_cache(CACHE_KNOWN_OBJECT_IDS, default={})
    
    # Display header
    box = container.box()
    header_row = box.row()
    header_row.label(text="Object Name", icon='OBJECT_DATA')
    header_row.label(text="Stable ID", icon='MODIFIER')
    
    # Display all scene objects with their stable IDs
    if context.scene and context.scene.objects:
        for obj in context.scene.objects:
            props = getattr(obj, "dgblocks_object_stable_id_props", None)
            if props and props.stable_id:
                row = box.row()
                row.label(text=obj.name)
                row.label(text=props.stable_id)
    else:
        box.label(text="No objects in scene", icon='INFO')
    
    # Display summary info
    container.separator()
    info_box = container.box()
    info_box.label(text=f"Total IDs in Cache: {len(id_cache)}", icon='KEYINGSET')
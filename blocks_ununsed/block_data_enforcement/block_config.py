
from enum import Enum
import bpy

class Python_Library_Dependencies(Enum):
    # 1st list element, used when installing = "pip install <name>" 
    # 2nd list element, used when importing = "import <name>" 
    # These often match, can occasionally differ
    NUMBA = ["numba", "numba"]
    SHAPELY = ["shapely", "shapely"]
    SIX = ["six", "six"]

my_stable_id_target_list = [
    bpy.types.Object, 
    bpy.types.Material, 
    bpy.types.Scene, 
    bpy.types.World]

def my_filter_for_stable_id_assignment(context:bpy.context, datablock_member:bpy.types, logger = None) -> bool:
    
    #...
    # Check if it's a specific type
    if isinstance(datablock_member, bpy.types.Object):
        logger.info("It's an Object")
    
    # Check the name
    name = datablock_member.name
    if datablock_member.name.startswith("_"):
        return False  # skip names starting with underscore
    
    # Check if it's from a linked library
    if datablock_member.library is not None:
        print(f"Linked from: {datablock_member.library.filepath}")
        return False  # skip linked datablocks
    
    # Check if it's an override of a linked datablock
    if datablock_member.override_library is not None:
        print("This datablock is sourced from a library override")
    
    # Check if it's indirectly linked (dependency of a linked datablock)
    if datablock_member.is_library_indirect:
        return False
    
    # Check if it has a fake user (preserved even with 0 users)
    if datablock_member.use_fake_user:
        return False
        log.debug("Has fake user")
    
    # Check user count
    if datablock_member.users == 0:
        return False  # orphan data
    
    # Check if it's embedded (e.g., node trees inside materials)
    if datablock_member.is_embedded_data:
        return False
    
    # Get the type as a string (useful for logging/debugging)
    type_name = type(datablock_member).__name__  # e.g., "Object", "Mesh"
    bl_rna_type = datablock_member.bl_rna.identifier  # same thing via RNA
    #...
    
    return True
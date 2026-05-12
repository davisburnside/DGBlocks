import bpy
from bpy.app.handlers import persistent
from ...core_helpers.constants import Core_Block_Loggers
from ...core_features.loggers.feature_wrapper import get_logger  # type: ignore

# Blender's msgbus needs some (any) python object to hold a reference to
_msgbus_owner_for_active_scene = object()
_msgbus_owner_for_active_window_scene_viewlayer = object()
_msgbus_owner_for_scene_names = object()
_msgbus_T1 = object()

@persistent
def _msgbus_window_scene_changed(*args):
    """Called by bpy.msgbus when the active scene changes in any window."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Window Scene changed — now in '{bpy.context.scene.name_full}'")

@persistent
def _msgbus_window_scene_viewlayer_changed(*args):
    """Called by bpy.msgbus when the active view layer changes."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Window Scene Viewlayer changed — now in '{bpy.context.view_layer.name}'")

@persistent
def _msgbus_scene_name_changed(*args):
    """Called by bpy.msgbus when the active scene name changes."""
    logger = get_logger(Core_Block_Loggers.SCENE_MONITOR)
    print(f"msgbus: Scene Name changed — now in '{bpy.context.scene.name_full}'")

def _msgbus_test1(*args):
    print(f"TEST1   '")

# list of tuples to define msgbus subscriptions
# tuple[0] = msgbus sub "owner" object
# tuple[1] = msgbus key: the data being listened to
# tuple[2] = callback function when the data changes
msgbus_subs = [
    # (_msgbus_owner_for_active_scene, (bpy.types.Window, "scene"), _msgbus_window_scene_changed),
    # (_msgbus_owner_for_active_window_scene_viewlayer, (bpy.types.Window, "view_layer"), _msgbus_window_scene_viewlayer_changed),
    # (_msgbus_owner_for_scene_names, (bpy.types.Scene, "name"), _msgbus_scene_name_changed),
    # (_msgbus_T1, (bpy.types.BlendData, "scenes"), _msgbus_test1)
]

def clear_msgbuses(msgbus_subs: list[tuple]):

    for msgbus_owner, msgbus_key, _ in msgbus_subs:
        try:
            print(f"clearing msgbus {msgbus_key}")
            bpy.msgbus.clear_by_owner(msgbus_owner)
        except Exception as e:
            print(e)

def add_msgbuses(msgbus_subs: list[tuple]):

    for (msbus_owner, msgbus_key, msgbus_callback) in msgbus_subs:
        print(f"Registering msgbus listener for {msgbus_key}")
        bpy.msgbus.subscribe_rna(
            key=msgbus_key,
            owner=msbus_owner,
            args=(),
            notify=msgbus_callback,
        )

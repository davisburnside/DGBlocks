
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d

default_modal_passthrough = {'PASS_THROUGH'}
default_modal_consumed = {'RUNNING_MODAL'}

# Region types that sit ON TOP of a VIEW_3D's WINDOW region. A point inside one of these
# is over the UI, not over the viewport, even though it is also inside WINDOW's rect.
_OVERLAY_REGION_TYPES = ("UI", "TOOLS", "TOOL_PROPS", "HEADER", "TOOL_HEADER", "ASSET_SHELF",
                         "ASSET_SHELF_HEADER", "HUD", "NAV_BAR", "EXECUTE", "FOOTER")

def get_viewport_region(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region
    return None, None


# ==============================================================================================================================
# EVENT CONTEXT
# ==============================================================================================================================

def _is_point_in_region(region, x, y) -> bool:
    return (region.x <= x < region.x + region.width) and (region.y <= y < region.y + region.height)


def is_event_over_viewport(context, event) -> bool:
    """True only when the pointer is over the 3D viewport's drawable area.

    This is what stops a click on the N-panel (or the header, the toolbar, the redo
    popover) from reaching the selection logic and wiping the user's picks.

    Two tests are needed, not one. A raw `modal_handler_add` handler receives EVERY
    event in the window regardless of where the pointer is, so the WINDOW region has to
    be hit-tested manually — and the N-panel and toolbar are drawn INSIDE the area, on
    top of WINDOW's rect, so being inside WINDOW is not by itself sufficient. Each
    overlay region is therefore subtracted.

    Note this is a geometric test, not an event-routing one: it cannot know whether a
    gizmo or a modal operator elsewhere has claimed the event. That is what the
    keymap/WorkSpaceTool migration is for; this guard fixes the case that actually loses
    the user's work today.
    """
    x, y = event.mouse_x, event.mouse_y

    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        if not (area.x <= x < area.x + area.width and area.y <= y < area.y + area.height):
            continue

        window_region = None
        for region in area.regions:
            if region.type == 'WINDOW':
                window_region = region
            elif region.type in _OVERLAY_REGION_TYPES and _is_point_in_region(region, x, y):
                return False

        return window_region is not None and _is_point_in_region(window_region, x, y)

    return False


# 2nd-level Helper funcs -----------------------------------

def _get_raycast_data(context, event):
    """Get viewport ray data for raycasting. Returns (origin, direction) in world space."""
    area, region = get_viewport_region(context)
    region_3d = area.spaces.active.region_3d

    # convert window-space mouse to region-space
    region_mouse_xy = (
        event.mouse_x - region.x,
        event.mouse_y - region.y
    )
    
    # get ray data from viewport "camera" (not Camera Object)
    vec_raycast_viewport_origin = region_2d_to_origin_3d(region, region_3d, region_mouse_xy)
    vec_ray_direction = region_2d_to_vector_3d(region, region_3d, region_mouse_xy)
    
    return vec_raycast_viewport_origin, vec_ray_direction



"""
Leaf module for the animations sub-feature.

Imports NOTHING from the parent block. This is what keeps the sub-feature free of
circular imports: common_declarations.py -> ui.py -> animations.constants is safe,
because the chain terminates here.
"""

# Valid values for Animation_Declaration.data_type
ANIM_DATA_TYPE_UNIFORMS = 'uniforms_data'
ANIM_DATA_TYPE_BATCH    = 'batch_data'

# Valid values for Animation_Declaration.loop_mode
ANIM_LOOP_ONCE      = 'once'        # play start -> end, then finish
ANIM_LOOP_REPEAT    = 'repeat'      # play start -> end, snap back to start, repeat
ANIM_LOOP_PING_PONG = 'ping_pong'   # play start -> end, then end -> start, repeat

ANIM_VALID_LOOP_MODES = (ANIM_LOOP_ONCE, ANIM_LOOP_REPEAT, ANIM_LOOP_PING_PONG)

# batch_data attribute that may never be animated (integer topology, not interpolatable)
ANIM_FORBIDDEN_DATA_NAME = '_indices'

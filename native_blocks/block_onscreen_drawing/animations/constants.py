
# Valid values for Animation_Declaration.data_type
ANIM_DATA_TYPE_UNIFORMS = 'uniforms_data'
ANIM_DATA_TYPE_BATCH  = 'batch_data'

# Valid values for Animation_Declaration.loop_mode
ANIM_LOOP_ONCE = 'once'
ANIM_LOOP_REPEAT = 'repeat'
ANIM_LOOP_PING_PONG = 'ping_pong'

ANIM_VALID_LOOP_MODES = (ANIM_LOOP_ONCE, ANIM_LOOP_REPEAT, ANIM_LOOP_PING_PONG)

# batch_data attribute that may never be animated (integer topology, not interpolatable)
ANIM_FORBIDDEN_DATA_NAME = '_indices'

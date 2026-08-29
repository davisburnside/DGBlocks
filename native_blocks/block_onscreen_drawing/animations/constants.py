
# Valid values for Animation_Declaration.data_type
ANIM_DATA_TYPE_UNIFORMS = 'uniforms_data'
ANIM_DATA_TYPE_BATCH  = 'batch_data'

# Valid values for Animation_Declaration.loop_mode
ANIM_LOOP_ONCE = 'once'
ANIM_LOOP_REPEAT = 'repeat'
ANIM_LOOP_PING_PONG = 'ping_pong'

ANIM_VALID_LOOP_MODES = (ANIM_LOOP_ONCE, ANIM_LOOP_REPEAT, ANIM_LOOP_PING_PONG)

# Valid values for Animation_Declaration.easing — applied to t (0..1) before the lerp.
# "Out" variant only, one per easings.net family — the trimmed "essentials" subset picked
# for the global builtin-animation timing-function property (Out reads best for UI motion).
ANIM_EASE_LINEAR = 'linear'
ANIM_EASE_EASE_OUT_SINE = 'ease_out_sine'
ANIM_EASE_EASE_OUT_QUAD = 'ease_out_quad'
ANIM_EASE_EASE_OUT_CUBIC = 'ease_out_cubic'
ANIM_EASE_EASE_OUT_QUART = 'ease_out_quart'
ANIM_EASE_EASE_OUT_QUINT = 'ease_out_quint'
ANIM_EASE_EASE_OUT_EXPO = 'ease_out_expo'
ANIM_EASE_EASE_OUT_CIRC = 'ease_out_circ'
ANIM_EASE_EASE_OUT_BACK = 'ease_out_back'
ANIM_EASE_EASE_OUT_ELASTIC = 'ease_out_elastic'
ANIM_EASE_EASE_OUT_BOUNCE = 'ease_out_bounce'

ANIM_VALID_EASINGS = (
    ANIM_EASE_LINEAR,
    ANIM_EASE_EASE_OUT_SINE,
    ANIM_EASE_EASE_OUT_QUAD,
    ANIM_EASE_EASE_OUT_CUBIC,
    ANIM_EASE_EASE_OUT_QUART,
    ANIM_EASE_EASE_OUT_QUINT,
    ANIM_EASE_EASE_OUT_EXPO,
    ANIM_EASE_EASE_OUT_CIRC,
    ANIM_EASE_EASE_OUT_BACK,
    ANIM_EASE_EASE_OUT_ELASTIC,
    ANIM_EASE_EASE_OUT_BOUNCE,
)

# (value, label, description) triples for building the easing EnumProperty — one entry per
# ANIM_VALID_EASINGS member, in the same order.
ANIM_EASING_UI_ITEMS = (
    (ANIM_EASE_LINEAR,           "Linear",         "No easing — constant rate"),
    (ANIM_EASE_EASE_OUT_SINE,    "Ease Out Sine",    "Gentle deceleration"),
    (ANIM_EASE_EASE_OUT_QUAD,    "Ease Out Quad",    "Mild deceleration"),
    (ANIM_EASE_EASE_OUT_CUBIC,   "Ease Out Cubic",   "Moderate deceleration"),
    (ANIM_EASE_EASE_OUT_QUART,   "Ease Out Quart",   "Strong deceleration"),
    (ANIM_EASE_EASE_OUT_QUINT,   "Ease Out Quint",   "Very strong deceleration"),
    (ANIM_EASE_EASE_OUT_EXPO,    "Ease Out Expo",    "Sharp initial burst, long settle"),
    (ANIM_EASE_EASE_OUT_CIRC,    "Ease Out Circ",    "Circular deceleration curve"),
    (ANIM_EASE_EASE_OUT_BACK,    "Ease Out Back",    "Slight overshoot past the end value"),
    (ANIM_EASE_EASE_OUT_ELASTIC, "Ease Out Elastic", "Springy overshoot with decaying oscillation"),
    (ANIM_EASE_EASE_OUT_BOUNCE,  "Ease Out Bounce",  "Decaying bounces landing on the end value"),
)

# batch_data attribute that may never be animated (integer topology, not interpolatable)
ANIM_FORBIDDEN_DATA_NAME = '_indices'

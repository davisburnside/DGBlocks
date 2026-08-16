p = r'block_onscreen_drawing/builtin_shaders_and_effects/custom_shader_polyline_annotated.py'
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix 1: vertex_in names must match GLSL source variable names (seg_a, seg_b)
old1 = 'shader_info.vertex_in(0, "VEC3", "pos_a")\n        shader_info.vertex_in(1, "VEC3", "pos_b")'
new1 = 'shader_info.vertex_in(0, "VEC3", "seg_a")\n        shader_info.vertex_in(1, "VEC3", "seg_b")'
assert old1 in c, 'FAIL: vertex_in anchor not found'
c = c.replace(old1, new1, 1)

# Fix 2: batch_for_shader content keys must match vertex_in names
old2 = '"pos_a": pos_a, "pos_b": pos_b, "vcol":  vcol,'
new2 = '"seg_a": pos_a, "seg_b": pos_b, "vcol":  vcol,'
assert old2 in c, 'FAIL: batch content anchor not found'
c = c.replace(old2, new2, 1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('Fixed: vertex_in names and batch content keys now use seg_a/seg_b to match GLSL source')

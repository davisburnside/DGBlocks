# Blender Depsgraph & msgbus Update Triggers

Companion to *Property Update Callbacks* and *Data Persistence*.
Behaviour described for Blender 4.x. Verify edge cases in your target version — several of these are
long-standing "known issues" rather than specified behaviour.

---

## The three notification systems at a glance

| | Property `update=` | `depsgraph_update_post` | `bpy.msgbus` |
|---|---|---|---|
| Watches | one property you declared | all evaluated data in the view layer | one RNA property (or all instances of a type) |
| Tells you *what* changed | ✅ `self` + context | 🟡 roughly, via `depsgraph.updates` | ❌ only your own `args` |
| Python RNA write | ✅ Yes | 🟡 Only if RNA update runs¹ | ✅ Yes |
| UI edit | ✅ Yes | 🟡 Only if RNA update runs¹ | ✅ Yes |
| Viewport transform (G/R/S) | ❌ No | ✅ Yes | ❌ No² |
| Animation / drivers | ✅ Yes | ✅ Yes | ❌ No |
| Timing | immediate, mid-operator | after depsgraph evaluation | deferred until all operators finish |
| Coalesced | ❌ every write | ✅ per update cycle | ✅ once per property per cycle |
| Included in undo step | ✅ Yes | ✅ Yes | ❌ No³ |
| Survives file load | n/a (lives on the property) | only with `@persistent` | ❌ must re-subscribe |

¹ See the *Python-defined properties* trap below — the single biggest gotcha on this page.
² The transform system writes matrices directly, not through RNA.
³ Changes made from a msgbus callback are not recorded in the related undo step, so Undo → Redo silently drops them.

---

## `depsgraph_update_pre` / `depsgraph_update_post`

```python
from bpy.app.handlers import persistent

@persistent
def on_depsgraph(scene, depsgraph):
    ...

bpy.app.handlers.depsgraph_update_post.append(on_depsgraph)
```

### What fires it

| Event | Fires? | Notes |
|---|---|---|
| Object transform via Python | ✅ Yes | |
| Transform in viewport (G/R/S, gizmo) | ✅ Yes | |
| Selection change (click, box select) | ✅ Yes | Not every select operator tags; mostly consistent in practice |
| Active object change | ✅ Yes | |
| Mode toggle (Object ↔ Edit ↔ Pose) | ✅ Yes | |
| Mesh edit inside Edit Mode | ✅ Yes | Original mesh datablock is not written until you leave Edit Mode |
| Add / delete / duplicate object | ✅ Yes | |
| Rename a datablock | ✅ Yes | |
| Parenting, collection link/unlink | ✅ Yes | |
| Modifier add/remove/property change | ✅ Yes | `is_updated_geometry` |
| Material / shader node edit | ✅ Yes | `is_updated_shading` |
| Frame change / scrubbing | ✅ Yes | `frame_change_pre/post` also fire |
| Undo / redo | ✅ Yes | |
| Open .blend | ✅ Yes | After `load_post` |
| **Built-in** RNA property (UI or Python) | ✅ Yes | These have C-level update functions that tag the ID |
| `bpy.props` property| ✅ Yes | |
| Custom IDProperty from Python (`obj["x"] = 1`) | ❌ No | Classic driver-not-refreshing bug; call `obj.update_tag()` |
| Custom property edited in the **UI** | ✅ Yes | UI writes go through RNA; IDProperties are tagged broadly |
| WindowManager / Screen / UI-only props | ❌ No | Not depsgraph-evaluated datablocks |
| `id.update_tag()` (+ next evaluation) | ✅ Yes | The manual escape hatch |
| `view_layer.update()` with nothing tagged | ❌ No | |
| `context.evaluated_depsgraph_get()` (read) | ❌ No | |

### The Python-defined property trap

```python
# Does NOT tag the depsgraph, does NOT fire depsgraph handlers:
scene.my_addon.strength = 0.5        # bpy.props prop with no update=
obj["uuid"] = "abc123"               # raw IDProperty

# Does:
strength: FloatProperty(update=lambda self, ctx: None)   # empty update fn is enough
# or, explicitly:
obj.update_tag()                     # then let the next cycle evaluate
```

Tracker refs: #113930 (bpy.props / custom props are not considered an ID change from code),
#63793 / #91140 (drivers reading custom props don't refresh).

### `depsgraph.updates`

| Member | Meaning |
|---|---|
| `update.id` | The **evaluated** datablock — use `update.id.original` for the real one |
| `update.is_updated_geometry` | Mesh/curve data changed |
| `update.is_updated_transform` | Matrix changed |
| `update.is_updated_shading` | Material/shader changed |

The list can be empty even when the handler fires. Always guard before indexing.

### Handler gotchas

| Gotcha | Mitigation |
|---|---|
| Writing to `bpy.data` inside the handler re-tags → infinite recursion | Re-entrancy flag, or defer with `bpy.app.timers.register` |
| Handler is removed on file load / New File | Decorate with `@bpy.app.handlers.persistent` |
| Writing to `update.id` (evaluated copy) doesn't stick | Write to `update.id.original`; UI may still not reflect it |
| Fires on *every selection click* | Keep the handler cheap; early-out on `depsgraph.updates` contents |
| Doesn't reflect animated values while rendering | Use `frame_change_post(scene, depsgraph)` + `obj.evaluated_get(depsgraph)` |
| Handlers stack on script reload | Remove by function `__name__` before appending |

---

## `bpy.msgbus`

```python
owner = object()   # keep a module-level reference, or it gets collected

bpy.msgbus.subscribe_rna(
    key=(bpy.types.LayerObjects, "active"),
    owner=owner,
    args=(),
    notify=on_active_changed,
)
```

### What fires it

| Event | Notify? | Notes |
|---|---|---|
| Python RNA assignment (`obj.location.x += 3`) | ✅ Yes | Documented behaviour |
| UI slider / field / button edit | ✅ Yes | Documented behaviour |
| Viewport transform (G/R/S, gizmo, drag) | ❌ No | Transform system bypasses RNA |
| Animation system / drivers | ❌ No | Documented exclusion |
| Undo / redo | ⚠️ Unreliable | Don't rely on it; subscriptions can also be dropped |
| `collection.add()` / `.remove()` / `.move()` | ❌ No | Same blind spot as update callbacks |
| ID created / deleted (`bpy.data.objects.new`) | ❌ No | No RNA property write to observe |
| `bpy.props` property with no `update=`, set from Python | ⚠️ Expect No | Same `rna_property_update()` path that skips depsgraph tagging also does the msgbus publish — test this in your version |
| Raw IDProperty write from Python | ⚠️ Expect No | As above |
| `bpy.msgbus.publish_rna(key=...)` | ✅ Yes | The manual escape hatch |

### Subscription lifetime

| Event | Subscription survives? |
|---|---|
| Ordinary property edits | ✅ Yes |
| New File (Ctrl+N) / Open .blend | ❌ Cleared — re-subscribe from a `@persistent` `load_post` handler |
| Undo / redo | ⚠️ May be dropped |
| Script reload (F8) / addon re-register | ❌ New owner object — `clear_by_owner(old)` first, then re-subscribe |
| Owner object garbage-collected | ❌ Silently dead — hold the owner at module level |
| `options={'PERSISTENT'}` | 🟡 Survives some re-registration cases; still re-subscribe on `load_post` to be safe |

### Key forms

| Key | Scope |
|---|---|
| `(bpy.types.Object, "location")` | Every Object instance |
| `obj.path_resolve("name", False)` | That one datablock's property |
| `(bpy.types.LayerObjects, "active")` | Active-object changes — the canonical example |
| `bpy.types.Object` | Whole struct type (broad, noisy) |

Properties converted to Python objects on access (strings, ints) must be keyed with
`path_resolve(name, False)`, not by reading them.

### msgbus gotchas

| Gotcha | Consequence |
|---|---|
| Callback receives only `args` | You get no "what changed" info — pass identifiers in, or re-read state |
| Coalesced once per property per cycle | Ten assignments in a loop → one callback |
| Deferred until operators finish | Don't assume ordering relative to `update=` callbacks |
| Changes aren't in the undo step | Undo → Redo can silently discard your reaction |
| Silent failure modes | A dead owner or bad key throws no error; it just never fires |

---

## Choosing a mechanism

| Goal | Use |
|---|---|
| React to your own addon property | `update=` on the property |
| React to a built-in property edited in the UI | `bpy.msgbus` |
| React to active object / selection | `bpy.msgbus` on `LayerObjects.active`, or a depsgraph handler |
| React to transforms, geometry edits, object add/delete | `depsgraph_update_post` |
| React to CollectionProperty add/remove | Operator logic or sentinel counter (see Property Update Callbacks sheet) |
| React to frame changes | `frame_change_pre` / `frame_change_post` |
| React to file load / save | `load_post`, `save_pre` (all `@persistent`) |
| Force downstream refresh after a Python write | `id.update_tag()`, then `context.view_layer.update()` if you need it now |

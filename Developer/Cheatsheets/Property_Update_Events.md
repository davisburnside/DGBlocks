# Blender Property Update Callback Cheat Sheet

## General Rules

| Trigger | Fires? |
|---|---|
| RNA property assignment (`obj.prop = val`) | ✅ Yes |
| User edits value in UI | ✅ Yes |
| Undo/redo | ✅ Yes |
| Animation/drivers writing a value | ✅ Yes |
| Reading a property | ❌ No |
| Setting the same value (no diff check) | ✅ Yes |
| Internal C-level writes bypassing RNA | ❌ No |
| Property registration/initialization | ❌ No |

---

## Scalar Properties
`FloatProperty` `IntProperty` `BoolProperty` `StringProperty` `EnumProperty`

| Action | Update fires? | `self` is... |
|---|---|---|
| Value set via Python | ✅ Yes | Owner struct |
| Value set via UI | ✅ Yes | Owner struct |
| Value unchanged but re-assigned | ✅ Yes | Owner struct |

---

## PointerProperty

| Action | PointerProperty update fires? |
|---|---|
| Pointer reassigned to different object | ✅ Yes |
| Internal property of pointed-to struct changed | ❌ No |
| Pointed-to struct's own property update | ✅ Yes (that prop's callback) |

---

## PropertyGroup

PropertyGroup has no update callback of its own. Updates only fire on individual properties inside it.

| Action | Fires? | `self` is... |
|---|---|---|
| Child property set via Python | ✅ Yes (child's callback) | PropertyGroup instance |
| Child property set via UI | ✅ Yes (child's callback) | PropertyGroup instance |
| Any child changes → group-level notification | ❌ No (no such mechanism) | — |

---

## CollectionProperty

| Action | CollectionProperty update fires? | Item property update fires? |
|---|---|---|
| `collection.add()` | ❌ No | ❌ No |
| `collection.remove(i)` | ❌ No | ❌ No |
| `collection.move(a, b)` | ❌ No | ❌ No |
| `collection[i].prop = val` | ❌ No | ✅ Yes |
| `collection[i].prop` edited in UI | ❌ No | ✅ Yes |

---

## CollectionProperty Workarounds

| Workaround | Notes |
|---|---|
| Sentinel `IntProperty` (manual counter) | Increment/decrement on add/remove; attach update to it |
| Logic inside the operator | Put post-mutation code in `execute()` of add/remove operator |
| `bpy.app.handlers` + cached length | Poll for length changes in e.g. `depsgraph_update_post` |
| `bpy.msgbus` | ❌ Also does not fire for add/remove |
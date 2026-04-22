
# Blender data persistence & storage options


  | Event                   | `WindowManager`          | `Scene`                  | `Object` / `Mesh` etc.   | `bpy.app.driver_namespace` | `AddonPreferences`  | External (.json)    | `Runtime Cache (RTC)`    |
| :---------------------- | :----------------------- | :----------------------- | :----------------------- | :------------------------- | :------------------ | :------------------ | :------------------ |
| **Script Reload (F8)**  | ❌ Resets                | ✅ Persists              | ✅ Persists              | ✅ Persists                | ✅ Persists         | ✅ Persists         | ❌ Not saved               |
| **New File (Ctrl+N)**   | ❌ Resets¹      | ❌ Resets                | ❌ Resets                | ✅ Persists                | ✅ Persists         | ✅ Persists         | ❌ Not saved               |
| **Open .blend File**    | 📂 Loaded from file²    | 📂 Loaded from file      | 📂 Loaded from file      | ✅ Persists                | ✅ Persists         | ✅ Persists         | ❌ Not saved               |
| **Blender Restart**     | ❌ Resets                | ❌ Resets                | ❌ Resets                | ❌ Resets                  | ✅ Persists         | ✅ Persists         |❌ Not saved               |
| **Save Startup (Ctrl+U)**| ✅ Baked into startup   | ✅ Baked into startup    | ✅ Baked into startup    | ❌ Not saved               | ✅ Persists         | ✅ Persists         |❌ Not saved               |
----
¹ WindowManager still *exists* after Ctrl+N (the addon stays registered), but all property
  values reset to their declared defaults — functionally equivalent to a reset.

² WindowManager props ARE serialized into .blend files. On open, values are restored from
  the file if the property existed when it was saved; otherwise they fall back to defaults.
  This makes wm props surprisingly useful for per-file UI state.




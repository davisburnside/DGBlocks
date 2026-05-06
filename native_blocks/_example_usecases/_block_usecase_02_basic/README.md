# block-example-simple-2

A fully wired example block demonstrating all standard DGBlocks features.

- Depends on `block-core` and `block-debug-console-print`
- Subscribes to all 4 core hooks: `hook_core_event_undo`, `hook_core_event_redo`, `hook_block_registered`, `hook_block_unregistered`
- Subscribes to both debug-console-print hooks: `hook_debug_get_state_data_to_print`, `hook_debug_uilayout_draw_console_print_settings`
- Defines one logger (`DEMO`) and one RTC member (`DEMO_DATA`)
- Provides a `PropertyGroup` with a demo toggle, an operator that logs a message, and a panel to expose them

Use this as a reference when building a new block that needs the full framework.
